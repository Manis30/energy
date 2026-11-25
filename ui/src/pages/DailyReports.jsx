import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import DailyOperationsPipeline from './daily-reports/DailyOperationsPipeline';
import UploadHistorySection from './daily-reports/UploadHistorySection';
import { dailyReportsApi } from '../services/dailyReportsApi';
import { findingsApi } from '../services/findingsApi';
import './daily-reports/daily-operations.css';

const DEFAULT_REPORTING_DATE = '2026-10-15';
const DEFAULT_PLANT_ID = 'IN-TN-01';

export default function DailyReports() {
  const [searchParams, setSearchParams] = useSearchParams();
  const dateFromUrl = searchParams.get('date');

  const [reportingDate, setReportingDate] = useState(() => dateFromUrl || DEFAULT_REPORTING_DATE);
  const [plantId, setPlantId] = useState(DEFAULT_PLANT_ID);
  const [showHistoryModal, setShowHistoryModal] = useState(false);

  // Data Entry State: Energy and Production editable rows & master data
  const [energyRows, setEnergyRows] = useState([]);
  const [productionRows, setProductionRows] = useState([]);
  const [masterData, setMasterData] = useState(null);
  const [savedCounts, setSavedCounts] = useState(null);
  const [loadingSaved, setLoadingSaved] = useState(true);
  const [validationResult, setValidationResult] = useState(null);
  const [savingEntries, setSavingEntries] = useState(false);

  // Pipeline execution state from backend
  const [pipelineState, setPipelineState] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [statusError, setStatusError] = useState(null);


  // Expanded stage flags
  const [expandedStages, setExpandedStages] = useState({
    data_upload: true,
    validation: true,
    database_ingestion: true,
    data_reconciliation: false,
    daily_analytics: false,
    intelligence_report: false,
    anomaly_detection: false,
    investigation_handoff: false,
  });

  // Uploaded file buffers
  const [energyFile, setEnergyFile] = useState(null);
  const [productionFile, setProductionFile] = useState(null);
  const [ingestMode, setIngestMode] = useState('INCREMENTAL');

  // Operation progress flags
  const [validating, setValidating] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [runningDownstream, setRunningDownstream] = useState(false);
  const [syncingFindings, setSyncingFindings] = useState(false);
  const [actionSuccessMsg, setActionSuccessMsg] = useState(null);

  // Overlap prevention ref to protect against rapid repeated clicks
  const isCommittingRef = useRef(false);

  // Synchronized active scope refs to prevent race conditions & out-of-order responses
  const reportingDateRef = useRef(reportingDate);
  const plantIdRef = useRef(plantId);
  const statusRequestIdRef = useRef(0);
  const recordsRequestIdRef = useRef(0);

  useEffect(() => {
    reportingDateRef.current = reportingDate;
  }, [reportingDate]);

  useEffect(() => {
    plantIdRef.current = plantId;
  }, [plantId]);

  // Date mismatch and persistence result states
  const [dateMismatch, setDateMismatch] = useState(null);
  const [lastIngestResult, setLastIngestResult] = useState(null);
  const [failedReportType, setFailedReportType] = useState(null);

  // Active selected stage for single-panel horizontal stepper view
  const [selectedStage, setSelectedStage] = useState('data_upload');

  // Sync date changes with URL and reset uncommitted file buffers
  const handleDateChange = (newDate) => {
    reportingDateRef.current = newDate;
    setReportingDate(newDate);
    setSelectedStage('data_upload');
    setEnergyFile(null);
    setProductionFile(null);
    setStatusError(null);
    setActionSuccessMsg(null);
    setDateMismatch(null);
    setLastIngestResult(null);
    setFailedReportType(null);
    setSavedCounts(null);
    setLoadingSaved(true);
    setSearchParams({ date: newDate });
  };

  const handleSwitchDate = (newDate) => {
    setDateMismatch(null);
    handleDateChange(newDate);
  };

  // Switch both Plant and Date (used when Add Readings modal saves for a different plant/date)
  const handleSwitchPlantAndDate = useCallback((newPlant, newDate) => {
    let changed = false;
    if (newDate && newDate !== reportingDateRef.current) {
      reportingDateRef.current = newDate;
      setReportingDate(newDate);
      setSearchParams({ date: newDate });
      changed = true;
    }
    if (newPlant && newPlant !== plantIdRef.current) {
      plantIdRef.current = newPlant;
      setPlantId(newPlant);
      changed = true;
    }
    if (changed) {
      setStatusError(null);
      setActionSuccessMsg(null);
      setDateMismatch(null);
      setSelectedStage('data_upload');
      setSavedCounts(null);
      setLoadingSaved(true);
    }
  }, [setSearchParams]);

  // Helper to merge authoritative pipeline state safely:
  // - Enforces matching plant and reporting date
  // - Prevents older/superseded run IDs from overwriting active current runs
  // - Prevents partial responses from wiping unreturned stage data
  // - Treats explicit status from latest authoritative response as valid (including NOT_STARTED)
  const applyAuthoritativePipelineState = useCallback((incoming, expectedDate, expectedPlant) => {
    if (!incoming) return;

    const activeDate = reportingDateRef.current;
    const activePlant = plantIdRef.current;

    // Reject updates for non-matching date or plant
    if (expectedDate && expectedDate !== activeDate) return;
    if (expectedPlant && expectedPlant !== activePlant) return;
    if (incoming.reporting_date && incoming.reporting_date !== activeDate) return;
    if (incoming.plant_id && incoming.plant_id !== activePlant) return;

    setPipelineState((prev) => {
      if (!prev) return incoming;

      // Check run ID consistency if available:
      // Don't let a superseded or non-current run overwrite an active current run
      const prevRun = prev.pipeline_run;
      const incomingRun = incoming.pipeline_run;
      if (
        prevRun?.run_id &&
        incomingRun?.run_id &&
        prevRun.run_id !== incomingRun.run_id &&
        incomingRun.is_current === false &&
        prevRun.is_current !== false
      ) {
        return prev;
      }

      // Preserve complete stage map when incoming response has partial stages,
      // while honoring explicit authoritative stage statuses (including resets to NOT_STARTED)
      const prevStages = prev.stages || {};
      const incomingStages = incoming.stages || {};
      const mergedStages = {
        ...prevStages,
        ...incomingStages,
      };

      return {
        ...prev,
        ...incoming,
        stages: mergedStages,
        database_state: incoming.database_state || prev.database_state,
      };
    });
  }, []);

  // Fetch Authoritative Pipeline State from Backend
  const fetchStatus = useCallback(async (targetDate = reportingDateRef.current, targetPlant = plantIdRef.current) => {
    const reqId = ++statusRequestIdRef.current;
    setLoadingStatus(true);
    setStatusError(null);
    try {
      const res = await dailyReportsApi.getPipelineStatus(targetDate, targetPlant);
      if (
        reqId !== statusRequestIdRef.current ||
        targetDate !== reportingDateRef.current ||
        targetPlant !== plantIdRef.current
      ) {
        return;
      }

      applyAuthoritativePipelineState(res, targetDate, targetPlant);

      // Auto-expand active or completed downstream stages if data exists
      if (res?.database_state?.has_data) {
        setExpandedStages((prev) => ({
          ...prev,
          data_reconciliation: true,
          daily_analytics: true,
          intelligence_report: true,
          anomaly_detection: true,
          investigation_handoff: true,
        }));
      }
    } catch (err) {
      if (reqId === statusRequestIdRef.current) {
        console.error('Failed to retrieve pipeline status:', err);
        setStatusError(err.message || 'Unable to load pipeline execution state.');
      }
    } finally {
      if (reqId === statusRequestIdRef.current) {
        setLoadingStatus(false);
      }
    }
  }, [applyAuthoritativePipelineState]);

  // Fetch saved records and master data for plant & date
  const loadSavedRecords = useCallback(async (targetDate = reportingDateRef.current, targetPlant = plantIdRef.current) => {
    const reqId = ++recordsRequestIdRef.current;
    setLoadingSaved(true);
    try {
      const data = await dailyReportsApi.getDailyRecords(targetDate, targetPlant);
      if (
        reqId === recordsRequestIdRef.current &&
        targetDate === reportingDateRef.current &&
        targetPlant === plantIdRef.current
      ) {
        setSavedCounts({
          energy: data.energy_records_count || 0,
          production: data.production_records_count || 0,
        });
        setMasterData(data.master_data || null);
        setEnergyRows(data.energy_records || []);
        setProductionRows(data.production_records || []);
        setValidationResult(null);
      }
    } catch (err) {
      if (reqId === recordsRequestIdRef.current) {
        console.warn('Failed to load saved records:', err);
      }
    } finally {
      if (reqId === recordsRequestIdRef.current) {
        setLoadingSaved(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchStatus(reportingDate, plantId);
    loadSavedRecords(reportingDate, plantId);
  }, [reportingDate, plantId, fetchStatus, loadSavedRecords]);

  // Data Entry: Validate in-place rows against schema, constraints, balances
  const handleValidateEntries = async () => {
    setValidating(true);
    setStatusError(null);
    setActionSuccessMsg(null);
    try {
      const res = await dailyReportsApi.validateDataEntries({
        reporting_date: reportingDate,
        plant_id: plantId,
        energy_rows: energyRows,
        production_rows: productionRows,
        mode: ingestMode,
      });
      setValidationResult(res);
      if (res.valid) {
        setActionSuccessMsg(`Validation passed: ${res.total_valid} entries verified against database schema and constraints.`);
        try {
          await dailyReportsApi.updatePipelineStatus(
            reportingDate,
            'validation',
            'COMPLETED',
            `Data validation passed (${res.total_valid} rows validated against PostgreSQL schema, foreign keys, and balance constraints).`,
            { total_valid_rows: res.total_valid, total_rejected_rows: 0, energy_valid: res.energy_summary?.valid_rows, production_valid: res.production_summary?.valid_rows }
          );
        } catch (uErr) {
          console.warn('Pipeline status update failed:', uErr);
        }
        await fetchStatus(reportingDate, plantId);
      } else {
        setStatusError(`Validation identified ${res.total_errors} issue(s). Please review row highlights.`);
        try {
          await dailyReportsApi.updatePipelineStatus(
            reportingDate,
            'validation',
            'COMPLETED_WITH_WARNINGS',
            `Validation identified ${res.total_errors} issue(s) in entered records.`,
            { total_valid_rows: res.total_valid, total_rejected_rows: res.total_errors, errors: res.errors }
          );
        } catch (uErr) {
          console.warn('Pipeline status update failed:', uErr);
        }
        await fetchStatus(reportingDate, plantId);
      }
    } catch (err) {
      console.error('Validation failed:', err);
      setStatusError(err.message || 'Validation request failed.');
    } finally {
      setValidating(false);
    }
  };

  // Data Entry: Save rows idempotently to Neon PostgreSQL fact tables
  const handleSaveEntries = async (entryType = 'MANUAL', customPayload = null) => {
    setSavingEntries(true);
    setStatusError(null);
    setActionSuccessMsg(null);
    const targetDate = customPayload?.reporting_date || reportingDate;
    const targetPlant = customPayload?.plant_id || plantId;
    try {
      const eRows = customPayload ? (customPayload.energy_rows || []) : energyRows;
      const pRows = customPayload ? (customPayload.production_rows || []) : productionRows;
      const res = await dailyReportsApi.saveDataEntries({
        reporting_date: targetDate,
        plant_id: targetPlant,
        energy_rows: eRows,
        production_rows: pRows,
        entry_type: typeof entryType === 'string' ? entryType : 'MANUAL',
        mode: ingestMode,
      });
      if (res && res.success) {
        setActionSuccessMsg(res.message);
        setValidationResult(null);
        if (targetDate !== reportingDate || targetPlant !== plantId) {
          handleSwitchPlantAndDate(targetPlant, targetDate);
        }
        let reloadFailed = false;
        try {
          await loadSavedRecords(targetDate, targetPlant);
          await fetchStatus(targetDate, targetPlant);
        } catch (rErr) {
          console.warn('Reloading after commit failed:', rErr);
          reloadFailed = true;
        }
        if (reloadFailed) {
          setActionSuccessMsg(`${res.message || 'Entry saved.'} Note: refreshing the record list failed, please refresh.`);
        }
        setExpandedStages((prev) => ({
          ...prev,
          data_upload: false,
          validation: true,
          database_ingestion: true,
        }));
        return { ...res, reloadFailed };
      } else {
        const errMsg = res?.message || 'Failed to save entries to database.';
        setStatusError(errMsg);
        return { success: false, message: errMsg, errors: res?.errors };
      }
    } catch (err) {
      console.error('Save failed:', err);
      const errMsg = err.message || 'Save request failed.';
      setStatusError(errMsg);
      return { success: false, message: errMsg };
    } finally {
      setSavingEntries(false);
    }
  };

  const toggleStage = (stageKey) => {
    setExpandedStages((prev) => ({
      ...prev,
      [stageKey]: !prev[stageKey],
    }));
  };

  // -------------------------------------------------------------------------
  // Explicit Action: Validate & Save (Auto-Ingest for Incremental)
  // -------------------------------------------------------------------------
  const handleValidateAndSave = async () => {
    if (isCommittingRef.current || validating || ingesting) return;
    if (!energyFile && !productionFile) {
      setStatusError('Please select at least one Energy or Production file to validate & save.');
      return;
    }

    isCommittingRef.current = true;
    setValidating(true);
    setStatusError(null);
    setActionSuccessMsg(null);
    setDateMismatch(null);
    setFailedReportType(null);

    let totalValid = 0;
    let totalRejected = 0;
    const validationDetails = {};

    try {
      // 1. Validate only the report types the operator actually supplied
      if (energyFile) {
        const energyRes = await dailyReportsApi.validateReport(energyFile, {
          reportType: 'ENERGY',
          confirmedDate: reportingDate,
          mode: ingestMode,
        });
        validationDetails.energy = energyRes;

        // Check date mismatch: file contents date vs selected reporting date
        const energyDates = energyRes.detected_dates || (energyRes.summary?.detected_date ? [energyRes.summary.detected_date] : []);
        const primaryEnergyDate = energyDates[0] || energyRes.summary?.detected_date;
        if (primaryEnergyDate && primaryEnergyDate !== reportingDate) {
          setDateMismatch({
            fileType: 'Energy',
            selectedDate: reportingDate,
            detectedDate: primaryEnergyDate,
          });
          setStatusError(
            `Reporting date mismatch: Selected reporting date is ${reportingDate}, but Energy file contains readings for ${primaryEnergyDate}. Please align the date before saving.`
          );
          setExpandedStages((prev) => ({ ...prev, data_upload: true, validation: true }));
          setSelectedStage('data_upload');
          return;
        }

        // Check plant scope
        const plantsFound = energyRes.summary?.plants_found || [];
        if (plantsFound.length > 0 && !plantsFound.includes(plantId)) {
          setStatusError(
            `Plant scope mismatch: Energy file contains data for plant ${plantsFound.join(', ')}, but current scope is ${plantId}. Please align plant scope before saving.`
          );
          setExpandedStages((prev) => ({ ...prev, data_upload: true, validation: true }));
          setSelectedStage('data_upload');
          return;
        }

        totalValid += (energyRes.summary?.valid_rows ?? 0);
        totalRejected += (energyRes.summary?.rejected_rows ?? 0);
      }

      if (productionFile) {
        const prodRes = await dailyReportsApi.validateReport(productionFile, {
          reportType: 'PRODUCTION',
          confirmedDate: reportingDate,
          mode: ingestMode,
        });
        validationDetails.production = prodRes;

        // Check date mismatch
        const prodDates = prodRes.detected_dates || (prodRes.summary?.detected_date ? [prodRes.summary.detected_date] : []);
        const primaryProdDate = prodDates[0] || prodRes.summary?.detected_date;
        if (primaryProdDate && primaryProdDate !== reportingDate) {
          setDateMismatch({
            fileType: 'Production',
            selectedDate: reportingDate,
            detectedDate: primaryProdDate,
          });
          setStatusError(
            `Reporting date mismatch: Selected reporting date is ${reportingDate}, but Production file contains readings for ${primaryProdDate}. Please align the date before saving.`
          );
          setExpandedStages((prev) => ({ ...prev, data_upload: true, validation: true }));
          setSelectedStage('data_upload');
          return;
        }

        // Check plant scope
        const prodPlants = prodRes.summary?.plants_found || [];
        if (prodPlants.length > 0 && !prodPlants.includes(plantId)) {
          setStatusError(
            `Plant scope mismatch: Production file contains data for plant ${prodPlants.join(', ')}, but current scope is ${plantId}. Please align plant scope before saving.`
          );
          setExpandedStages((prev) => ({ ...prev, data_upload: true, validation: true }));
          setSelectedStage('data_upload');
          return;
        }

        totalValid += (prodRes.summary?.valid_rows ?? 0);
        totalRejected += (prodRes.summary?.rejected_rows ?? 0);
      }

      // Check formatting or schema warnings
      const hasWarnings = totalRejected > 0;
      const stageStatus = hasWarnings ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED';
      const summaryMsg = `${totalValid} valid rows verified (${totalRejected} rejected).`;

      // Persist validation stage to backend
      const detailsObj = {
        total_valid_rows: totalValid,
        total_rejected_rows: totalRejected,
        files_validated: (energyFile ? 1 : 0) + (productionFile ? 1 : 0),
        has_staged_files: true,
        has_staged_energy: Boolean(energyFile),
        has_staged_production: Boolean(productionFile),
        energy_upload_id: validationDetails.energy?.upload_id,
        production_upload_id: validationDetails.production?.upload_id,
        energy_valid_rows: validationDetails.energy?.summary?.valid_rows || 0,
        production_valid_rows: validationDetails.production?.summary?.valid_rows || 0,
      };

      const updatedStatus = await dailyReportsApi.updatePipelineStatus(
        reportingDate,
        'validation',
        stageStatus,
        summaryMsg,
        detailsObj
      );
      applyAuthoritativePipelineState(updatedStatus, reportingDate, plantId);

      // Require explicit confirmation for OVERWRITE_CORRECTION
      if (ingestMode === 'OVERWRITE_CORRECTION') {
        setExpandedStages((prev) => ({ ...prev, validation: true, database_ingestion: true }));
        setSelectedStage('database_ingestion');
        setActionSuccessMsg(
          'Files validated for OVERWRITE_CORRECTION. Review replacement scope and click "Confirm & Commit Records to Database" below.'
        );
        return;
      }

      // If rejected rows exist, show rejected rows and preserve review path before committing
      if (totalRejected > 0) {
        setExpandedStages((prev) => ({ ...prev, validation: true, database_ingestion: true }));
        setSelectedStage('validation');
        setStatusError(
          `Validation found ${totalRejected} rejected rows. Review the rejected rows in Stage 2 before deciding whether to commit valid records.`
        );
        return;
      }

      // INCREMENTAL mode with 0 rejections: AUTO-SAVE TO POSTGRESQL!
      setValidating(false);
      setIngesting(true);

      const ingestResults = {};
      const ingestedBatches = [];
      let energyCommitted = 0;
      let prodCommitted = 0;

      // Ingest Energy if supplied using fresh validation upload ID directly
      if (energyFile && validationDetails.energy) {
        try {
          const eRes = await dailyReportsApi.ingestReport(energyFile, {
            reportType: 'ENERGY',
            reportingDate,
            plantId,
            uploadId: validationDetails.energy.upload_id,
            mode: 'INCREMENTAL',
          });
          ingestResults.energy = eRes;
          energyCommitted = eRes.imported_rows || 0;
          if (eRes.upload_id) {
            ingestedBatches.push({ type: 'ENERGY', uploadId: eRes.upload_id, count: energyCommitted });
          }
          // Succeeded: clear energyFile from memory
          setEnergyFile(null);
        } catch (eErr) {
          setFailedReportType('ENERGY');
          throw eErr;
        }
      }

      // Ingest Production if supplied using fresh validation upload ID directly
      if (productionFile && validationDetails.production) {
        try {
          const pRes = await dailyReportsApi.ingestReport(productionFile, {
            reportType: 'PRODUCTION',
            reportingDate,
            plantId,
            uploadId: validationDetails.production.upload_id,
            mode: 'INCREMENTAL',
          });
          ingestResults.production = pRes;
          prodCommitted = pRes.imported_rows || 0;
          if (pRes.upload_id) {
            ingestedBatches.push({ type: 'PRODUCTION', uploadId: pRes.upload_id, count: prodCommitted });
          }
          // Succeeded: clear productionFile from memory
          setProductionFile(null);
        } catch (pErr) {
          setFailedReportType('PRODUCTION');
          // If energy succeeded and production failed: retain energy result and allow retry of production
          if (ingestResults.energy) {
            setLastIngestResult({ ...ingestResults });
            await fetchStatus(reportingDate);
            setStatusError(
              `Energy telemetry saved successfully (${ingestResults.energy.imported_rows} new rows, ID: ${ingestResults.energy.upload_id}). Production ingestion failed: ${pErr.message}. You can retry saving the Production file.`
            );
            return;
          }
          throw pErr;
        }
      }

      setLastIngestResult(ingestResults);

      // Refresh persisted pipeline status from backend
      const refreshedState = await dailyReportsApi.getPipelineStatus(reportingDate, plantId);
      applyAuthoritativePipelineState(refreshedState, reportingDate, plantId);

      // Check if duplicate only
      const energyDup = ingestResults.energy && ingestResults.energy.imported_rows === 0 && (ingestResults.energy.duplicate_rows > 0 || ingestResults.energy.total_rows > 0);
      const prodDup = ingestResults.production && ingestResults.production.imported_rows === 0 && (ingestResults.production.duplicate_rows > 0 || ingestResults.production.total_rows > 0);
      const isAllDup = (energyFile ? energyDup : true) && (productionFile ? prodDup : true);

      if (isAllDup && (energyDup || prodDup)) {
        setActionSuccessMsg(
          'Already stored — 0 new rows: all records in the uploaded file(s) already exist in PostgreSQL fact tables. Existing pipeline data reused.'
        );
      } else {
        const batchSummary = ingestedBatches.map((b) => `${b.type}: ${b.count} rows (${b.uploadId})`).join(', ');
        setActionSuccessMsg(
          `Validated & saved successfully! Committed ${energyCommitted} energy and ${prodCommitted} production records to PostgreSQL fact tables. [${batchSummary}]. Phase 4 (Data Reconciliation) is now unlocked.`
        );
      }

      setExpandedStages((prev) => ({
        ...prev,
        database_ingestion: true,
        data_reconciliation: true,
      }));
      setSelectedStage('data_reconciliation');
    } catch (err) {
      console.error('Validation & save error:', err);
      setStatusError(err.message || 'Validation or database ingestion failed.');
      fetchStatus(reportingDate);
    } finally {
      isCommittingRef.current = false;
      setValidating(false);
      setIngesting(false);
    }
  };

  // Wire handleValidateFiles to handleValidateAndSave so all callers resolve to the current Validate & save flow
  const handleValidateFiles = handleValidateAndSave;

  // Stage 3: Explicit Confirm & Ingest (For OVERWRITE_CORRECTION, Retry, or Staged batches)
  const handleConfirmIngest = async () => {
    if (isCommittingRef.current || ingesting) return;

    const validationStage = pipelineState?.stages?.validation;
    const stagedDetails = validationStage?.details;
    const hasMemoryFiles = Boolean(energyFile || productionFile);
    const hasStaged = Boolean(
      stagedDetails && (
        stagedDetails.has_staged_files ||
        stagedDetails.energy_upload_id ||
        stagedDetails.production_upload_id ||
        (validationStage.status !== 'BLOCKED' && validationStage.status !== 'NOT_STARTED' && (stagedDetails.total_valid_rows > 0 || stagedDetails.files_validated > 0))
      )
    );

    if (!hasMemoryFiles && !hasStaged) {
      setStatusError('No validated files available for ingestion. Please upload and validate files in Stage 1 first.');
      return;
    }

    isCommittingRef.current = true;
    setIngesting(true);
    setStatusError(null);
    setActionSuccessMsg(null);
    setFailedReportType(null);

    const ingestedBatches = [];
    const ingestResults = {};
    let energyCommitted = 0;
    let prodCommitted = 0;

    try {
      if (energyFile || stagedDetails?.has_staged_energy || stagedDetails?.energy_upload_id || (!hasMemoryFiles && stagedDetails?.total_valid_rows > 0)) {
        try {
          const res = await dailyReportsApi.ingestReport(energyFile, {
            reportType: 'ENERGY',
            reportingDate,
            plantId,
            uploadId: stagedDetails?.energy_upload_id,
            mode: ingestMode,
          });
          ingestResults.energy = res;
          energyCommitted = res.imported_rows || 0;
          if (res.upload_id) {
            ingestedBatches.push({ type: 'ENERGY', uploadId: res.upload_id, count: energyCommitted });
          }
          setEnergyFile(null);
        } catch (e) {
          if (energyFile || stagedDetails?.has_staged_energy || stagedDetails?.energy_upload_id) {
            setFailedReportType('ENERGY');
            throw e;
          }
        }
      }

      if (productionFile || stagedDetails?.has_staged_production || stagedDetails?.production_upload_id || (!hasMemoryFiles && stagedDetails?.total_valid_rows > 0)) {
        try {
          const res = await dailyReportsApi.ingestReport(productionFile, {
            reportType: 'PRODUCTION',
            reportingDate,
            plantId,
            uploadId: stagedDetails?.production_upload_id,
            mode: ingestMode,
          });
          ingestResults.production = res;
          prodCommitted = res.imported_rows || 0;
          if (res.upload_id) {
            ingestedBatches.push({ type: 'PRODUCTION', uploadId: res.upload_id, count: prodCommitted });
          }
          setProductionFile(null);
        } catch (e) {
          if (productionFile || stagedDetails?.has_staged_production || stagedDetails?.production_upload_id) {
            setFailedReportType('PRODUCTION');
            if (ingestResults.energy) {
              setLastIngestResult({ ...ingestResults });
              await fetchStatus(reportingDate);
              setStatusError(
                `Energy telemetry committed successfully (${ingestResults.energy.imported_rows} new rows, ID: ${ingestResults.energy.upload_id}). Production ingestion failed: ${e.message}. You can retry saving the Production file.`
              );
              return;
            }
            throw e;
          }
        }
      }

      setLastIngestResult(ingestResults);

      const verifiedState = await dailyReportsApi.getPipelineStatus(reportingDate, plantId);
      applyAuthoritativePipelineState(verifiedState, reportingDate, plantId);

      const energyDup = ingestResults.energy && ingestResults.energy.imported_rows === 0 && (ingestResults.energy.duplicate_rows > 0 || ingestResults.energy.total_rows > 0);
      const prodDup = ingestResults.production && ingestResults.production.imported_rows === 0 && (ingestResults.production.duplicate_rows > 0 || ingestResults.production.total_rows > 0);
      const isAllDup = (energyCommitted === 0 && prodCommitted === 0) && (energyDup || prodDup);

      if (isAllDup) {
        setActionSuccessMsg('Already stored — 0 new rows: all records in the uploaded file(s) already exist in PostgreSQL fact tables.');
      } else {
        const batchSummary = ingestedBatches.map((b) => `${b.type}: ${b.count} rows (${b.uploadId})`).join(', ');
        setActionSuccessMsg(
          `Database Ingestion Verified & Completed! Successfully committed ${energyCommitted} energy and ${prodCommitted} production records to PostgreSQL fact tables. [${batchSummary}]. Phase 4 (Data Reconciliation) is now unlocked.`
        );
      }

      setExpandedStages((prev) => ({
        ...prev,
        database_ingestion: true,
        data_reconciliation: true,
      }));
      setSelectedStage('data_reconciliation');
    } catch (err) {
      console.error('Ingestion error:', err);
      setStatusError(err.message || 'Failed to ingest records into database.');
      fetchStatus(reportingDate, plantId);
    } finally {
      isCommittingRef.current = false;
      setIngesting(false);
    }
  };

  const handleRetryFailedFile = () => {
    if (failedReportType === 'PRODUCTION' && productionFile) {
      handleValidateAndSave();
    } else if (failedReportType === 'ENERGY' && energyFile) {
      handleValidateAndSave();
    } else {
      handleConfirmIngest();
    }
  };

  // Stages 4-8: Execute Downstream Pipeline (Recon, Analytics, Report, Anomalies, Handoff)
  const handleRunDownstream = async () => {
    const activeDate = reportingDateRef.current;
    const activePlant = plantIdRef.current;
    const reqId = ++statusRequestIdRef.current;
    setRunningDownstream(true);
    setStatusError(null);
    try {
      const updated = await dailyReportsApi.runDownstreamPipeline(activeDate, activePlant);
      if (
        reqId === statusRequestIdRef.current &&
        activeDate === reportingDateRef.current &&
        activePlant === plantIdRef.current
      ) {
        applyAuthoritativePipelineState(updated, activeDate, activePlant);
        setExpandedStages({
          data_upload: false,
          validation: false,
          database_ingestion: false,
          data_reconciliation: true,
          daily_analytics: true,
          intelligence_report: true,
          anomaly_detection: true,
          investigation_handoff: true,
        });
        setActionSuccessMsg('Daily Operations downstream processing completed successfully.');
      }
    } catch (err) {
      console.error('Downstream pipeline execution failed:', err);
      setStatusError(err.message || 'Downstream processing failed.');
      fetchStatus(activeDate, activePlant);
    } finally {
      setRunningDownstream(false);
    }
  };

  // Sync Anomalies to Findings Centre
  const handleSyncFindings = async () => {
    if (syncingFindings) return;
    setSyncingFindings(true);
    setStatusError(null);
    const activeDate = reportingDateRef.current;
    const activePlant = plantIdRef.current;
    try {
      const payload = {
        plant_id: activePlant,
        start_time: `${activeDate}T00:00:00`,
        end_time: `${activeDate}T23:59:59`,
        caller_attribution: 'Daily Operations Pipeline',
      };
      const syncResult = await findingsApi.syncFindings(payload);

      // Keep completed Stage 8 result visible while a separate sync is running
      const currentHandoff = pipelineState?.stages?.investigation_handoff;
      const currentDetails = currentHandoff?.details || {};
      const newItemsPrep = syncResult?.total_anomalies_evaluated ?? currentDetails.items_prepared_count ?? 0;
      const newFindingsSync = (syncResult?.occurrences_recorded ?? 0) + (syncResult?.duplicates_ignored ?? 0);
      const newFindings = syncResult?.new_findings_created ?? 0;
      const reusedFindings = (syncResult?.existing_findings_updated ?? 0) + (syncResult?.duplicates_ignored ?? 0);

      const updatedHandoffDetails = {
        ...currentDetails,
        total_items: newItemsPrep,
        items_prepared_count: newItemsPrep,
        findings_synchronized_count: newFindingsSync,
        new_findings_count: newFindings,
        reused_findings_count: reusedFindings,
      };

      const updatedSummary = `Prepared ${newItemsPrep} anomaly investigation items (${newFindings} newly created findings, ${reusedFindings} existing/reused findings synchronized in database).`;

      // Preserve completed Stage 8 in local pipelineState so it stays visibly COMPLETED during sync
      setPipelineState((prev) => {
        if (!prev) return prev;
        const prevStages = prev.stages || {};
        return {
          ...prev,
          stages: {
            ...prevStages,
            investigation_handoff: {
              ...(prevStages.investigation_handoff || {}),
              status: prevStages.investigation_handoff?.status || 'COMPLETED',
              summary: updatedSummary,
              details: updatedHandoffDetails,
            },
          },
        };
      });

      try {
        await dailyReportsApi.updatePipelineStatus(
          activeDate,
          'investigation_handoff',
          'COMPLETED',
          updatedSummary,
          updatedHandoffDetails
        );
      } catch (updateErr) {
        console.warn('Failed to update pipeline stage status for handoff:', updateErr);
      }

      setActionSuccessMsg(
        `Anomalies synchronized with Findings Centre (${newFindings} new findings created, ${syncResult?.existing_findings_updated || 0} updated, ${syncResult?.occurrences_recorded || 0} occurrences recorded).`
      );
      await fetchStatus(activeDate, activePlant);
    } catch (err) {
      console.error('Failed to sync findings:', err);
      setStatusError(err.message || 'Failed to synchronize findings.');
    } finally {
      // Clear syncingFindings when the sync request settles, including on error
      setSyncingFindings(false);
    }
  };

  return (
    <div className="dashboard-container daily-ops-container">
      {/* Single-Line Modern Toolbar Header */}
      <motion.header
        className="daily-ops-header-card"
        role="banner"
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
      >
        <div className="daily-ops-controls-row" role="toolbar" aria-label="Daily Operations Controls">
          <div className="daily-ops-controls-left">
            {/* 1. Reporting Date */}
          <div className="daily-ops-control-item daily-ops-date-item">
            <div className="daily-ops-input-wrap">
              <input
                id="daily-ops-date"
                type="date"
                className="daily-ops-date-input"
                value={reportingDate}
                onChange={(e) => handleDateChange(e.target.value)}
                min="2026-01-01"
                max="2030-12-31"
                aria-label="Select Daily Operations Reporting Date"
              />
            </div>
          </div>

          {/* 2. Plant Selector */}
          <div className="daily-ops-control-item daily-ops-plant-item">
            <div className="daily-ops-select-wrap">
              <select
                id="daily-ops-plant"
                className="daily-ops-date-input daily-ops-select-input"
                value={plantId}
                onChange={(e) => {
                  const newPlant = e.target.value;
                  plantIdRef.current = newPlant;
                  setPlantId(newPlant);
                  setStatusError(null);
                  setActionSuccessMsg(null);
                  setSavedCounts(null);
                  setLoadingSaved(true);
                }}
                aria-label="Select Target Plant"
              >
                <option value="IN-TN-01">IN-TN-01 (Tamil Nadu Electronics Assembly)</option>
                <option value="IN-KA-01">IN-KA-01 (Karnataka Plant)</option>
              </select>
              <span className="daily-ops-select-chevron" aria-hidden="true">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </span>
            </div>
          </div>
        </div>

        {/* Action Buttons Group on the Right */}
          <div className="daily-ops-actions-group">
            {/* 3. Refresh Status Action Button */}
            <div className="daily-ops-action-item">
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary"
                onClick={() => fetchStatus(reportingDate, plantId)}
                disabled={loadingStatus}
                title="Refresh telemetry and pipeline execution status"
                aria-label="Refresh Status"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  className={loadingStatus ? 'spin-icon' : ''}
                >
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.19" />
                </svg>
                <span>{loadingStatus ? 'Refreshing…' : 'Refresh'}</span>
              </button>
            </div>

            {/* 4. Run Downstream Pipeline Action Button */}
            <div className="daily-ops-action-item">
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-primary"
                onClick={handleRunDownstream}
                disabled={runningDownstream || !pipelineState?.database_state?.has_data}
                title={
                  !pipelineState?.database_state?.has_data
                    ? 'Database records required before running downstream stages'
                    : 'Execute Reconciliation, Analytics, Report, Anomalies, and Investigation Handoff'
                }
                aria-label="Run pipeline"
              >
                {runningDownstream ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="spin-icon">
                      <line x1="12" y1="2" x2="12" y2="6" />
                      <line x1="12" y1="18" x2="12" y2="22" />
                      <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
                      <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
                      <line x1="2" y1="12" x2="6" y2="12" />
                      <line x1="18" y1="12" x2="22" y2="12" />
                    </svg>
                    <span>Running…</span>
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                    <span>Run pipeline</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Global Notifications */}
        {actionSuccessMsg && (
          <div className="daily-ops-alert-banner info" role="status">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <span>{actionSuccessMsg}</span>
          </div>
        )}
        {statusError && (
          <div className="daily-ops-alert-banner error" role="alert">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{statusError}</span>
          </div>
        )}
      </motion.header>

      {/* Main 8-Stage Horizontal Pipeline Stepper */}
      <DailyOperationsPipeline
        pipelineState={pipelineState}
        selectedStage={selectedStage}
        onSelectStage={setSelectedStage}
        expandedStages={expandedStages}
        toggleStage={toggleStage}
        reportingDate={reportingDate}
        plantId={plantId}
        onSwitchPlantAndDate={handleSwitchPlantAndDate}
        // Data Entry props
        energyRows={energyRows}
        setEnergyRows={setEnergyRows}
        productionRows={productionRows}
        setProductionRows={setProductionRows}
        masterData={masterData}
        savedCounts={savedCounts}
        loadingSaved={loadingSaved}
        validationResult={validationResult}
        validating={validating}
        savingEntries={savingEntries}
        onValidateEntries={handleValidateEntries}
        onSaveEntries={handleSaveEntries}
        onReloadRecords={() => loadSavedRecords(reportingDate, plantId)}
        // Legacy file & ingestion props
        energyFiles={energyFile}
        productionFiles={productionFile}
        handleEnergyFileSelect={setEnergyFile}
        handleProductionFileSelect={setProductionFile}
        handleValidateFiles={handleValidateAndSave}
        handleValidateAndSave={handleValidateAndSave}
        ingesting={ingesting}
        handleConfirmIngest={handleConfirmIngest}
        ingestMode={ingestMode}
        setIngestMode={setIngestMode}
        dateMismatch={dateMismatch}
        handleSwitchDate={handleSwitchDate}
        lastIngestResult={lastIngestResult}
        failedReportType={failedReportType}
        handleRetryFailedFile={handleRetryFailedFile}
        runningDownstream={runningDownstream}
        handleRunDownstream={handleRunDownstream}
        handleSyncFindings={handleSyncFindings}
        syncingFindings={syncingFindings}
      />

      {/* Modal / Drawer for Upload History Audit Log */}
      {showHistoryModal && (
        <div className="reports-modal-overlay" onClick={() => setShowHistoryModal(false)}>
          <div
            className="reports-modal-card"
            style={{ maxWidth: '960px', width: '92%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="reports-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="reports-card-title">Daily Reports Ingestion History & Audit Log</h3>
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary"
                onClick={() => setShowHistoryModal(false)}
              >
                Close
              </button>
            </div>
            <div style={{ marginTop: '1rem' }}>
              <UploadHistorySection key="upload-history-drawer" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
