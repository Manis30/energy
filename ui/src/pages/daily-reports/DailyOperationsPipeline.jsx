import React, { useRef, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { formatCurrency, formatNumber } from '../../utils/formatters';
import DailyDataEntryForm from './DailyDataEntryForm';

const STAGE_TITLES = {
  data_upload: 'Data Entry',
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

const RECON_CHECK_NAMES = {
  CHK_ENERGY_COVERAGE: 'Energy coverage',
  CHK_PRODUCTION_COVERAGE: 'Production coverage',
  CHK_TIMESTAMP_ALIGNMENT: 'Timestamp alignment',
  CHK_DUPLICATE_RECORDS: 'Duplicate records',
  CHK_SOURCE_CONSISTENCY: 'Source consistency',
  CHK_REFERENCE_INTEGRITY: 'Reference integrity',
  CHK_DATA_QUALITY: 'Data quality',
  ENERGY_COVERAGE: 'Energy coverage',
  PRODUCTION_COVERAGE: 'Production coverage',
  TIMESTAMP_ALIGNMENT: 'Timestamp alignment',
  DUPLICATE_RECORDS: 'Duplicate records',
  SOURCE_CONSISTENCY: 'Source consistency',
  REFERENCE_INTEGRITY: 'Reference integrity',
  DATA_QUALITY: 'Data quality',
};

const getCheckFriendlyName = (chk) => {
  if (chk.check_id && RECON_CHECK_NAMES[chk.check_id]) return RECON_CHECK_NAMES[chk.check_id];
  if (chk.category && RECON_CHECK_NAMES[chk.category]) return RECON_CHECK_NAMES[chk.category];
  if (chk.name) {
    return chk.name.replace(/\s*&.*$/, '').trim();
  }
  return chk.check_id
    ? chk.check_id.replace(/^CHK_/, '').replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())
    : 'System check';
};

const formatCheckSummary = (chk) => {
  const s = String(chk?.summary || '');
  const status = String(chk?.status || '').toUpperCase();

  if (chk.check_id === 'CHK_ENERGY_COVERAGE' || chk.category === 'ENERGY_COVERAGE') {
    const meterMatch = s.match(/Evaluated (\d+) observed energy meter stream/i);
    const meterCount = meterMatch ? meterMatch[1] : null;
    const gapMatch = s.match(/Identified (\d+) coverage gap/i);
    const gapCount = gapMatch ? parseInt(gapMatch[1], 10) : 0;
    if (meterCount) {
      return gapCount > 0
        ? `${meterCount} meter streams checked. ${gapCount} coverage gap${gapCount === 1 ? '' : 's'} identified.`
        : `${meterCount} meter streams checked. No coverage gaps found.`;
    }
  }

  if (chk.check_id === 'CHK_PRODUCTION_COVERAGE' || chk.category === 'PRODUCTION_COVERAGE') {
    const lineMatch = s.match(/Found (\d+) active line stream/i) || s.match(/Evaluated (\d+) registered line/i);
    const lineCount = lineMatch ? lineMatch[1] : null;
    const unobsMatch = s.match(/(\d+) unobserved line warning/i);
    const unobsCount = unobsMatch ? parseInt(unobsMatch[1], 10) : 0;
    if (lineCount) {
      return unobsCount > 0
        ? `${lineCount} line streams checked. ${unobsCount} unobserved line warning${unobsCount === 1 ? '' : 's'} identified.`
        : `${lineCount} line streams checked. No unobserved line warnings found.`;
    }
  }

  if (chk.check_id === 'CHK_TIMESTAMP_ALIGNMENT' || chk.category === 'TIMESTAMP_ALIGNMENT') {
    const misMatch = s.match(/(\d+) active production hour\(s\) with zero energy/i);
    const misCount = misMatch ? parseInt(misMatch[1], 10) : 0;
    if (status === 'PASS' || misCount === 0) {
      return 'Timestamp check passed. No energy or production misalignments found.';
    }
    return `Timestamp warning: ${misCount} production hours with zero energy telemetry.`;
  }

  if (chk.check_id === 'CHK_DUPLICATE_RECORDS' || chk.category === 'DUPLICATE_RECORDS') {
    if (status === 'PASS' || s.includes('0 duplicate energy key')) {
      return 'Uniqueness check passed. No duplicate records found.';
    }
    return 'Duplicate records detected during key verification.';
  }

  if (chk.check_id === 'CHK_SOURCE_CONSISTENCY' || chk.category === 'SOURCE_CONSISTENCY') {
    if (status === 'PASS' || s.includes('0 inconsistency')) {
      return 'Source consistency verified. Upload logs match ingested facts.';
    }
    return 'Source consistency discrepancy detected across upload logs.';
  }

  if (chk.check_id === 'CHK_REFERENCE_INTEGRITY' || chk.category === 'REFERENCE_INTEGRITY') {
    if (status === 'PASS' || s.includes('0 orphan') || s.includes('0 violation')) {
      return 'Reference integrity verified. All foreign keys match dimension tables.';
    }
    return 'Foreign key integrity warning: orphaned records identified.';
  }

  if (chk.check_id === 'CHK_DATA_QUALITY' || chk.category === 'DATA_QUALITY') {
    if (status === 'PASS' || s.includes('0 anomaly') || s.includes('0 out-of-range')) {
      return 'Data quality checks passed. Voltage and quantities within physical bounds.';
    }
    return 'Data quality warnings detected for electrical or production parameters.';
  }

  if (s) {
    return s.replace(/\s+/g, ' ').trim();
  }
  return status === 'PASS' ? 'Check passed with zero discrepancies.' : 'Reconciliation evaluation completed.';
};

const getReconCheckBadge = (status) => {
  const s = String(status || '').toUpperCase();
  switch (s) {
    case 'PASS':
    case 'PASSED':
    case 'COMPLETED':
      return <span className="daily-ops-recon-badge pass">Passed</span>;
    case 'WARNING':
    case 'WARN':
    case 'COMPLETED_WITH_WARNINGS':
      return <span className="daily-ops-recon-badge warning">Warning</span>;
    case 'FAIL':
    case 'FAILED':
      return <span className="daily-ops-recon-badge fail">Failed</span>;
    case 'UNAVAILABLE':
    case 'UNKNOWN':
      return <span className="daily-ops-recon-badge unknown">Unknown</span>;
    case 'NOT_STARTED':
      return <span className="daily-ops-recon-badge not-started">Not started</span>;
    default:
      if (!status) return <span className="daily-ops-recon-badge unknown">Unknown</span>;
      return <span className="daily-ops-recon-badge not-started">{status}</span>;
  }
};

const formatAnomalyMeasurement = (ev) => {
  if (!ev) return 'Baseline unavailable';

  // 1. Power factor anomalies
  const isPf = ev.power_factor != null || (ev.detector && ev.detector.toLowerCase().includes('power factor'));
  if (isPf) {
    const pfVal = ev.power_factor != null
      ? Number(ev.power_factor)
      : (ev.actual_value != null && Number(ev.actual_value) < 1.0 ? Number(ev.actual_value) : null);
    if (pfVal != null) {
      const basePf = ev.baseline_value != null ? Number(ev.baseline_value) : null;
      if (basePf != null) {
        return `PF ${pfVal.toFixed(3)} vs ${basePf.toFixed(3)} base`;
      }
      return `PF ${pfVal.toFixed(3)} (Base: ≥0.900)`;
    }
  }

  // 2. Numeric actual and baseline
  const actual = ev.actual_value != null ? Number(ev.actual_value) : (ev.actual_kwh != null ? Number(ev.actual_kwh) : null);
  const baseline = ev.baseline_value != null ? Number(ev.baseline_value) : (ev.baseline_kwh != null ? Number(ev.baseline_kwh) : null);
  const unit = ev.unit || 'kWh';

  if (actual != null && baseline != null) {
    const diff = actual - baseline;
    const diffSign = diff > 0 ? '+' : '';
    const diffPct = baseline !== 0 ? ` (${diffSign}${((diff / baseline) * 100).toFixed(1)}%)` : '';
    return `${actual.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })} ${unit} vs ${baseline.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })} ${unit}${diffPct}`;
  }

  if (actual != null && baseline == null) {
    return `${actual.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })} ${unit} (Baseline unavailable)`;
  }

  if (actual == null && baseline != null) {
    return `Base: ${baseline.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })} ${unit}`;
  }

  // 3. Deviation score fallback
  if (ev.deviation_score != null) {
    const score = Number(ev.deviation_score);
    if (ev.detector && ev.detector.toLowerCase().includes('z-score')) {
      return `${score > 0 ? '+' : ''}${score.toFixed(2)}σ deviation (Baseline unavailable)`;
    }
    return `${score > 0 ? '+' : ''}${score.toFixed(1)}% deviation (Baseline unavailable)`;
  }

  // 4. Fallback if baseline is completely missing
  return 'Baseline unavailable';
};

export default function DailyOperationsPipeline({
  pipelineState,
  selectedStage: externalSelectedStage,
  onSelectStage: externalOnSelectStage,
  expandedStages,
  toggleStage,
  reportingDate,
  plantId,
  onSwitchPlantAndDate,
  // Data Entry props
  energyRows = [],
  setEnergyRows,
  productionRows = [],
  setProductionRows,
  masterData,
  savedCounts,
  loadingSaved,
  validationResult,
  validating,
  savingEntries,
  onValidateEntries,
  onSaveEntries,
  onReloadRecords,
  // Legacy / Downstream props
  energyFiles,
  productionFiles,
  handleEnergyFileSelect,
  handleProductionFileSelect,
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
  const [expandedCheckId, setExpandedCheckId] = useState(null);
  const [expandedHandoffRows, setExpandedHandoffRows] = useState({});

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
  const isStageCompleted = (status) => {
    const s = String(status || '').toUpperCase();
    return s === 'COMPLETED' || s === 'COMPLETED_WITH_WARNINGS';
  };
  const completedCount = STAGE_KEYS.filter((k) => isStageCompleted(stages[k]?.status)).length;
  const progressPercent = Math.round((completedCount / STAGE_KEYS.length) * 100);
  const onValidate = handleValidateAndSave || handleValidateFiles;
  const selectedStageObj = stages[selectedStageKey] || {
    status: 'NOT_STARTED',
    summary: 'Pending stage initialization',
  };

  const getStatusBadge = (status, stageKey) => {
    const s = String(status || '').toUpperCase();
    const isHandoff = stageKey === 'investigation_handoff';
    switch (s) {
      case 'COMPLETED':
        return (
          <span className="daily-ops-status-badge completed">
            {isHandoff ? 'Stage completed' : 'Completed'}
          </span>
        );
      case 'COMPLETED_WITH_WARNINGS':
        return (
          <span className="daily-ops-status-badge warning">
            {isHandoff ? 'Stage completed with warnings' : 'Completed with warnings'}
          </span>
        );
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
    const s = String(status || '').toUpperCase();
    switch (s) {
      case 'COMPLETED':
        return (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        );
      case 'COMPLETED_WITH_WARNINGS':
        return (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        );
      case 'IN_PROGRESS':
        return (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="spin-icon" aria-hidden="true">
            <line x1="12" y1="2" x2="12" y2="6" />
            <line x1="12" y1="18" x2="12" y2="22" />
            <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
            <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
          </svg>
        );
      case 'FAILED':
        return (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        );
      case 'BLOCKED':
        return (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        );
      default:
        return <span>{idx + 1}</span>;
    }
  };

  const getNodeClass = (status) => {
    const s = String(status || '').toUpperCase();
    switch (s) {
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
    const cur = String(currentStatus || '').toUpperCase();
    const nxt = String(nextStatus || '').toUpperCase();
    if (
      (cur === 'COMPLETED' || cur === 'COMPLETED_WITH_WARNINGS') &&
      (nxt === 'COMPLETED' || nxt === 'COMPLETED_WITH_WARNINGS' || nxt === 'IN_PROGRESS')
    ) {
      return cur === 'COMPLETED_WITH_WARNINGS' ? 'warning' : 'completed';
    }
    if (cur === 'IN_PROGRESS') {
      return 'in-progress';
    }
    if (cur === 'COMPLETED') {
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
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              <span>Operational pipeline</span>
            </h3>
          </div>

          <div className="daily-ops-stepper-meta">
            <span className="daily-ops-progress-text">
              <strong>{completedCount} of 8</strong> completed
            </span>
            <div className="daily-ops-progress-bar-bg" title={`${progressPercent}% completed`}>
              <div
                className="daily-ops-progress-bar-fill"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Desktop Single-Row 8-Step Track */}
        <div className="daily-ops-desktop-stepper-wrap">
          <div className="daily-ops-horizontal-stepper" role="tablist" aria-label="Pipeline Stages">
            {STAGE_KEYS.map((key, idx) => {
              const stage = stages[key] || { status: 'NOT_STARTED', summary: 'Pending initialization' };
              const isSelected = selectedStageKey === key;
              const isCurrent = pipelineState?.current_stage === key;
              const isLast = idx === STAGE_KEYS.length - 1;
              const nextStatus = !isLast ? stages[STAGE_KEYS[idx + 1]]?.status : null;
              const hasWarning = stage.status === 'COMPLETED_WITH_WARNINGS';
              const hasFailed = stage.status === 'FAILED';

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

                  <span className="daily-ops-h-title">{STAGE_TITLES[key]}</span>
                  {hasWarning && (
                    <span className="daily-ops-h-alert-indicator warning">Warning</span>
                  )}
                  {hasFailed && (
                    <span className="daily-ops-h-alert-indicator failed">Failed</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Mobile / Narrow Screen Compact Stage Selector */}
        <div className="daily-ops-mobile-stepper" aria-label="Pipeline Stage Selection">
          <button
            type="button"
            className="daily-ops-mobile-nav-btn"
            onClick={handlePrevStage}
            disabled={selectedIndex === 0}
            aria-label="Previous Stage"
          >
            ‹
          </button>
          <div className="daily-ops-mobile-stage-summary">
            <span className="daily-ops-mobile-step-pill">Stage {selectedIndex + 1} of 8</span>
            <span className="daily-ops-mobile-step-title">{STAGE_TITLES[selectedStageKey]}</span>
            {getStatusBadge(selectedStageObj.status, selectedStageKey)}
          </div>
          <button
            type="button"
            className="daily-ops-mobile-nav-btn"
            onClick={handleNextStage}
            disabled={selectedIndex === STAGE_KEYS.length - 1}
            aria-label="Next Stage"
          >
            ›
          </button>
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
            <h3 className="daily-ops-detail-title">{`${selectedIndex + 1}. ${STAGE_TITLES[selectedStageKey]}`}</h3>
            {getStatusBadge(selectedStageObj.status, selectedStageKey)}
            {pipelineState?.current_stage === selectedStageKey && selectedStageObj.status !== 'COMPLETED' && (
              <span className="daily-ops-active-chip">Active</span>
            )}
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
                <span>Previous</span>
              </button>
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary daily-ops-btn-sm"
                onClick={handleNextStage}
                disabled={selectedIndex === STAGE_KEYS.length - 1}
                aria-label="Next Stage"
              >
                <span>Next</span>
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

            {/* STAGE 1: DATA ENTRY */}
            {selectedStageKey === 'data_upload' && (
              <DailyDataEntryForm
                reportingDate={reportingDate}
                plantId={plantId}
                masterData={masterData}
                energyRows={energyRows}
                setEnergyRows={setEnergyRows}
                productionRows={productionRows}
                setProductionRows={setProductionRows}
                savedCounts={savedCounts}
                onValidate={onValidateEntries}
                onSave={onSaveEntries}
                validating={validating}
                saving={savingEntries}
                validationResult={validationResult}
                onReload={onReloadRecords}
                loadingSaved={loadingSaved}
                onSwitchPlantAndDate={onSwitchPlantAndDate}
              />
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
                    Enter or paste Energy and Production data in Stage 1 and click "Validate entries" to inspect and verify records.
                  </p>
                )}

                {(onValidateEntries || energyFiles || productionFiles) && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                    <button
                      type="button"
                      className="daily-ops-btn daily-ops-btn-primary"
                      onClick={onValidateEntries || onValidate}
                      disabled={validating}
                    >
                      {validating ? 'Validating Entries...' : 'Re-Validate Entries'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* STAGE 3: DATABASE INGESTION */}
            {selectedStageKey === 'database_ingestion' && (
              <div className="daily-ops-stage-ingestion-content">
                {/* 1. Compact Saved Records Summary */}
                <div className="daily-ops-saved-records-card">
                  <div className="daily-ops-saved-metric-col">
                    <span className="daily-ops-saved-metric-label">Energy</span>
                    <span className="daily-ops-saved-metric-value">
                      {formatNumber(selectedStageObj?.details?.energy_records ?? savedCounts?.energy ?? 0)}
                    </span>
                    <span className="daily-ops-saved-metric-sub">
                      ({formatNumber(selectedStageObj?.details?.linked_energy_records != null ? selectedStageObj.details.linked_energy_records : ((selectedStageObj?.details?.energy_records ?? savedCounts?.energy ?? 0) > 0 ? 1 : 0))} linked to upload)
                    </span>
                  </div>
                  <div className="daily-ops-saved-metric-divider" aria-hidden="true" />
                  <div className="daily-ops-saved-metric-col">
                    <span className="daily-ops-saved-metric-label">Production</span>
                    <span className="daily-ops-saved-metric-value">
                      {formatNumber(selectedStageObj?.details?.production_records ?? savedCounts?.production ?? 0)}
                    </span>
                    <span className="daily-ops-saved-metric-sub">
                      ({formatNumber(selectedStageObj?.details?.linked_production_records != null ? selectedStageObj.details.linked_production_records : ((selectedStageObj?.details?.production_records ?? savedCounts?.production ?? 0) > 0 ? 1 : 0))} linked to upload)
                    </span>
                  </div>
                  {selectedStageObj?.details?.has_partial_uploads && selectedStageObj?.details?.rejected_rows_count > 0 && (
                    <>
                      <div className="daily-ops-saved-metric-divider" aria-hidden="true" />
                      <div className="daily-ops-saved-metric-col is-warning">
                        <span className="daily-ops-saved-metric-label">Rejected</span>
                        <span className="daily-ops-saved-metric-value" style={{ color: '#f59e0b' }}>
                          {formatNumber(selectedStageObj.details.rejected_rows_count)}
                        </span>
                        <span className="daily-ops-saved-metric-sub">Partial upload batches</span>
                      </div>
                    </>
                  )}
                </div>

                {/* 2. Simplified Ingestion Controls */}
                <div className="daily-ops-ingest-controls-section">
                  <div className="daily-ops-ingest-controls-row">
                    <div className="daily-ops-ingest-select-group">
                      <label htmlFor="daily-ops-ingest-mode" className="daily-ops-ingest-label">
                        Ingestion mode
                      </label>
                      <select
                        id="daily-ops-ingest-mode"
                        value={ingestMode}
                        onChange={(e) => setIngestMode(e.target.value)}
                        className="daily-ops-ingest-select"
                      >
                        <option value="OVERWRITE_CORRECTION">Replace records for this date</option>
                        <option value="INCREMENTAL">Skip existing records</option>
                      </select>
                    </div>

                    {(selectedStageObj.status !== 'COMPLETED' || energyFiles || productionFiles) && (
                      <button
                        type="button"
                        className="daily-ops-btn daily-ops-btn-primary"
                        onClick={handleConfirmIngest}
                        disabled={ingesting || (!energyFiles && !productionFiles && stages.validation?.status === 'BLOCKED')}
                      >
                        {ingesting ? 'Committing to PostgreSQL…' : 'Confirm & commit records to database'}
                      </button>
                    )}
                  </div>

                  <p className="daily-ops-ingest-helper">
                    {ingestMode === 'OVERWRITE_CORRECTION'
                      ? 'Replaces existing records for this date. Confirmation is required before writing to the database.'
                      : 'Preserves existing records and skips duplicates. Confirmation is required before writing to the database.'}
                  </p>
                </div>
              </div>
            )}

            {/* STAGE 4: DATA RECONCILIATION */}
            {selectedStageKey === 'data_reconciliation' && (
              <div className="daily-ops-stage-recon-content">
                {selectedStageObj.details?.checks || selectedStageObj.details?.counts ? (
                  <>
                    {/* 1. Slim summary strip directly above table */}
                    <div className="daily-ops-recon-summary-strip">
                      <span className="daily-ops-recon-metric">
                        <strong>
                          {selectedStageObj.details?.counts?.total_checks ?? selectedStageObj.details?.checks?.length ?? 0}
                        </strong>{' '}
                        checks
                      </span>
                      <span className="daily-ops-recon-sep" aria-hidden="true">·</span>
                      <span className="daily-ops-recon-metric is-pass">
                        <strong>
                          {selectedStageObj.details?.counts?.pass_count ?? (selectedStageObj.details?.checks || []).filter(c => String(c.status).toUpperCase() === 'PASS').length}
                        </strong>{' '}
                        passed
                      </span>
                      <span className="daily-ops-recon-sep" aria-hidden="true">·</span>
                      <span className="daily-ops-recon-metric is-warning">
                        <strong>
                          {selectedStageObj.details?.counts?.warning_count ?? (selectedStageObj.details?.checks || []).filter(c => String(c.status).toUpperCase() === 'WARNING').length}
                        </strong>{' '}
                        warnings
                      </span>
                      <span className="daily-ops-recon-sep" aria-hidden="true">·</span>
                      <span className="daily-ops-recon-metric is-fail">
                        <strong>
                          {selectedStageObj.details?.counts?.fail_count ?? (selectedStageObj.details?.checks || []).filter(c => String(c.status).toUpperCase() === 'FAIL').length}
                        </strong>{' '}
                        failed
                      </span>
                    </div>

                    {/* 2. Simplified 3-column table */}
                    {selectedStageObj.details?.checks && selectedStageObj.details.checks.length > 0 && (
                      <div className="daily-ops-recon-table-wrapper">
                        <table className="daily-ops-recon-table">
                          <thead>
                            <tr>
                              <th scope="col" className="daily-ops-recon-th-check">Check</th>
                              <th scope="col" className="daily-ops-recon-th-result">Result</th>
                              <th scope="col" className="daily-ops-recon-th-summary">Summary</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedStageObj.details.checks.map((chk) => {
                              const isExpanded = expandedCheckId === chk.check_id;
                              const friendlyName = getCheckFriendlyName(chk);
                              const shortSummary = formatCheckSummary(chk);
                              return (
                                <React.Fragment key={chk.check_id}>
                                  <tr
                                    className={`daily-ops-recon-row ${isExpanded ? 'is-expanded' : ''}`}
                                    onClick={() => setExpandedCheckId(isExpanded ? null : chk.check_id)}
                                  >
                                    <td className="daily-ops-recon-td-check">
                                      <button
                                        type="button"
                                        className="daily-ops-recon-expand-btn"
                                        aria-expanded={isExpanded}
                                        title="Toggle diagnostic details"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setExpandedCheckId(isExpanded ? null : chk.check_id);
                                        }}
                                      >
                                        <svg
                                          width="12"
                                          height="12"
                                          viewBox="0 0 24 24"
                                          fill="none"
                                          stroke="currentColor"
                                          strokeWidth="2.5"
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          className={`daily-ops-recon-chevron ${isExpanded ? 'is-open' : ''}`}
                                          aria-hidden="true"
                                        >
                                          <polyline points="9 18 15 12 9 6" />
                                        </svg>
                                        <span>{friendlyName}</span>
                                      </button>
                                    </td>
                                    <td className="daily-ops-recon-td-result">
                                      {getReconCheckBadge(chk.status)}
                                    </td>
                                    <td className="daily-ops-recon-td-summary">
                                      <span className="daily-ops-recon-summary-text">{shortSummary}</span>
                                    </td>
                                  </tr>
                                  {isExpanded && (
                                    <tr className="daily-ops-recon-detail-row">
                                      <td colSpan={3} className="daily-ops-recon-detail-cell">
                                        <div className="daily-ops-recon-detail-box">
                                          <div className="daily-ops-recon-detail-meta">
                                            <span className="daily-ops-recon-detail-pill">
                                              <strong>Check ID:</strong> <code>{chk.check_id}</code>
                                            </span>
                                            <span className="daily-ops-recon-detail-pill">
                                              <strong>Category:</strong> <code>{chk.category}</code>
                                            </span>
                                          </div>
                                          <div className="daily-ops-recon-detail-full">
                                            <strong>Full diagnostic:</strong> {chk.summary || chk.description || 'No additional diagnostics reported.'}
                                          </div>
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '13px' }}>
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
              <div className="daily-ops-anomaly-container">
                {selectedStageObj.details ? (
                  <>
                    {/* Detector Summary Strip */}
                    {(() => {
                      const counts = selectedStageObj.details?.counts_by_detector || {};
                      const events = selectedStageObj.details?.events || [];

                      const detectorItems = [
                        {
                          id: 'statistical_zscore',
                          label: 'Statistical outliers',
                          count: counts.statistical_zscore ?? events.filter((e) => e.detector === 'Statistical Z-Score').length,
                          tooltip: 'Z-score threshold: > 3.0σ deviation from historical mean',
                        },
                        {
                          id: 'rolling_baseline',
                          label: 'Rolling excursions',
                          count: counts.rolling_baseline ?? events.filter((e) => e.detector === 'Rolling Baseline').length,
                          tooltip: 'Rolling window threshold: 24-hour moving window deviation > 2.5σ',
                        },
                        {
                          id: 'low_power_factor',
                          label: 'Low power factor',
                          count: counts.low_power_factor ?? events.filter((e) => e.detector === 'Low Power Factor').length,
                          tooltip: 'Power factor threshold: PF < 0.900 under active operating load',
                        },
                        {
                          id: 'zero_production_standby',
                          label: 'Standby waste',
                          count: counts.zero_production_standby ?? events.filter((e) => e.detector === 'Zero-Production Standby').length,
                          tooltip: 'Standby threshold: Consumption during zero line output intervals',
                        },
                      ];

                      const comparableCount = events.filter(
                        (e) => e.detector === 'Comparable-Period Shift' || e.type === 'COMPARABLE_PERIOD_ELECTRICITY_CHANGE'
                      ).length || (counts.persistent_baseload && events.some((e) => e.detector?.includes('Comparable')) ? counts.persistent_baseload : 0);

                      if (comparableCount > 0 || events.some((e) => e.detector === 'Comparable-Period Shift')) {
                        detectorItems.push({
                          id: 'comparable_period_shift',
                          label: 'Comparable-period shift',
                          count: comparableCount,
                          tooltip: 'Shift comparison threshold: Deviation against comparable production operating periods',
                        });
                      }

                      return (
                        <div className="daily-ops-anomaly-summary-strip" role="region" aria-label="Detector Summary">
                          {detectorItems.map((item) => (
                            <div
                              key={item.id}
                              className="daily-ops-anomaly-summary-item"
                              title={item.tooltip}
                              aria-label={`${item.label}: ${item.count}. ${item.tooltip}`}
                              tabIndex={0}
                            >
                              <span className="daily-ops-anomaly-summary-label">{item.label}</span>
                              <span className={`daily-ops-anomaly-summary-count ${item.count > 0 ? 'has-findings' : 'zero-findings'}`}>
                                {formatNumber(item.count)}
                              </span>
                            </div>
                          ))}
                        </div>
                      );
                    })()}

                    {/* Findings Table */}
                    {selectedStageObj.details.events && selectedStageObj.details.events.length > 0 ? (
                      <div className="daily-ops-table-wrapper">
                        <table className="daily-ops-anomaly-table">
                          <thead>
                            <tr>
                              <th scope="col">Finding</th>
                              <th scope="col">Affected asset</th>
                              <th scope="col">Detected at</th>
                              <th scope="col">Severity</th>
                              <th scope="col">Measurement</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedStageObj.details.events.map((ev, i) => {
                              const findingName = ev.detector || (ev.anomaly_type ? ev.anomaly_type.replace(/_/g, ' ') : 'Anomaly');
                              const assetName = ev.meter_id || ev.line_id || plantId || 'Plant';
                              const detectedAt = ev.timestamp
                                ? new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })
                                : 'All day';
                              const sev = (ev.severity || 'MEDIUM').toUpperCase();
                              const sevClass = sev === 'CRITICAL' ? 'sev-critical' : sev === 'HIGH' ? 'sev-high' : sev === 'LOW' ? 'sev-low' : 'sev-medium';
                              const measurementText = formatAnomalyMeasurement(ev);

                              return (
                                <tr key={ev.id || i}>
                                  <td className="daily-ops-anomaly-finding-cell">
                                    <span className="daily-ops-anomaly-finding-title">{findingName}</span>
                                  </td>
                                  <td className="daily-ops-anomaly-asset-cell">
                                    <span className="daily-ops-anomaly-asset-tag">{assetName}</span>
                                  </td>
                                  <td className="daily-ops-anomaly-time-cell">{detectedAt}</td>
                                  <td className="daily-ops-anomaly-sev-cell">
                                    <span className={`daily-ops-sev-badge ${sevClass}`}>{sev}</span>
                                  </td>
                                  <td className="daily-ops-anomaly-measurement-cell">{measurementText}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="daily-ops-alert-banner info" style={{ margin: 0 }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <circle cx="12" cy="12" r="10" />
                          <line x1="12" y1="16" x2="12" y2="12" />
                          <line x1="12" y1="8" x2="12.01" y2="8" />
                        </svg>
                        <span>No anomalies detected for this run. All monitored assets operating within baseline bounds.</span>
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Click "Run Downstream Pipeline" in the top toolbar to execute anomaly detection.
                  </p>
                )}
              </div>
            )}

            {/* STAGE 8: INVESTIGATION HANDOFF */}
            {selectedStageKey === 'investigation_handoff' && (() => {
              const handoffItems = selectedStageObj.details?.items || [];
              const totalAnomalies = handoffItems.length;
              const linkedCount = handoffItems.filter((item) => Boolean(item.finding_id)).length;
              const unlinkedCount = totalAnomalies - linkedCount;
              const anomalySummary = `${totalAnomalies} ${totalAnomalies === 1 ? 'anomaly' : 'anomalies'} · ${linkedCount} linked · ${unlinkedCount} unlinked`;

              return (
                <div className="daily-ops-handoff-container">
                  {/* Toolbar: Live summary on left, sync & navigation controls on right */}
                  <div className="daily-ops-handoff-toolbar">
                    <div className="daily-ops-handoff-summary">
                      {anomalySummary}
                    </div>
                    <div className="daily-ops-handoff-actions">
                      <button
                        type="button"
                        className="daily-ops-btn daily-ops-btn-secondary"
                        onClick={() => navigate(`/investigation-actions?plant_id=${encodeURIComponent(plantId)}`)}
                      >
                        Open Investigation Centre
                      </button>
                      <button
                        type="button"
                        className="daily-ops-btn daily-ops-btn-primary"
                        onClick={handleSyncFindings}
                        disabled={syncingFindings || (selectedStageObj.status !== 'COMPLETED' && selectedStageObj.status !== 'COMPLETED_WITH_WARNINGS')}
                        title={selectedStageObj.status !== 'COMPLETED' && selectedStageObj.status !== 'COMPLETED_WITH_WARNINGS' ? 'Investigation handoff must complete successfully before syncing' : undefined}
                      >
                        {syncingFindings ? 'Syncing...' : 'Sync all'}
                      </button>
                    </div>
                  </div>

                  {/* Findings correlation table */}
                  {handoffItems.length > 0 ? (
                    <div className="daily-ops-table-wrapper">
                      <table className="daily-ops-table daily-ops-handoff-table">
                        <thead>
                          <tr>
                            <th>Anomaly</th>
                            <th>Asset</th>
                            <th>Detected at</th>
                            <th>Suggested priority</th>
                            <th>Finding</th>
                            <th style={{ textAlign: 'right' }}>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {handoffItems.map((item, i) => {
                            const prio = (item.suggested_priority || item.severity || 'MEDIUM').toUpperCase();
                            const prioLabel = prio.charAt(0) + prio.slice(1).toLowerCase();
                            const isLinked = Boolean(item.finding_id);
                            const isExpanded = Boolean(expandedHandoffRows[i]);

                            // Short supporting fact only when adding information
                            let shortFact = '';
                            if (item.actual_value !== undefined && item.actual_value !== null) {
                              const actVal = Number(item.actual_value);
                              const actStr = !isNaN(actVal) ? actVal.toFixed(2) : String(item.actual_value);
                              const baseVal = item.baseline_value !== undefined && item.baseline_value !== null ? Number(item.baseline_value) : null;
                              const baseStr = baseVal !== null && !isNaN(baseVal) ? baseVal.toFixed(2) : null;
                              shortFact = baseStr ? `Recorded ${actStr} vs ${baseStr} baseline` : `Recorded ${actStr}`;
                            } else if (item.deviation_pct !== undefined && item.deviation_pct !== null) {
                              const dev = Number(item.deviation_pct);
                              if (!isNaN(dev)) {
                                shortFact = `Deviation: ${(dev * 100).toFixed(1)}%`;
                              }
                            }

                            // Finding status display
                            const findingStatusRaw = item.finding_status || 'NEW';
                            const findingStatusFormatted = findingStatusRaw.charAt(0) + findingStatusRaw.slice(1).toLowerCase();
                            const findingLabel = isLinked ? `Linked · ${findingStatusFormatted}` : 'Unlinked';

                            // Detection timestamp
                            const timeStr = item.timestamp
                              ? new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                              : 'All Day';

                            // Asset display
                            const assetStr = item.meter_id || item.line_id || plantId;

                            return (
                              <React.Fragment key={i}>
                                <tr className={isExpanded ? 'daily-ops-row-expanded' : ''}>
                                  <td className="daily-ops-col-anomaly">
                                    <div className="daily-ops-anomaly-name-row">
                                      <button
                                        type="button"
                                        className="daily-ops-row-expand-btn"
                                        onClick={() => setExpandedHandoffRows(prev => ({ ...prev, [i]: !prev[i] }))}
                                        aria-expanded={isExpanded}
                                        title={isExpanded ? 'Collapse details' : 'Expand details'}
                                      >
                                        <svg
                                          width="12"
                                          height="12"
                                          viewBox="0 0 24 24"
                                          fill="none"
                                          stroke="currentColor"
                                          strokeWidth="2.5"
                                          style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s ease' }}
                                        >
                                          <polyline points="9 18 15 12 9 6" />
                                        </svg>
                                      </button>
                                      <strong className="daily-ops-anomaly-title">{item.detector || item.anomaly_type || 'Anomaly'}</strong>
                                    </div>
                                    {shortFact && (
                                      <div className="daily-ops-anomaly-fact">{shortFact}</div>
                                    )}
                                  </td>
                                  <td className="daily-ops-col-asset">
                                    <span className="daily-ops-asset-id">{assetStr}</span>
                                  </td>
                                  <td className="daily-ops-col-time">
                                    <span className="daily-ops-time-val">{timeStr}</span>
                                  </td>
                                  <td className="daily-ops-col-prio">
                                    <span className={`daily-ops-badge badge-${prio.toLowerCase()}`}>
                                      {prioLabel}
                                    </span>
                                  </td>
                                  <td className="daily-ops-col-finding">
                                    <span
                                      className={`daily-ops-finding-pill ${isLinked ? 'is-linked' : 'is-unlinked'}`}
                                      title={isLinked ? `Finding ID: ${item.finding_id}` : undefined}
                                    >
                                      {findingLabel}
                                    </span>
                                  </td>
                                  <td className="daily-ops-col-action" style={{ textAlign: 'right' }}>
                                    {isLinked ? (
                                      <button
                                        type="button"
                                        className="daily-ops-btn daily-ops-btn-secondary daily-ops-btn-sm"
                                        onClick={() => navigate(`/investigation-actions?finding_id=${encodeURIComponent(item.finding_id)}`)}
                                      >
                                        Open finding
                                      </button>
                                    ) : (
                                      <button
                                        type="button"
                                        className="daily-ops-btn daily-ops-btn-secondary daily-ops-btn-sm"
                                        onClick={() => navigate(`/investigation-actions?plant_id=${encodeURIComponent(plantId)}`)}
                                      >
                                        Open directory
                                      </button>
                                    )}
                                  </td>
                                </tr>
                                {isExpanded && (
                                  <tr className="daily-ops-detail-expanded-row">
                                    <td colSpan={6}>
                                      <div className="daily-ops-handoff-row-details">
                                        {item.priority_reason && (
                                          <div className="daily-ops-detail-item">
                                            <span className="daily-ops-detail-label">Description:</span>
                                            <span className="daily-ops-detail-val">{item.priority_reason}</span>
                                          </div>
                                        )}
                                        {item.finding_id && (
                                          <div className="daily-ops-detail-item">
                                            <span className="daily-ops-detail-label">Finding ID:</span>
                                            <code className="daily-ops-detail-code">{item.finding_id}</code>
                                          </div>
                                        )}
                                        {item.evidence_classification && (
                                          <div className="daily-ops-detail-item">
                                            <span className="daily-ops-detail-label">Classification:</span>
                                            <span className="daily-ops-detail-val">{item.evidence_classification}</span>
                                          </div>
                                        )}
                                        {item.anomaly_type && (
                                          <div className="daily-ops-detail-item">
                                            <span className="daily-ops-detail-label">Detector Type:</span>
                                            <span className="daily-ops-detail-val">{item.anomaly_type}</span>
                                          </div>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="daily-ops-alert-banner info">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="16" x2="12" y2="12" />
                        <line x1="12" y1="8" x2="12.01" y2="8" />
                      </svg>
                      <span><strong>Investigation Status:</strong> No anomalies detected for this date; all operating equipment is within compliance bounds.</span>
                    </div>
                  )}
                </div>
              );
            })()}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* OPPORTUNITIES TO REVIEW */}
      <div className={`daily-ops-opportunities-section ${opportunities.length === 0 || loadingOpportunities ? 'is-empty' : ''}`}>
        {loadingOpportunities ? (
          <div className="daily-ops-opportunities-empty-row">
            <div className="daily-ops-opportunities-empty-left">
              <span className="daily-ops-opportunities-empty-title">Opportunities to review</span>
              <span className="daily-ops-opportunities-empty-text">Checking for opportunities…</span>
            </div>
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary daily-ops-opportunities-action"
              onClick={() => navigate(`/investigation-actions?plant_id=${encodeURIComponent(plantId)}`)}
            >
              Open in Investigation Centre →
            </button>
          </div>
        ) : opportunities.length === 0 ? (
          <div className="daily-ops-opportunities-empty-row">
            <div className="daily-ops-opportunities-empty-left">
              <span className="daily-ops-opportunities-empty-title">Opportunities to review · 0</span>
              <span className="daily-ops-opportunities-empty-text">None for {plantId} on {reportingDate}.</span>
            </div>
            <button
              type="button"
              className="daily-ops-btn daily-ops-btn-secondary daily-ops-opportunities-action"
              onClick={() => navigate(`/investigation-actions?plant_id=${encodeURIComponent(plantId)}`)}
            >
              Open in Investigation Centre →
            </button>
          </div>
        ) : (
          <>
            <div className="daily-ops-opportunities-header">
              <div className="daily-ops-opportunities-title-group">
                <h4 className="daily-ops-opportunities-title">
                  Opportunities to review
                </h4>
                <span className="daily-ops-opportunities-badge has-opps">
                  {opportunities.length}
                </span>
              </div>
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary daily-ops-opportunities-action"
                onClick={() => navigate(`/investigation-actions?plant_id=${encodeURIComponent(plantId)}`)}
              >
                Open in Investigation Centre →
              </button>
            </div>
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
          </>
        )}
      </div>
    </div>
  );
}
