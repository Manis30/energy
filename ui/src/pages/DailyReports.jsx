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

  // Date mismatch and persistence result states
  const [dateMismatch, setDateMismatch] = useState(null);
  const [lastIngestResult, setLastIngestResult] = useState(null);
  const [failedReportType, setFailedReportType] = useState(null);

  // Active selected stage for single-panel horizontal stepper view
  const [selectedStage, setSelectedStage] = useState('data_upload');

  // Sync date changes with URL and reset uncommitted file buffers
  const handleDateChange = (newDate) => {
    setReportingDate(newDate);
    setSelectedStage('data_upload');
    setEnergyFile(null);
    setProductionFile(null);
    setStatusError(null);
    setActionSuccessMsg(null);
    setDateMismatch(null);
    setLastIngestResult(null);
    setFailedReportType(null);
    setSearchParams({ date: newDate });
  };

  const handleSwitchDate = (newDate) => {
    setDateMismatch(null);
    handleDateChange(newDate);
  };

  // Fetch Authoritative Pipeline State from Backend
  const fetchStatus = useCallback(async (targetDate = reportingDate) => {
    setLoadingStatus(true);
    setStatusError(null);
    try {
      const res = await dailyReportsApi.getPipelineStatus(targetDate, plantId);
      setPipelineState(res);

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
      console.error('Failed to retrieve pipeline status:', err);
      setStatusError(err.message || 'Unable to load pipeline execution state.');
    } finally {
      setLoadingStatus(false);
    }
  }, [reportingDate, plantId]);

  useEffect(() => {
    fetchStatus(reportingDate);
  }, [reportingDate, fetchStatus]);

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
      setPipelineState(updatedStatus);

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
      setPipelineState(refreshedState);

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
      setPipelineState(verifiedState);

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
      fetchStatus(reportingDate);
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
    setRunningDownstream(true);
    setStatusError(null);
    try {
      const updated = await dailyReportsApi.runDownstreamPipeline(reportingDate, plantId);
      setPipelineState(updated);
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
    } catch (err) {
      console.error('Downstream pipeline execution failed:', err);
      setStatusError(err.message || 'Downstream processing failed.');
      fetchStatus(reportingDate);
    } finally {
      setRunningDownstream(false);
    }
  };

  // Sync Anomalies to Findings Centre
  const handleSyncFindings = async () => {
    if (syncingFindings) return;
    setSyncingFindings(true);
    setStatusError(null);
    try {
      const payload = {
        plant_id: plantId,
        start_time: `${reportingDate}T00:00:00`,
        end_time: `${reportingDate}T23:59:59`,
        caller_attribution: 'Daily Operations Pipeline',
      };
      const syncResult = await findingsApi.syncFindings(payload);

      // Refresh handoff counts in pipeline stage state
      const currentHandoff = pipelineState?.stages?.investigation_handoff;
      const currentDetails = currentHandoff?.details || {};
      const newItemsPrep = syncResult.total_anomalies_evaluated ?? currentDetails.items_prepared_count ?? 0;
      const newFindingsSync = (syncResult.occurrences_recorded ?? 0) + (syncResult.duplicates_ignored ?? 0);
      const newFindings = syncResult.new_findings_created ?? 0;
      const reusedFindings = (syncResult.existing_findings_updated ?? 0) + (syncResult.duplicates_ignored ?? 0);

      const updatedHandoffDetails = {
        ...currentDetails,
        total_items: newItemsPrep,
        items_prepared_count: newItemsPrep,
        findings_synchronized_count: newFindingsSync,
        new_findings_count: newFindings,
        reused_findings_count: reusedFindings,
      };

      const updatedSummary = `Prepared ${newItemsPrep} anomaly investigation items (${newFindings} newly created findings, ${reusedFindings} existing/reused findings synchronized in database).`;

      try {
        await dailyReportsApi.updatePipelineStatus(
          reportingDate,
          'investigation_handoff',
          'COMPLETED',
          updatedSummary,
          updatedHandoffDetails
        );
      } catch (updateErr) {
        console.warn('Failed to update pipeline stage status for handoff:', updateErr);
      }

      setActionSuccessMsg(
        `Anomalies synchronized with Findings Centre (${newFindings} new findings created, ${syncResult.existing_findings_updated || 0} updated, ${syncResult.occurrences_recorded || 0} occurrences recorded).`
      );
      await fetchStatus(reportingDate);
    } catch (err) {
      console.error('Failed to sync findings:', err);
      setStatusError(err.message || 'Failed to synchronize findings.');
    } finally {
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
          {/* 1. Reporting Date */}
          <div className="daily-ops-control-item daily-ops-date-item">
            <label className="daily-ops-label" htmlFor="daily-ops-date">
              Reporting Date
            </label>
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
            <label className="daily-ops-label" htmlFor="daily-ops-plant">
              Plant
            </label>
            <div className="daily-ops-select-wrap">
              <select
                id="daily-ops-plant"
                className="daily-ops-date-input daily-ops-select-input"
                value={plantId}
                onChange={(e) => setPlantId(e.target.value)}
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

          {/* 3. Refresh Status Action Button */}
          <div className="daily-ops-action-item">
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary"
              onClick={() => fetchStatus(reportingDate)}
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
              <span>{loadingStatus ? 'Refreshing…' : 'Refresh Status'}</span>
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
              aria-label="Run Downstream Pipeline"
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
                  <span>Processing Pipeline…</span>
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span>Run Downstream Pipeline</span>
                </>
              )}
            </button>
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
        energyFiles={energyFile}
        productionFiles={productionFile}
        handleEnergyFileSelect={setEnergyFile}
        handleProductionFileSelect={setProductionFile}
        validating={validating}
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
