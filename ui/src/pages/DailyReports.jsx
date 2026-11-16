import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
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

  // Sync date changes with URL and reset uncommitted file buffers
  const handleDateChange = (newDate) => {
    setReportingDate(newDate);
    setEnergyFile(null);
    setProductionFile(null);
    setStatusError(null);
    setActionSuccessMsg(null);
    setSearchParams({ date: newDate });
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

  // Stage 2: Validate Files
  const handleValidateFiles = async () => {
    if (!energyFile && !productionFile) {
      alert('Please select at least one Energy or Production file to validate.');
      return;
    }

    setValidating(true);
    setStatusError(null);
    setActionSuccessMsg(null);

    let totalValid = 0;
    let totalRejected = 0;
    const validationDetails = {};

    try {
      if (energyFile) {
        const energyRes = await dailyReportsApi.validateReport(energyFile, {
          reportType: 'ENERGY',
          confirmedDate: reportingDate,
          mode: ingestMode,
        });
        validationDetails.energy = energyRes;
        totalValid += energyRes.valid_rows_count || 0;
        totalRejected += energyRes.rejected_rows_count || 0;
      }

      if (productionFile) {
        const prodRes = await dailyReportsApi.validateReport(productionFile, {
          reportType: 'PRODUCTION',
          confirmedDate: reportingDate,
          mode: ingestMode,
        });
        validationDetails.production = prodRes;
        totalValid += prodRes.valid_rows_count || 0;
        totalRejected += prodRes.rejected_rows_count || 0;
      }

      const hasWarnings = totalRejected > 0;
      const stageStatus = hasWarnings ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED';
      const summaryMsg = `${totalValid} valid rows verified (${totalRejected} rejected).`;

      // Persist validation stage to backend
      const updatedStatus = await dailyReportsApi.updatePipelineStatus(
        reportingDate,
        'validation',
        stageStatus,
        summaryMsg
      );
      setPipelineState(updatedStatus);
      setExpandedStages((prev) => ({ ...prev, validation: true, database_ingestion: true }));
      setActionSuccessMsg('Files validated successfully. Review and confirm ingestion.');
    } catch (err) {
      console.error('Validation error:', err);
      setStatusError(err.message || 'File validation failed.');
      await dailyReportsApi.updatePipelineStatus(
        reportingDate,
        'validation',
        'FAILED',
        err.message || 'Validation rejected due to format/constraint violations.'
      );
      fetchStatus(reportingDate);
    } finally {
      setValidating(false);
    }
  };

  // Stage 3: Confirm & Ingest Records into PostgreSQL
  const handleConfirmIngest = async () => {
    if (!energyFile && !productionFile) {
      alert('No validated files available for ingestion.');
      return;
    }

    setIngesting(true);
    setStatusError(null);
    setActionSuccessMsg(null);

    let energyCommitted = 0;
    let prodCommitted = 0;

    try {
      if (energyFile) {
        const res = await dailyReportsApi.ingestReport(energyFile, {
          reportType: 'ENERGY',
          reportingDate,
          mode: ingestMode,
        });
        energyCommitted = res.imported_rows || 0;
      }

      if (productionFile) {
        const res = await dailyReportsApi.ingestReport(productionFile, {
          reportType: 'PRODUCTION',
          reportingDate,
          mode: ingestMode,
        });
        prodCommitted = res.imported_rows || 0;
      }

      setActionSuccessMsg(
        `Successfully committed ${energyCommitted} energy and ${prodCommitted} production records to PostgreSQL. Auto-initiating downstream pipeline...`
      );

      // Auto-trigger downstream processing pipeline
      await handleRunDownstream();
    } catch (err) {
      console.error('Ingestion error:', err);
      setStatusError(err.message || 'Failed to ingest records into database.');
      fetchStatus(reportingDate);
    } finally {
      setIngesting(false);
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
    setSyncingFindings(true);
    try {
      await findingsApi.syncFromAnomalies({
        plant_id: plantId,
        start_time: `${reportingDate}T00:00:00`,
        end_time: `${reportingDate}T23:59:59`,
        caller_attribution: 'Daily Operations Pipeline',
      });
      setActionSuccessMsg('Anomalies synchronized with Findings Centre without duplication.');
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
      {/* Top Header Card */}
      <div className="daily-ops-header-card">
        <div className="daily-ops-header-top">
          <div className="daily-ops-title-group">
            <span className="daily-ops-badge">Daily Operations Pipeline</span>
            <h1 className="daily-ops-title">Daily Operations Intelligence Pipeline</h1>
            <p className="daily-ops-subtitle">
              Unified operational control for factory telemetry: file ingestion, schema validation, cross-source reconciliation, deterministic analytics, executive briefing, anomaly surveillance, and investigation handoff.
            </p>
          </div>

          <div className="daily-ops-actions-group">
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary"
              onClick={() => dailyReportsApi.downloadTemplate('energy')}
              title="Download Energy CSV Template"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Energy Template
            </button>
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary"
              onClick={() => dailyReportsApi.downloadTemplate('production')}
              title="Download Production CSV Template"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Production Template
            </button>
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary"
              onClick={() => setShowHistoryModal((v) => !v)}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              Upload History
            </button>
          </div>
        </div>

        {/* Date Selection and Pipeline Execution Controls */}
        <div className="daily-ops-controls-row">
          <div className="daily-ops-date-picker-group">
            <label className="daily-ops-label" htmlFor="daily-ops-date">
              Reporting Date:
            </label>
            <input
              id="daily-ops-date"
              type="date"
              className="daily-ops-date-input"
              value={reportingDate}
              onChange={(e) => handleDateChange(e.target.value)}
              min="2026-01-01"
              max="2030-12-31"
            />
            <span className="daily-ops-label" style={{ marginLeft: '0.75rem' }}>
              Plant:
            </span>
            <select
              className="daily-ops-date-input"
              value={plantId}
              onChange={(e) => setPlantId(e.target.value)}
            >
              <option value="IN-TN-01">IN-TN-01 (Tamil Nadu Electronics Assembly)</option>
              <option value="IN-KA-01">IN-KA-01 (Karnataka Plant)</option>
            </select>
          </div>

          <div className="daily-ops-actions-group">
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary"
              onClick={() => fetchStatus(reportingDate)}
              disabled={loadingStatus}
            >
              Refresh Status
            </button>
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
            >
              {runningDownstream ? 'Processing Pipeline...' : 'Run Downstream Pipeline'}
            </button>
          </div>
        </div>

        {/* Global Notifications */}
        {actionSuccessMsg && (
          <div className="daily-ops-alert-banner info" style={{ marginTop: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <span>{actionSuccessMsg}</span>
          </div>
        )}
        {statusError && (
          <div className="daily-ops-alert-banner error" style={{ marginTop: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{statusError}</span>
          </div>
        )}
      </div>

      {/* Main 8-Stage Vertical Stepper */}
      <DailyOperationsPipeline
        pipelineState={pipelineState}
        expandedStages={expandedStages}
        toggleStage={toggleStage}
        reportingDate={reportingDate}
        plantId={plantId}
        energyFiles={energyFile}
        productionFiles={productionFile}
        handleEnergyFileSelect={setEnergyFile}
        handleProductionFileSelect={setProductionFile}
        validating={validating}
        handleValidateFiles={handleValidateFiles}
        ingesting={ingesting}
        handleConfirmIngest={handleConfirmIngest}
        ingestMode={ingestMode}
        setIngestMode={setIngestMode}
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
