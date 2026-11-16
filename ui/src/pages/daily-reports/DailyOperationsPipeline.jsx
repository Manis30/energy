import React from 'react';
import { useNavigate } from 'react-router-dom';
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
  ingesting,
  handleConfirmIngest,
  ingestMode,
  setIngestMode,
  runningDownstream,
  handleRunDownstream,
  handleSyncFindings,
  syncingFindings,
}) {
  const navigate = useNavigate();
  const stages = pipelineState?.stages || {};

  const getStatusBadge = (status) => {
    switch (status) {
      case 'COMPLETED':
        return <span className="daily-ops-status-badge completed">Completed</span>;
      case 'COMPLETED_WITH_WARNINGS':
        return <span className="daily-ops-status-badge warning">Completed (Warnings)</span>;
      case 'IN_PROGRESS':
        return <span className="daily-ops-status-badge in-progress">In Progress</span>;
      case 'FAILED':
        return <span className="daily-ops-status-badge failed">Failed</span>;
      case 'BLOCKED':
        return <span className="daily-ops-status-badge blocked">Blocked</span>;
      default:
        return <span className="daily-ops-status-badge not-started">Not Started</span>;
    }
  };

  const getNodeIcon = (status, idx) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        );
      case 'COMPLETED_WITH_WARNINGS':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        );
      case 'IN_PROGRESS':
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="spin-icon">
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
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        );
      case 'BLOCKED':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
        return '';
    }
  };

  return (
    <div className="daily-ops-stepper">
      {STAGE_KEYS.map((key, idx) => {
        const stage = stages[key] || { status: 'NOT_STARTED', summary: 'Pending initialization' };
        const isExpanded = expandedStages[key];
        const isCurrent = pipelineState?.current_stage === key;
        const isLast = idx === STAGE_KEYS.length - 1;

        return (
          <div key={key} className="daily-ops-stage-wrapper">
            <div className="daily-ops-stepper-track">
              <div className={`daily-ops-node ${getNodeClass(stage.status)}`}>
                {getNodeIcon(stage.status, idx)}
              </div>
              {!isLast && (
                <div
                  className={`daily-ops-line ${
                    stage.status === 'COMPLETED' || stage.status === 'COMPLETED_WITH_WARNINGS' ? 'completed' : ''
                  }`}
                />
              )}
            </div>

            <div className={`daily-ops-stage-card ${isCurrent ? 'active-stage' : ''}`}>
              {/* Stage Header */}
              <div className="daily-ops-stage-header" onClick={() => toggleStage(key)}>
                <div className="daily-ops-stage-header-left">
                  <div className="daily-ops-stage-title-row">
                    <h3 className="daily-ops-stage-title">{`${idx + 1}. ${STAGE_TITLES[key]}`}</h3>
                    {getStatusBadge(stage.status)}
                  </div>
                  <p className="daily-ops-stage-summary">{stage.summary}</p>
                </div>

                <div className="daily-ops-stage-header-right">
                  {stage.timestamp && (
                    <span className="daily-ops-timestamp">
                      {new Date(stage.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  )}
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className={`daily-ops-chevron ${isExpanded ? 'expanded' : ''}`}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </div>

              {/* Collapsible Stage Body */}
              {isExpanded && (
                <div className="daily-ops-stage-body">
                  {/* FAILED STATE RECOVERY BOX */}
                  {stage.status === 'FAILED' && (
                    <div className="daily-ops-recovery-box">
                      <div>
                        <strong>Execution Error:</strong> {stage.summary}
                      </div>
                      <button
                        type="button"
                        className="daily-ops-btn daily-ops-btn-primary"
                        onClick={() => {
                          if (key === 'validation') handleValidateFiles();
                          else if (key === 'database_ingestion') handleConfirmIngest();
                          else handleRunDownstream();
                        }}
                      >
                        Retry Stage
                      </button>
                    </div>
                  )}

                  {/* STAGE 1: DATA UPLOAD */}
                  {key === 'data_upload' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      {stage.details?.is_historical_baseline && (
                        <div className="daily-ops-alert-banner info">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="16" x2="12" y2="12" />
                            <line x1="12" y1="8" x2="12.01" y2="8" />
                          </svg>
                          <span>
                            <strong>Historical Telemetry Baseline:</strong> Fact records exist in PostgreSQL for {reportingDate}. You may upload new files below to perform an incremental or overwrite ingestion, or execute downstream pipeline stages directly on baseline data.
                          </span>
                        </div>
                      )}

                      {stage.details?.has_linked_uploads && stage.details?.files?.length > 0 && (
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
                              {stage.details.files.map((f, fi) => (
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
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                          </svg>
                          Energy Telemetry File
                        </h4>
                        <label className="daily-ops-dropzone">
                          <input
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            style={{ display: 'none' }}
                            onChange={(e) => handleEnergyFileSelect(e.target.files[0])}
                          />
                          <div className="daily-ops-dropzone-icon">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                          </svg>
                          Production Output File
                        </h4>
                        <label className="daily-ops-dropzone">
                          <input
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            style={{ display: 'none' }}
                            onChange={(e) => handleProductionFileSelect(e.target.files[0])}
                          />
                          <div className="daily-ops-dropzone-icon">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
                    </div>
                  )}

                  {/* Validate Action for Stage 1 */}
                  {key === 'data_upload' && (energyFiles || productionFiles) && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                      <button
                        type="button"
                        className="daily-ops-btn daily-ops-btn-primary"
                        onClick={handleValidateFiles}
                        disabled={validating}
                      >
                        {validating ? 'Validating Uploads...' : 'Proceed to Validation'}
                      </button>
                    </div>
                  )}

                  {/* STAGE 2: VALIDATION */}
                  {key === 'validation' && (
                    <div>
                      {stage.details ? (
                        <div className="daily-ops-kpi-grid">
                          <div className="daily-ops-kpi-card">
                            <span className="daily-ops-kpi-label">Valid Records</span>
                            <span className="daily-ops-kpi-value" style={{ color: '#10b981' }}>
                              {formatNumber(stage.details.total_valid_rows || 0)}
                            </span>
                            <span className="daily-ops-kpi-sub">Ready for database ingest</span>
                          </div>
                          <div className="daily-ops-kpi-card">
                            <span className="daily-ops-kpi-label">Rejected Records</span>
                            <span
                              className="daily-ops-kpi-value"
                              style={{ color: (stage.details.total_rejected_rows || 0) > 0 ? '#ef4444' : 'var(--text-primary)' }}
                            >
                              {formatNumber(stage.details.total_rejected_rows || 0)}
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
                          Select Energy or Production files in Stage 1 and click "Proceed to Validation".
                        </p>
                      )}
                    </div>
                  )}

                  {/* STAGE 3: DATABASE INGESTION */}
                  {key === 'database_ingestion' && (
                    <div className="daily-ops-confirm-box">
                      <div className="daily-ops-alert-banner info">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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

                        {(stage.status !== 'COMPLETED' || energyFiles || productionFiles) && (
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

                      {stage.details && (
                        <div className="daily-ops-kpi-grid" style={{ marginTop: '0.5rem' }}>
                          <div className="daily-ops-kpi-card">
                            <span className="daily-ops-kpi-label">Committed Energy Rows</span>
                            <span className="daily-ops-kpi-value">{formatNumber(stage.details.energy_records || 0)}</span>
                            <span className="daily-ops-kpi-sub">
                              {stage.details.linked_energy_records ? `(${formatNumber(stage.details.linked_energy_records)} linked to upload)` : 'fact_energy_meter_hourly'}
                            </span>
                          </div>
                          <div className="daily-ops-kpi-card">
                            <span className="daily-ops-kpi-label">Committed Production Rows</span>
                            <span className="daily-ops-kpi-value">{formatNumber(stage.details.production_records || 0)}</span>
                            <span className="daily-ops-kpi-sub">
                              {stage.details.linked_production_records ? `(${formatNumber(stage.details.linked_production_records)} linked to upload)` : 'fact_hourly_production'}
                            </span>
                          </div>
                          {stage.details.has_partial_uploads && (
                            <div className="daily-ops-kpi-card" style={{ borderLeft: '3px solid #f59e0b' }}>
                              <span className="daily-ops-kpi-label">Rejected Ingestion Rows</span>
                              <span className="daily-ops-kpi-value" style={{ color: '#f59e0b' }}>
                                {formatNumber(stage.details.rejected_rows_count || 0)}
                              </span>
                              <span className="daily-ops-kpi-sub">Partial upload batches</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* STAGE 4: DATA RECONCILIATION */}
                  {key === 'data_reconciliation' && (
                    <div>
                      {stage.details?.counts ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                          <div className="daily-ops-kpi-grid">
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Total Checks</span>
                              <span className="daily-ops-kpi-value">{stage.details.counts.total_checks}</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Passed Checks</span>
                              <span className="daily-ops-kpi-value" style={{ color: '#10b981' }}>
                                {stage.details.counts.pass_count}
                              </span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Warnings</span>
                              <span className="daily-ops-kpi-value" style={{ color: '#f59e0b' }}>
                                {stage.details.counts.warning_count}
                              </span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Failed Checks</span>
                              <span className="daily-ops-kpi-value" style={{ color: '#ef4444' }}>
                                {stage.details.counts.fail_count}
                              </span>
                            </div>
                          </div>

                          {stage.details.checks && stage.details.checks.length > 0 && (
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
                                  {stage.details.checks.map((chk) => (
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
                          Click "Run Downstream Pipeline" to execute cross-source reconciliation.
                        </p>
                      )}
                    </div>
                  )}

                  {/* STAGE 5: DAILY ANALYTICS */}
                  {key === 'daily_analytics' && (
                    <div>
                      {stage.details?.energy_summary ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                          <div className="daily-ops-kpi-grid">
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Total Electrical Energy</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.energy_summary?.total_consumption_kwh != null
                                  ? formatNumber(stage.details.energy_summary.total_consumption_kwh)
                                  : 'Unavailable'}
                              </span>
                              <span className="daily-ops-kpi-sub">kWh</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Total Energy Cost</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.energy_summary?.total_cost_inr != null
                                  ? formatCurrency(stage.details.energy_summary.total_cost_inr)
                                  : 'Unavailable'}
                              </span>
                              <span className="daily-ops-kpi-sub">INR (Application Tariff)</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Production Output</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.production_summary?.actual_qty != null
                                  ? formatNumber(stage.details.production_summary.actual_qty)
                                  : 'Unavailable'}
                              </span>
                              <span className="daily-ops-kpi-sub">
                                {stage.details.production_summary?.good_qty != null
                                  ? `Good: ${formatNumber(stage.details.production_summary.good_qty)} • Scrap: ${formatNumber(stage.details.production_summary.reject_qty || 0)}`
                                  : 'Output breakdown unavailable'}
                              </span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Avg Power Factor</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.power_factor?.avg_power_factor != null
                                  ? Number(stage.details.power_factor.avg_power_factor).toFixed(3)
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
                                {stage.details.process_sec?.smt_summary?.overall_process_sec_kwh_per_board != null
                                  ? Number(stage.details.process_sec.smt_summary.overall_process_sec_kwh_per_board).toFixed(4)
                                  : 'Unavailable'}
                              </span>
                              <span className="daily-ops-kpi-sub">kWh / PCB board</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">FAL Process SEC</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.process_sec?.fal_summary?.overall_process_sec_kwh_per_phone != null
                                  ? Number(stage.details.process_sec.fal_summary.overall_process_sec_kwh_per_phone).toFixed(4)
                                  : 'Unavailable'}
                              </span>
                              <span className="daily-ops-kpi-sub">kWh / phone</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Factory SEC</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.factory_sec?.factory_sec_data_available && stage.details.factory_sec?.factory_sec_kwh_per_finished_unit != null
                                  ? Number(stage.details.factory_sec.factory_sec_kwh_per_finished_unit).toFixed(4)
                                  : 'Unavailable'}
                              </span>
                              <span className="daily-ops-kpi-sub">
                                {stage.details.factory_sec?.factory_sec_data_available
                                  ? 'Plant Energy / FAL phones'
                                  : stage.details.factory_sec?.factory_sec_alignment_note || 'Alignment incomplete'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <p style={{ color: 'var(--text-secondary)' }}>
                          Click "Run Downstream Pipeline" to execute analytics calculations.
                        </p>
                      )}
                    </div>
                  )}

                  {/* STAGE 6: INTELLIGENCE REPORT */}
                  {key === 'intelligence_report' && (
                    <div>
                      {stage.details?.key_takeaways ? (
                        <div className="daily-ops-confirm-box" style={{ background: 'var(--bg-surface)' }}>
                          <h4 className="daily-ops-card-title">{stage.details.title}</h4>
                          <ul className="daily-ops-takeaway-list">
                            {stage.details.key_takeaways.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                          {stage.details.reconciliation_notes && (
                            <div className="daily-ops-alert-banner info" style={{ marginTop: '0.5rem' }}>
                              <span>{stage.details.reconciliation_notes}</span>
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
                  {key === 'anomaly_detection' && (
                    <div>
                      {stage.details ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                          <div className="daily-ops-kpi-grid">
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Statistical Outliers</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.counts_by_detector?.statistical_zscore || 0}
                              </span>
                              <span className="daily-ops-kpi-sub">Z-Score ({'>'} 3.0σ)</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Rolling Excursions</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.counts_by_detector?.rolling_baseline || 0}
                              </span>
                              <span className="daily-ops-kpi-sub">24-hour moving window</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Low Power Factor</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.counts_by_detector?.low_power_factor || 0}
                              </span>
                              <span className="daily-ops-kpi-sub">PF {'<'} 0.900</span>
                            </div>
                            <div className="daily-ops-kpi-card">
                              <span className="daily-ops-kpi-label">Standby Waste</span>
                              <span className="daily-ops-kpi-value">
                                {stage.details.counts_by_detector?.zero_production_standby || 0}
                              </span>
                              <span className="daily-ops-kpi-sub">0 line output intervals</span>
                            </div>
                          </div>

                          {stage.details.events && stage.details.events.length > 0 && (
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
                                  {stage.details.events.map((ev, i) => (
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
                          Click "Run Downstream Pipeline" to execute anomaly detection.
                        </p>
                      )}
                    </div>
                  )}

                  {/* STAGE 8: INVESTIGATION HANDOFF */}
                  {key === 'investigation_handoff' && (
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
                            disabled={syncingFindings}
                          >
                            {syncingFindings ? 'Syncing to Investigation Centre...' : 'Sync All to Investigation Centre'}
                          </button>
                        </div>
                      </div>

                      {stage.details?.items && stage.details.items.length > 0 ? (
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
                              {stage.details.items.map((item, i) => (
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
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

