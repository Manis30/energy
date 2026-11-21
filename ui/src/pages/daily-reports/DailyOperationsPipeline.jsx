import React, { useRef, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { formatCurrency, formatNumber } from '../../utils/formatters';

const STAGE_TITLES = {
  data_upload: 'Data Upload',
  validation: 'Validation',
  database_ingestion: 'Database Ingestion',
  data_reconciliation: 'Data Reconciliation',
  daily_analytics: 'Daily Analytics',
  intelligence_report: 'Intelligence Report',
  anomaly_detection: 'Anomaly Detection',
  investigation_handoff: 'Investigation Handoff',
};

const STAGE_KEYS = [
  'data_upload',
  'validation',
  'database_ingestion',
  'data_reconciliation',
  'daily_analytics',
  'intelligence_report',
  'anomaly_detection',
  'investigation_handoff',
];

export default function DailyOperationsPipeline({
  pipelineState,
  selectedStage: externalSelectedStage,
  onSelectStage: externalOnSelectStage,
  expandedStages,
  toggleStage,
  reportingDate,
  plantId,
  // Upload & File states
  energyFiles,
  productionFiles,
  handleEnergyFileSelect,
  handleProductionFileSelect,
  // Action handlers
  validating,
  handleValidateFiles,
  handleValidateAndSave,
  ingesting,
  handleConfirmIngest,
  ingestMode,
  setIngestMode,
  dateMismatch,
  handleSwitchDate,
  lastIngestResult,
  failedReportType,
  handleRetryFailedFile,
  runningDownstream,
  handleRunDownstream,
  handleSyncFindings,
  syncingFindings,
}) {
  const navigate = useNavigate();
  const [internalSelectedStage, setInternalSelectedStage] = useState('data_upload');
  const selectedStageKey = externalSelectedStage || internalSelectedStage;
  const stepRefs = useRef({});

  // Opportunities to Review state
  const [opportunities, setOpportunities] = useState([]);
  const [loadingOpportunities, setLoadingOpportunities] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (!plantId || !reportingDate) return;

    setLoadingOpportunities(true);
    fetch(`/api/daily-reports/opportunities?reporting_date=${reportingDate}&plant_id=${plantId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (isMounted) {
          setOpportunities(data?.opportunities || []);
          setLoadingOpportunities(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.warn('Failed to load opportunities to review:', err);
          setOpportunities([]);
          setLoadingOpportunities(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [plantId, reportingDate, pipelineState]);

  const handleSelectStage = (key) => {
    if (externalOnSelectStage) {
      externalOnSelectStage(key);
    }
    setInternalSelectedStage(key);
    toggleStage?.(key);
  };

  // Bring selected marker smoothly into view on narrow viewports
  useEffect(() => {
    const el = stepRefs.current[selectedStageKey];
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'center',
      });
    }
  }, [selectedStageKey]);

  const selectedIndex = Math.max(0, STAGE_KEYS.indexOf(selectedStageKey));

  const handlePrevStage = () => {
    if (selectedIndex > 0) {
      handleSelectStage(STAGE_KEYS[selectedIndex - 1]);
    }
  };

  const handleNextStage = () => {
    if (selectedIndex < STAGE_KEYS.length - 1) {
      handleSelectStage(STAGE_KEYS[selectedIndex + 1]);
    }
  };

  const stages = pipelineState?.stages || {};
  const completedCount = STAGE_KEYS.filter(
    (k) => stages[k]?.status === 'COMPLETED' || stages[k]?.status === 'COMPLETED_WITH_WARNINGS'
  ).length;
  const progressPercent = Math.round((completedCount / STAGE_KEYS.length) * 100);
  const onValidate = handleValidateAndSave || handleValidateFiles;
  const selectedStageObj = stages[selectedStageKey] || {
    status: 'NOT_STARTED',
    summary: 'Pending stage initialization',
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'COMPLETED':
        return <span className="daily-ops-status-badge completed">Completed</span>;
      case 'COMPLETED_WITH_WARNINGS':
        return <span className="daily-ops-status-badge warning">Completed with warnings</span>;
      case 'IN_PROGRESS':
        return <span className="daily-ops-status-badge in-progress">In progress</span>;
      case 'FAILED':
        return <span className="daily-ops-status-badge failed">Failed</span>;
      case 'BLOCKED':
        return <span className="daily-ops-status-badge blocked">Blocked</span>;
      default:
        return <span className="daily-ops-status-badge not-started">Not started</span>;
    }
  };

  const getNodeIcon = (status, idx) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        );
      case 'COMPLETED_WITH_WARNINGS':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        );
      case 'IN_PROGRESS':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="spin-icon" aria-hidden="true">
            <line x1="12" y1="2" x2="12" y2="6" />
            <line x1="12" y1="18" x2="12" y2="22" />
            <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
            <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
            <line x1="2" y1="12" x2="6" y2="12" />
            <line x1="18" y1="12" x2="22" y2="12" />
          </svg>
        );
      case 'FAILED':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        );
      case 'BLOCKED':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        );
      default:
        return <span>{idx + 1}</span>;
    }
  };

  const getNodeClass = (status) => {
    switch (status) {
      case 'COMPLETED':
        return 'completed';
      case 'COMPLETED_WITH_WARNINGS':
        return 'warning';
      case 'IN_PROGRESS':
        return 'in-progress';
      case 'FAILED':
        return 'failed';
      case 'BLOCKED':
        return 'blocked';
      default:
        return 'not-started';
    }
  };

  const getConnectorClass = (currentStatus, nextStatus) => {
    if (
      (currentStatus === 'COMPLETED' || currentStatus === 'COMPLETED_WITH_WARNINGS') &&
      (nextStatus === 'COMPLETED' || nextStatus === 'COMPLETED_WITH_WARNINGS' || nextStatus === 'IN_PROGRESS')
    ) {
      return currentStatus === 'COMPLETED_WITH_WARNINGS' ? 'warning' : 'completed';
    }
    if (currentStatus === 'IN_PROGRESS') {
      return 'in-progress';
    }
    if (currentStatus === 'COMPLETED') {
      return 'completed';
    }
    return '';
  };

  return (
    <div className="daily-ops-horizontal-pipeline-wrapper">
      {/* 1. Horizontal Pipeline Stepper Card */}
      <div className="daily-ops-stepper-card">
        <div className="daily-ops-stepper-header">
          <div className="daily-ops-stepper-title-area">
            <h3 className="daily-ops-stepper-heading">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              <span>8-Stage Operational Pipeline</span>
            </h3>
            <p className="daily-ops-stepper-subheading">
              Authoritative telemetry intake, deterministic reconciliation, and anomaly detection
            </p>
          </div>

          <div className="daily-ops-stepper-meta">
            <div className="daily-ops-progress-text">
              <strong>{completedCount} of 8</strong> Stages Completed
            </div>
            <div className="daily-ops-progress-bar-bg" title={`${progressPercent}% completed`}>
              <div
                className="daily-ops-progress-bar-fill"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Scrollable Horizontal Stepper Track */}
        <div className="daily-ops-horizontal-scroll">
          <div className="daily-ops-horizontal-stepper" role="tablist" aria-label="Pipeline Stages">
            {STAGE_KEYS.map((key, idx) => {
              const stage = stages[key] || { status: 'NOT_STARTED', summary: 'Pending initialization' };
              const isSelected = selectedStageKey === key;
              const isCurrent = pipelineState?.current_stage === key;
              const isLast = idx === STAGE_KEYS.length - 1;
              const nextStatus = !isLast ? stages[STAGE_KEYS[idx + 1]]?.status : null;

              return (
                <div
                  key={key}
                  ref={(el) => (stepRefs.current[key] = el)}
                  role="tab"
                  aria-selected={isSelected}
                  aria-controls={`stage-panel-${key}`}
                  tabIndex={0}
                  className={`daily-ops-h-step ${isSelected ? 'selected' : ''} ${isCurrent ? 'current-step' : ''}`}
                  onClick={() => handleSelectStage(key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleSelectStage(key);
                    }
                  }}
                  title={`Stage ${idx + 1}: ${STAGE_TITLES[key]} (${stage.status})`}
                >
                  <div className="daily-ops-h-node-wrapper">
                    {!isLast && (
                      <div
                        className={`daily-ops-h-connector ${getConnectorClass(stage.status, nextStatus)}`}
                      />
                    )}
                    <div className={`daily-ops-h-node ${getNodeClass(stage.status)}`}>
                      {getNodeIcon(stage.status, idx)}
                    </div>
                  </div>

                  <div className="daily-ops-h-label-group">
                    <span className="daily-ops-h-index">Stage {idx + 1}</span>
                    <span className="daily-ops-h-title">{STAGE_TITLES[key]}</span>
                    <div className="daily-ops-h-status-tag">
                      {getStatusBadge(stage.status)}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 2. Active Stage Detail Panel */}
      <div
        className="daily-ops-stage-detail-panel"
        id={`stage-panel-${selectedStageKey}`}
        role="tabpanel"
        aria-labelledby={`stage-tab-${selectedStageKey}`}
      >
        <div className="daily-ops-detail-header">
          <div className="daily-ops-detail-header-left">
            <div className="daily-ops-detail-title-row">
              <span className="daily-ops-phase-chip">Stage {selectedIndex + 1} of 8</span>
              <h3 className="daily-ops-detail-title">{`${selectedIndex + 1}. ${STAGE_TITLES[selectedStageKey]}`}</h3>
              {getStatusBadge(selectedStageObj.status)}
              {pipelineState?.current_stage === selectedStageKey && (
                <span className="daily-ops-active-chip">Active</span>
              )}
            </div>
            <p className="daily-ops-detail-summary">{selectedStageObj.summary || 'Pending stage execution'}</p>
          </div>

          <div className="daily-ops-detail-header-right">
            {selectedStageObj.timestamp && (
              <span className="daily-ops-detail-timestamp">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                {new Date(selectedStageObj.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            )}
            <div className="daily-ops-detail-nav-group">
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary daily-ops-btn-sm"
                onClick={handlePrevStage}
                disabled={selectedIndex === 0}
                aria-label="Previous Stage"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
                <span>Previous Stage</span>
              </button>
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary daily-ops-btn-sm"
                onClick={handleNextStage}
                disabled={selectedIndex === STAGE_KEYS.length - 1}
                aria-label="Next Stage"
              >
                <span>Next Stage</span>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Animated Single Panel Detail Body */}
        <AnimatePresence mode="wait">
          <motion.div
            key={selectedStageKey}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16, ease: 'easeOut' }}
            className="daily-ops-detail-body"
          >
            {/* FAILED STATE RECOVERY BOX */}
            {selectedStageObj.status === 'FAILED' && (
              <div className="daily-ops-recovery-box">
                <div>
                  <strong>Execution Error:</strong> {selectedStageObj.summary}
                </div>
                <button
                  type="button"
                  className="daily-ops-btn daily-ops-btn-primary"
                  onClick={() => {
                    if (selectedStageKey === 'validation') onValidate?.();
                    else if (selectedStageKey === 'database_ingestion') handleConfirmIngest?.();
                    else handleRunDownstream?.();
                  }}
                >
                  Retry Stage
                </button>
              </div>
            )}

            {/* BLOCKED STATE RECOVERY BOX */}
            {selectedStageObj.status === 'BLOCKED' && (
              <div
                className="daily-ops-recovery-box"
                style={{ borderColor: 'var(--accent-orange, #f59e0b)', background: 'rgba(245, 158, 11, 0.08)' }}
              >
                <div>
                  <strong>Stage Blocked:</strong> {selectedStageObj.summary}
                </div>
                <button
                  type="button"
                  className="daily-ops-btn daily-ops-btn-secondary"
                  onClick={() => {
                    if (selectedStageKey === 'investigation_handoff') {
                      handleSelectStage('anomaly_detection');
                    }
                  }}
                >
                  Review Anomaly Detection
                </button>
              </div>
            )}

            {/* STAGE 1: DATA UPLOAD */}
            {selectedStageKey === 'data_upload' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {selectedStageObj.details?.is_historical_baseline && (
                  <div className="daily-ops-alert-banner info">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="16" x2="12" y2="12" />
                      <line x1="12" y1="8" x2="12.01" y2="8" />
                    </svg>
                    <span>
                      <strong>Historical Telemetry Baseline:</strong> Fact records exist in PostgreSQL for {reportingDate}. You may upload new files below to perform an incremental or overwrite ingestion, or execute downstream pipeline stages directly on baseline data.
                    </span>
                  </div>
                )}

                {dateMismatch && (
                  <div className="daily-ops-alert-banner warning">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <span>
                        <strong>Date Mismatch:</strong> {dateMismatch.fileType} file contains data for <strong>{dateMismatch.detectedDate}</strong>, but current reporting date is <strong>{dateMismatch.selectedDate}</strong>.
                      </span>
                      {handleSwitchDate && (
                        <button
                          type="button"
                          className="daily-ops-btn daily-ops-btn-secondary"
                          style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}
                          onClick={() => handleSwitchDate(dateMismatch.detectedDate)}
                        >
                          Switch to {dateMismatch.detectedDate}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {selectedStageObj.details?.has_linked_uploads && selectedStageObj.details?.files?.length > 0 && (
                  <div className="daily-ops-table-wrapper" style={{ marginBottom: '0.5rem' }}>
                    <table className="daily-ops-table">
                      <thead>
                        <tr>
                          <th>Upload ID</th>
                          <th>File Name</th>
                          <th>Report Type</th>
                          <th>Size</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedStageObj.details.files.map((f, fi) => (
                          <tr key={fi}>
                            <td><strong>{f.upload_id}</strong></td>
                            <td>{f.filename}</td>
                            <td>{f.report_type}</td>
                            <td>{(f.size_bytes / 1024).toFixed(1)} KB</td>
                            <td>
                              <span className="daily-ops-status-badge completed">{f.status}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="daily-ops-upload-grid">
                  {/* Energy Upload Card */}
                  <div className="daily-ops-upload-card">
                    <h4 className="daily-ops-card-title">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                      Energy Telemetry File
                    </h4>
                    <label
                      className="daily-ops-dropzone"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (e.dataTransfer?.files?.[0]) {
                          handleEnergyFileSelect(e.dataTransfer.files[0]);
                        }
                      }}
                    >
                      <input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        style={{ display: 'none' }}
                        onChange={(e) => handleEnergyFileSelect(e.target.files[0])}
                      />
                      <div className="daily-ops-dropzone-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="17 8 12 3 7 8" />
                          <line x1="12" y1="3" x2="12" y2="15" />
                        </svg>
                      </div>
                      <p className="daily-ops-dropzone-text">Click or drag Energy file</p>
                      <p className="daily-ops-dropzone-hint">CSV, XLSX, XLS supported</p>
                    </label>
                    {energyFiles && (
                      <div className="daily-ops-file-box">
                        <div className="daily-ops-file-info">
                          <span className="daily-ops-file-name">{energyFiles.name}</span>
                          <span className="daily-ops-file-meta">
                            {(energyFiles.size / 1024).toFixed(1)} KB • {energyFiles.name.split('.').pop().toUpperCase()}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="daily-ops-btn daily-ops-btn-secondary"
                          onClick={() => handleEnergyFileSelect(null)}
                        >
                          Remove
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Production Upload Card */}
                  <div className="daily-ops-upload-card">
                    <h4 className="daily-ops-card-title">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                      </svg>
                      Production Output File
                    </h4>
                    <label
                      className="daily-ops-dropzone"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (e.dataTransfer?.files?.[0]) {
                          handleProductionFileSelect(e.dataTransfer.files[0]);
                        }
                      }}
                    >
                      <input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        style={{ display: 'none' }}
                        onChange={(e) => handleProductionFileSelect(e.target.files[0])}
                      />
                      <div className="daily-ops-dropzone-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="17 8 12 3 7 8" />
                          <line x1="12" y1="3" x2="12" y2="15" />
                        </svg>
                      </div>
                      <p className="daily-ops-dropzone-text">Click or drag Production file</p>
                      <p className="daily-ops-dropzone-hint">CSV, XLSX, XLS supported</p>
                    </label>
                    {productionFiles && (
                      <div className="daily-ops-file-box">
                        <div className="daily-ops-file-info">
                          <span className="daily-ops-file-name">{productionFiles.name}</span>
                          <span className="daily-ops-file-meta">
                            {(productionFiles.size / 1024).toFixed(1)} KB • {productionFiles.name.split('.').pop().toUpperCase()}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="daily-ops-btn daily-ops-btn-secondary"
                          onClick={() => handleProductionFileSelect(null)}
                        >
                          Remove
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Validate & Save Action for Stage 1 */}
                {(energyFiles || productionFiles) && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-primary"
                      onClick={onValidate}
                      disabled={validating}
                    >
                      {validating ? 'Validating Uploads...' : 'Validate & Save'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* STAGE 2: VALIDATION */}
            {selectedStageKey === 'validation' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {dateMismatch && (
                  <div className="daily-ops-alert-banner warning">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', flexWrap: 'gap: 0.5rem' }}>
                      <span>
                        <strong>Date Mismatch:</strong> {dateMismatch.fileType} file has date <strong>{dateMismatch.detectedDate}</strong>, but target date is <strong>{dateMismatch.selectedDate}</strong>.
                      </span>
                      {handleSwitchDate && (
                        <button
                          type="button"
                          className="daily-ops-btn daily-ops-btn-secondary"
                          style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}
                          onClick={() => handleSwitchDate(dateMismatch.detectedDate)}
                        >
                          Switch to {dateMismatch.detectedDate}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {selectedStageObj.details ? (
                  <div className="daily-ops-kpi-grid">
                    <div className="daily-ops-kpi-card">
                      <span className="daily-ops-kpi-label">Valid Records</span>
                      <span className="daily-ops-kpi-value" style={{ color: '#10b981' }}>
                        {formatNumber(selectedStageObj.details.total_valid_rows || 0)}
                      </span>
                      <span className="daily-ops-kpi-sub">Ready for database ingest</span>
                    </div>
                    <div className="daily-ops-kpi-card">
                      <span className="daily-ops-kpi-label">Rejected Records</span>
                      <span
                        className="daily-ops-kpi-value"
                        style={{ color: (selectedStageObj.details.total_rejected_rows || 0) > 0 ? '#ef4444' : 'var(--text-primary)' }}
                      >
                        {formatNumber(selectedStageObj.details.total_rejected_rows || 0)}
                      </span>
                      <span className="daily-ops-kpi-sub">Constraint / format errors</span>
                    </div>
                    <div className="daily-ops-kpi-card">
                      <span className="daily-ops-kpi-label">Reporting Date Target</span>
                      <span className="daily-ops-kpi-value" style={{ fontSize: '1.1rem' }}>
                        {reportingDate}
                      </span>
                      <span className="daily-ops-kpi-sub">Plant: {plantId}</span>
                    </div>
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Select Energy or Production files in Stage 1 and click "Validate & Save" to inspect and verify records.
                  </p>
                )}

                {(energyFiles || productionFiles) && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-primary"
                      onClick={onValidate}
                      disabled={validating}
                    >
                      {validating ? 'Validating Uploads...' : 'Re-Validate & Save'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* STAGE 3: DATABASE INGESTION */}
            {selectedStageKey === 'database_ingestion' && (
              <div className="daily-ops-confirm-box">
                <div className="daily-ops-alert-banner info">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="16" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12.01" y2="8" />
                  </svg>
                  <span>
                    <strong>Strict Safeguard:</strong> Records will only be written to PostgreSQL fact tables with explicit confirmation. Duplicates are handled according to your selected mode.
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <label className="daily-ops-label" style={{ display: 'block', marginBottom: '0.4rem' }}>
                      Ingestion Mode:
                    </label>
                    <select
                      value={ingestMode}
                      onChange={(e) => setIngestMode(e.target.value)}
                      className="daily-ops-date-input"
                      style={{ minWidth: '240px' }}
                    >
                      <option value="INCREMENTAL">INCREMENTAL (Skip Existing Duplicates)</option>
                      <option value="OVERWRITE_CORRECTION">OVERWRITE_CORRECTION (Replace Date Records)</option>
                    </select>
                  </div>

                  {(selectedStageObj.status !== 'COMPLETED' || energyFiles || productionFiles) && (
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-primary"
                      onClick={handleConfirmIngest}
                      disabled={ingesting || (!energyFiles && !productionFiles && stages.validation?.status === 'BLOCKED')}
                      style={{ marginTop: '1.4rem' }}
                    >
                      {ingesting ? 'Committing to PostgreSQL...' : 'Confirm & Commit Records to Database'}
                    </button>
                  )}
                </div>

                {selectedStageObj.details && (
                  <div className="daily-ops-kpi-grid" style={{ marginTop: '0.5rem' }}>
                    <div className="daily-ops-kpi-card">
                      <span className="daily-ops-kpi-label">Committed Energy Rows</span>
                      <span className="daily-ops-kpi-value">{formatNumber(selectedStageObj.details.energy_records || 0)}</span>
                      <span className="daily-ops-kpi-sub">
                        {selectedStageObj.details.linked_energy_records ? `(${formatNumber(selectedStageObj.details.linked_energy_records)} linked to upload)` : 'fact_energy_meter_hourly'}
                      </span>
                    </div>
                    <div className="daily-ops-kpi-card">
                      <span className="daily-ops-kpi-label">Committed Production Rows</span>
                      <span className="daily-ops-kpi-value">{formatNumber(selectedStageObj.details.production_records || 0)}</span>
                      <span className="daily-ops-kpi-sub">
                        {selectedStageObj.details.linked_production_records ? `(${formatNumber(selectedStageObj.details.linked_production_records)} linked to upload)` : 'fact_hourly_production'}
                      </span>
                    </div>
                    {selectedStageObj.details.has_partial_uploads && (
                      <div className="daily-ops-kpi-card" style={{ borderLeft: '3px solid #f59e0b' }}>
                        <span className="daily-ops-kpi-label">Rejected Ingestion Rows</span>
                        <span className="daily-ops-kpi-value" style={{ color: '#f59e0b' }}>
                          {formatNumber(selectedStageObj.details.rejected_rows_count || 0)}
                        </span>
                        <span className="daily-ops-kpi-sub">Partial upload batches</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* STAGE 4: DATA RECONCILIATION */}
            {selectedStageKey === 'data_reconciliation' && (
              <div>
                {selectedStageObj.details?.counts ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div className="daily-ops-kpi-grid">
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Total Checks</span>
                        <span className="daily-ops-kpi-value">{selectedStageObj.details.counts.total_checks}</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Passed Checks</span>
                        <span className="daily-ops-kpi-value" style={{ color: '#10b981' }}>
                          {selectedStageObj.details.counts.pass_count}
                        </span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Warnings</span>
                        <span className="daily-ops-kpi-value" style={{ color: '#f59e0b' }}>
                          {selectedStageObj.details.counts.warning_count}
                        </span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Failed Checks</span>
                        <span className="daily-ops-kpi-value" style={{ color: '#ef4444' }}>
                          {selectedStageObj.details.counts.fail_count}
                        </span>
                      </div>
                    </div>

                    {selectedStageObj.details.checks && selectedStageObj.details.checks.length > 0 && (
                      <div className="daily-ops-table-wrapper">
                        <table className="daily-ops-table">
                          <thead>
                            <tr>
                              <th>Check ID</th>
                              <th>Category</th>
                              <th>Status</th>
                              <th>Summary</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedStageObj.details.checks.map((chk) => (
                              <tr key={chk.check_id}>
                                <td><strong>{chk.check_id}</strong></td>
                                <td>{chk.category}</td>
                                <td>{getStatusBadge(chk.status)}</td>
                                <td>{chk.summary}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Click "Run Downstream Pipeline" in the top toolbar to execute cross-source reconciliation.
                  </p>
                )}
              </div>
            )}

            {/* STAGE 5: DAILY ANALYTICS */}
            {selectedStageKey === 'daily_analytics' && (
              <div>
                {selectedStageObj.details?.energy_summary ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div className="daily-ops-kpi-grid">
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Total Electrical Energy</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.energy_summary?.total_consumption_kwh != null
                            ? formatNumber(selectedStageObj.details.energy_summary.total_consumption_kwh)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">kWh</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Total Energy Cost</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.energy_summary?.total_cost_inr != null
                            ? formatCurrency(selectedStageObj.details.energy_summary.total_cost_inr)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">INR (Application Tariff)</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Production Output</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.production_summary?.actual_qty != null
                            ? formatNumber(selectedStageObj.details.production_summary.actual_qty)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">
                          {selectedStageObj.details.production_summary?.good_qty != null
                            ? `Good: ${formatNumber(selectedStageObj.details.production_summary.good_qty)} • Scrap: ${formatNumber(selectedStageObj.details.production_summary.reject_qty || 0)}`
                            : 'Output breakdown unavailable'}
                        </span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Avg Power Factor</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.power_factor?.avg_power_factor != null
                            ? Number(selectedStageObj.details.power_factor.avg_power_factor).toFixed(3)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">Threshold: 0.900</span>
                      </div>
                    </div>

                    {/* SEC Intensity Grid */}
                    <div className="daily-ops-kpi-grid">
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">SMT Process SEC</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.process_sec?.smt_summary?.overall_process_sec_kwh_per_board != null
                            ? Number(selectedStageObj.details.process_sec.smt_summary.overall_process_sec_kwh_per_board).toFixed(4)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">kWh / PCB board</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">FAL Process SEC</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.process_sec?.fal_summary?.overall_process_sec_kwh_per_phone != null
                            ? Number(selectedStageObj.details.process_sec.fal_summary.overall_process_sec_kwh_per_phone).toFixed(4)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">kWh / phone</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Factory SEC</span>
                        <span className="daily-ops-kpi-value">
                          {selectedStageObj.details.factory_sec?.factory_sec_data_available && selectedStageObj.details.factory_sec?.factory_sec_kwh_per_finished_unit != null
                            ? Number(selectedStageObj.details.factory_sec.factory_sec_kwh_per_finished_unit).toFixed(4)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">
                          {selectedStageObj.details.factory_sec?.factory_sec_data_available
                            ? 'Plant Energy / FAL phones'
                            : selectedStageObj.details.factory_sec?.factory_sec_alignment_note || 'Alignment incomplete'}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Click "Run Downstream Pipeline" in the top toolbar to execute analytics calculations.
                  </p>
                )}
              </div>
            )}

            {/* STAGE 6: INTELLIGENCE REPORT */}
            {selectedStageKey === 'intelligence_report' && (
              <div>
                {selectedStageObj.details?.key_takeaways ? (
                  <div className="daily-ops-confirm-box" style={{ background: 'var(--bg-surface)' }}>
                    <h4 className="daily-ops-card-title">{selectedStageObj.details.title}</h4>
                    <ul className="daily-ops-takeaway-list">
                      {selectedStageObj.details.key_takeaways.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                    {selectedStageObj.details.reconciliation_notes && (
                      <div className="daily-ops-alert-banner info" style={{ marginTop: '0.5rem' }}>
                        <span>{selectedStageObj.details.reconciliation_notes}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Daily intelligence brief will compile automatically after daily analytics.
                  </p>
                )}
              </div>
            )}

            {/* STAGE 7: ANOMALY DETECTION */}
            {selectedStageKey === 'anomaly_detection' && (
              <div>
                {selectedStageObj.details ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div className="daily-ops-kpi-grid">
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Statistical Outliers</span>
                        <span className="daily-ops-kpi-value">
                          {(selectedStageObj.status === 'COMPLETED' || selectedStageObj.status === 'COMPLETED_WITH_WARNINGS') && selectedStageObj.details?.counts_by_detector
                            ? (selectedStageObj.details.counts_by_detector?.statistical_zscore || 0)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">Z-Score ({'>'} 3.0σ)</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Rolling Excursions</span>
                        <span className="daily-ops-kpi-value">
                          {(selectedStageObj.status === 'COMPLETED' || selectedStageObj.status === 'COMPLETED_WITH_WARNINGS') && selectedStageObj.details?.counts_by_detector
                            ? (selectedStageObj.details.counts_by_detector?.rolling_baseline || 0)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">24-hour moving window</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Low Power Factor</span>
                        <span className="daily-ops-kpi-value">
                          {(selectedStageObj.status === 'COMPLETED' || selectedStageObj.status === 'COMPLETED_WITH_WARNINGS') && selectedStageObj.details?.counts_by_detector
                            ? (selectedStageObj.details.counts_by_detector?.low_power_factor || 0)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">PF {'<'} 0.900</span>
                      </div>
                      <div className="daily-ops-kpi-card">
                        <span className="daily-ops-kpi-label">Standby Waste</span>
                        <span className="daily-ops-kpi-value">
                          {(selectedStageObj.status === 'COMPLETED' || selectedStageObj.status === 'COMPLETED_WITH_WARNINGS') && selectedStageObj.details?.counts_by_detector
                            ? (selectedStageObj.details.counts_by_detector?.zero_production_standby || 0)
                            : 'Unavailable'}
                        </span>
                        <span className="daily-ops-kpi-sub">0 line output intervals</span>
                      </div>
                    </div>

                    {selectedStageObj.details.events && selectedStageObj.details.events.length > 0 && (
                      <div className="daily-ops-table-wrapper">
                        <table className="daily-ops-table">
                          <thead>
                            <tr>
                              <th>Timestamp</th>
                              <th>Detector</th>
                              <th>Scope</th>
                              <th>Severity</th>
                              <th>Actual vs Baseline</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedStageObj.details.events.map((ev, i) => (
                              <tr key={i}>
                                <td>{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'All Day'}</td>
                                <td>{ev.detector}</td>
                                <td>{ev.meter_id || ev.line_id || plantId}</td>
                                <td>
                                  <span className={`daily-ops-status-badge ${ev.severity?.toLowerCase() === 'critical' ? 'failed' : ev.severity?.toLowerCase() === 'high' ? 'warning' : 'completed'}`}>
                                    {ev.severity || 'MEDIUM'}
                                  </span>
                                </td>
                                <td>
                                  {ev.actual_kwh ? `${ev.actual_kwh.toFixed(2)} kWh` : ev.power_factor ? `PF: ${ev.power_factor.toFixed(3)}` : 'Deviation observed'}
                                  {ev.baseline_kwh ? ` (Base: ${ev.baseline_kwh.toFixed(2)} kWh)` : ''}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Click "Run Downstream Pipeline" in the top toolbar to execute anomaly detection.
                  </p>
                )}
              </div>
            )}

            {/* STAGE 8: INVESTIGATION HANDOFF */}
            {selectedStageKey === 'investigation_handoff' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                  <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    Review detected anomalies and hand off investigations to the Findings Centre.
                  </p>
                  <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-secondary"
                      onClick={() => navigate('/investigation-actions')}
                    >
                      Go to Investigation Centre
                    </button>
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-primary"
                      onClick={handleSyncFindings}
                      disabled={syncingFindings || (selectedStageObj.status !== 'COMPLETED' && selectedStageObj.status !== 'COMPLETED_WITH_WARNINGS')}
                      title={selectedStageObj.status !== 'COMPLETED' && selectedStageObj.status !== 'COMPLETED_WITH_WARNINGS' ? 'Investigation handoff must complete successfully before syncing' : undefined}
                    >
                      {syncingFindings ? 'Syncing to Investigation Centre...' : 'Sync All to Investigation Centre'}
                    </button>
                  </div>
                </div>

                {selectedStageObj.details?.items && selectedStageObj.details.items.length > 0 ? (
                  <div className="daily-ops-table-wrapper">
                    <table className="daily-ops-table">
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Anomaly &amp; Detector</th>
                          <th>Entity Scope</th>
                          <th>Suggested Priority</th>
                          <th>Finding Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedStageObj.details.items.map((item, i) => (
                          <tr key={i}>
                            <td>{item.timestamp ? new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'All Day'}</td>
                            <td>
                              <strong>{item.detector}</strong>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.priority_reason}</div>
                            </td>
                            <td>{item.meter_id || item.line_id || plantId}</td>
                            <td>
                              <span className={`daily-ops-status-badge ${item.suggested_priority === 'CRITICAL' ? 'failed' : item.suggested_priority === 'HIGH' ? 'warning' : 'not-started'}`}>
                                {item.suggested_priority} (Suggested)
                              </span>
                            </td>
                            <td>
                              {item.finding_id ? (
                                <span style={{ fontSize: '0.8rem', color: '#10b981', fontWeight: 600 }}>
                                  {item.finding_id} ({item.finding_status || 'ACTIVE'})
                                </span>
                              ) : (
                                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Unlinked</span>
                              )}
                            </td>
                            <td>
                              {item.finding_id ? (
                                <button
                                  type="button"
                                  className="daily-ops-btn daily-ops-btn-secondary"
                                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                                  onClick={() => navigate(`/investigation-actions?finding_id=${encodeURIComponent(item.finding_id)}`)}
                                >
                                  Investigate
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="daily-ops-btn daily-ops-btn-secondary"
                                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                                  onClick={() => navigate(`/investigation-actions?plant_id=${plantId}`)}
                                >
                                  View in Centre
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="daily-ops-alert-banner info">
                    <span>No anomalies detected for this date; all operating equipment is within compliance bounds.</span>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* OPPORTUNITIES TO REVIEW */}
      <div className="daily-ops-opportunities-section">
        <div className="daily-ops-opportunities-header">
          <div>
            <div className="daily-ops-opportunities-title-row">
              <h3 className="daily-ops-opportunities-title">
                Opportunities to Review
              </h3>
              <span
                className="daily-ops-opportunities-badge"
                style={{
                  background: opportunities.length > 0 ? 'rgba(59, 130, 246, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                  color: opportunities.length > 0 ? '#2563eb' : '#64748b',
                }}
              >
                {opportunities.length} Surfaced
              </span>
            </div>
            <p className="daily-ops-opportunities-subtitle">
              Deterministic ranking based on recurrence, consumption during comparable stoppages, data coverage, and load controllability.
            </p>
          </div>
          <button
            type="button"
            className="daily-ops-btn daily-ops-btn-secondary"
            style={{ fontSize: '13px', padding: '0.35rem 0.8rem' }}
            onClick={() => navigate(`/investigation-actions?plant_id=${encodeURIComponent(plantId)}`)}
          >
            Open All in Investigation Centre →
          </button>
        </div>

        {loadingOpportunities ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            Scanning pipeline findings for trial and evidence opportunities...
          </div>
        ) : opportunities.length === 0 ? (
          <div className="daily-ops-alert-banner info" style={{ margin: 0 }}>
            <span>No recurring standby or load opportunities requiring review for plant {plantId} on {reportingDate}.</span>
          </div>
        ) : (
          <div className="daily-ops-opp-grid">
            {opportunities.map((opp) => {
              const isTrial = opp.opportunity_type === 'TRIAL_CANDIDATE';
              const isEvidence = opp.opportunity_type === 'EVIDENCE_GATHERING';

              const typeBadgeColor = isTrial ? { bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' }
                : isEvidence ? { bg: '#fffbeb', text: '#b45309', border: '#fde68a' }
                : { bg: '#f5f3ff', text: '#6d28d9', border: '#ddd6fe' };

              const severityColor = opp.severity === 'CRITICAL' ? { bg: '#fee2e2', text: '#b91c1c' }
                : opp.severity === 'HIGH' ? { bg: '#ffedd5', text: '#c2410c' }
                : { bg: '#f1f5f9', text: '#475569' };

              const savingsColor = (opp.savings_potential === 'HIGH' || opp.savings_potential === 'VERY_HIGH')
                ? { bg: '#dcfce7', text: '#15803d' }
                : { bg: '#f1f5f9', text: '#334155' };

              return (
                <div
                  key={opp.opportunity_id}
                  className="daily-ops-opp-card"
                >
                  <div>
                    {/* Header Badges */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          background: typeBadgeColor.bg,
                          color: typeBadgeColor.text,
                          border: `1px solid ${typeBadgeColor.border}`,
                        }}
                      >
                        {isTrial ? '⚡ TRIAL CANDIDATE' : isEvidence ? '📋 EVIDENCE GATHERING' : '🔍 INVESTIGATION'}
                      </span>
                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                        <span
                          title="Operational finding severity"
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                            background: severityColor.bg,
                            color: severityColor.text,
                          }}
                        >
                          Severity: {opp.severity}
                        </span>
                        <span
                          title="Estimated financial savings potential"
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                            background: savingsColor.bg,
                            color: savingsColor.text,
                          }}
                        >
                          Savings: {opp.savings_potential}
                        </span>
                      </div>
                    </div>

                    {/* Title */}
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.98rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {opp.title}
                    </h4>

                    {/* Why Surfaced */}
                    <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      <strong style={{ color: 'var(--text-primary)' }}>Why surfaced: </strong>
                      {opp.why_surfaced}
                    </p>

                    {/* Evidence Notice if Evidence Gathering */}
                    {isEvidence && (
                      <div style={{ padding: '0.5rem 0.75rem', background: '#fffbeb', borderRadius: '6px', border: '1px solid #fde68a', fontSize: '0.78rem', color: '#92400e', marginBottom: '0.75rem' }}>
                        <strong>Submetering Gap: </strong>
                        {opp.audit_recommendation || 'Line-level aggregate meter requires submetering audit to isolate controllable auxiliary loads.'}
                      </div>
                    )}

                    {/* Metrics Row */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', background: 'var(--bg-secondary, #f8fafc)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.75rem' }}>
                      <div>
                        <div style={{ color: 'var(--text-muted)' }}>Stoppage Draw</div>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                          {opp.potential_kwh_per_stoppage != null ? `${opp.potential_kwh_per_stoppage} kWh` : 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-muted)' }}>Cost Potential</div>
                        <div style={{ fontWeight: 600, color: '#16a34a' }}>
                          {opp.potential_cost_per_stoppage_inr != null ? `₹${opp.potential_cost_per_stoppage_inr}` : 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-muted)' }}>Recurrence</div>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                          {opp.recurrence_count} occurrences
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Action Link */}
                  <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--border-color, #e2e8f0)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Scope: {opp.line_id || 'Line'} · {opp.meter_id || 'Meter'}
                    </span>
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-primary"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem' }}
                      onClick={() => {
                        const q = new URLSearchParams({
                          finding_id: opp.finding_id,
                          occurrence_id: opp.occurrence_id || '',
                          plant_id: opp.plant_id,
                          meter_id: opp.meter_id || '',
                          line_id: opp.line_id || '',
                        });
                        navigate(`/investigation-actions?${q.toString()}`);
                      }}
                    >
                      Open in Investigation Centre →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
