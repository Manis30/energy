import React, { useState } from 'react';
import { formatDate } from '../../utils/formatters';
import KpiCard, { KpiGrid } from '../../components/common/KpiCard';

export default function ValidationReviewSection({
  validationResult,
  confirmedDate,
  setConfirmedDate,
  onRevalidateWithDate,
  validating,
}) {
  const [activeTab, setActiveTab] = useState('summary'); // 'summary' | 'errors' | 'preview'
  const [errorSearch, setErrorSearch] = useState('');

  if (!validationResult) return null;

  const { summary, errors = [], preview = [], detected_dates = [] } = validationResult;

  const filteredErrors = errors.filter((err) => {
    if (!errorSearch) return true;
    const q = errorSearch.toLowerCase();
    return (
      (err.column && err.column.toLowerCase().includes(q)) ||
      (err.error_type && err.error_type.toLowerCase().includes(q)) ||
      (err.message && err.message.toLowerCase().includes(q)) ||
      String(err.row_number).includes(q)
    );
  });

  return (
    <div className="reports-section-card">
      <div className="reports-card-header">
        <div>
          <h2 className="reports-card-title">2. Validation Summary & Date Confirmation</h2>
          <p className="reports-card-subtitle">
            Source schema alignment, domain constraints, foreign keys, and duplicate auditing.
          </p>
        </div>
      </div>

      {/* Date Detection and Confirmation Card */}
      <div className="reports-date-confirm-box">
        <div className="date-confirm-info">
          <div className="date-confirm-label">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            Automatic Reporting Date Detection:
          </div>
          <div className="date-confirm-detected">
            {detected_dates.length > 0 ? (
              <span>
                Detected Date(s): <strong>{detected_dates.join(', ')}</strong>
              </span>
            ) : (
              <span>No explicit timestamp date detected</span>
            )}
          </div>
        </div>

        <div className="date-confirm-input-group">
          <label htmlFor="confirm-reporting-date" className="filter-label">
            Confirmed Reporting Date:
          </label>
          <input
            id="confirm-reporting-date"
            type="date"
            className="reports-date-input"
            value={confirmedDate || ''}
            onChange={(e) => setConfirmedDate(e.target.value)}
          />
          <button
            type="button"
            className="reports-secondary-btn"
            onClick={onRevalidateWithDate}
            disabled={validating}
            title="Re-validate rows against this specific reporting date"
          >
            Re-check for Date
          </button>
        </div>
      </div>

      {/* KPI Validation Summary Badges */}
      <KpiGrid className="reports-kpi-grid" style={{ marginBottom: '1.25rem' }}>
        <KpiCard
          id="val-total"
          title="Total Records"
          value={summary.total_rows.toLocaleString()}
          accent="purple"
          minimal={true}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          }
        />
        <KpiCard
          id="val-valid"
          title="Valid for Ingestion"
          value={summary.valid_rows.toLocaleString()}
          accent="purple"
          minimal={true}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          }
        />
        <KpiCard
          id="val-dupes"
          title="Duplicates Detected"
          value={summary.duplicate_rows.toLocaleString()}
          accent="purple"
          minimal={true}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
              <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
            </svg>
          }
        />
        <KpiCard
          id="val-rejected"
          title="Rejected Records"
          value={summary.rejected_rows.toLocaleString()}
          accent="purple"
          minimal={true}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          }
        />
      </KpiGrid>

      {/* Scope Chips */}
      <div className="reports-scope-chips">
        {summary.plants_found?.length > 0 && (
          <div className="scope-chip">
            <span className="chip-key">Plants:</span>
            <span className="chip-val">{summary.plants_found.join(', ')}</span>
          </div>
        )}
        {summary.meters_found?.length > 0 && (
          <div className="scope-chip">
            <span className="chip-key">Meters ({summary.meters_found.length}):</span>
            <span className="chip-val">{summary.meters_found.join(', ')}</span>
          </div>
        )}
        {summary.lines_found?.length > 0 && (
          <div className="scope-chip">
            <span className="chip-key">Lines ({summary.lines_found.length}):</span>
            <span className="chip-val">{summary.lines_found.join(', ')}</span>
          </div>
        )}
      </div>

      {/* Reporting Coverage & Completeness Card */}
      <div className={`reports-coverage-box ${summary.coverage_status === 'PARTIAL' ? 'coverage-partial' : 'coverage-complete'}`}>
        <div className="coverage-header">
          <div className="coverage-title-row">
            <span className={`coverage-badge ${summary.coverage_status === 'PARTIAL' ? 'badge-warning' : 'badge-success'}`}>
              {summary.coverage_status === 'PARTIAL' ? 'Partial Reporting Coverage' : 'Complete 24-Hour Coverage'}
            </span>
            <span className="coverage-subtitle">
              {summary.coverage_status === 'PARTIAL'
                ? `Operational Telemetry: ${summary.completeness?.hours_reported || 0} of 24 hourly intervals reported (${summary.missing_hours?.length || 0} hours unrecorded)`
                : 'All 24 hourly operating intervals and registered master entities are represented'}
            </span>
          </div>
        </div>

        {summary.coverage_status === 'PARTIAL' && (
          <div className="coverage-details">
            {summary.missing_hours?.length > 0 && (
              <div className="coverage-item">
                <strong>Missing Hourly Intervals:</strong>{' '}
                <span>
                  {summary.missing_hours.map((h) => `${String(h).padStart(2, '0')}:00`).join(', ')}
                </span>
              </div>
            )}
            {summary.missing_entities?.length > 0 && (
              <div className="coverage-item">
                <strong>Missing Expected {summary.report_type === 'ENERGY' ? 'Submeters' : 'Production Lines'}:</strong>{' '}
                <span>{summary.missing_entities.join(', ')}</span>
              </div>
            )}
            {summary.limitations?.length > 0 && (
              <div className="coverage-limitations">
                <strong>Analytics Impact &amp; Limitations:</strong>
                <ul>
                  {summary.limitations.map((lim, idx) => (
                    <li key={idx}>{lim}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="coverage-note">
              <em>Coverage Distinction:</em> Incomplete reporting coverage represents unrecorded operating intervals, distinct from rejected rows ({summary.rejected_rows}) which failed schema/range checks.
            </div>
          </div>
        )}
      </div>

      {/* Sub-Tabs: Validation Errors vs Data Preview */}
      <div className="reports-subtab-bar">
        <button
          type="button"
          className={`reports-subtab-btn ${activeTab === 'summary' ? 'active' : ''}`}
          onClick={() => setActiveTab('summary')}
        >
          Validation Status
        </button>
        <button
          type="button"
          className={`reports-subtab-btn ${activeTab === 'errors' ? 'active' : ''}`}
          onClick={() => setActiveTab('errors')}
        >
          Validation Issues ({errors.length})
        </button>
        <button
          type="button"
          className={`reports-subtab-btn ${activeTab === 'preview' ? 'active' : ''}`}
          onClick={() => setActiveTab('preview')}
        >
          Data Preview ({preview.length} rows)
        </button>
      </div>

      {/* Subtab 1: Status Overview */}
      {activeTab === 'summary' && (
        <div className="reports-status-summary">
          {summary.is_ready_for_ingest ? (
            <div className="reports-alert-box alert-success">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <div>
                <strong>Report Ready for Ingestion.</strong> {summary.valid_rows} records validated successfully for {formatDate(confirmedDate)}.
                {summary.duplicate_rows > 0 && ` ${summary.duplicate_rows} duplicate records will be handled according to your selected ingestion mode.`}
              </div>
            </div>
          ) : (
            <div className="reports-alert-box alert-danger">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <div>
                <strong>Report Cannot Be Ingested.</strong> 0 valid records found. Please review the {errors.length} validation issues below.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Subtab 2: Specific Validation Issues */}
      {activeTab === 'errors' && (
        <div className="reports-errors-panel">
          {errors.length === 0 ? (
            <div className="reports-empty-panel">No validation errors detected. All rows satisfy database constraints.</div>
          ) : (
            <>
              <div className="table-search-bar">
                <input
                  type="text"
                  placeholder="Filter errors by column, rule, or row #..."
                  value={errorSearch}
                  onChange={(e) => setErrorSearch(e.target.value)}
                  className="table-search-input"
                />
                <span className="search-count">Showing {filteredErrors.length} of {errors.length} issues</span>
              </div>
              <div className="table-responsive">
                <table className="anomaly-table">
                  <thead>
                    <tr>
                      <th style={{ width: '80px' }}>Row #</th>
                      <th style={{ width: '140px' }}>Column</th>
                      <th style={{ width: '160px' }}>Error Type</th>
                      <th>Validation Rule Issue</th>
                      <th style={{ width: '120px' }}>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredErrors.map((err, i) => (
                      <tr key={i}>
                        <td className="timestamp-cell">
                          {err.row_number === 0 ? 'Header' : `Row ${err.row_number}`}
                        </td>
                        <td>
                          <code>{err.column || 'general'}</code>
                        </td>
                        <td>
                          <span className="error-type-tag">{err.error_type}</span>
                        </td>
                        <td style={{ color: 'var(--status-danger)', fontWeight: 500 }}>
                          {err.message}
                        </td>
                        <td className="timestamp-cell">
                          {err.value !== null && err.value !== undefined ? String(err.value) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* Subtab 3: Data Preview */}
      {activeTab === 'preview' && (
        <div className="reports-preview-panel">
          <div className="table-responsive">
            <table className="anomaly-table">
              <thead>
                <tr>
                  <th style={{ width: '70px' }}>Row</th>
                  <th style={{ width: '90px' }}>Status</th>
                  {preview[0] &&
                    Object.keys(preview[0].data).map((k) => (
                      <th key={k}>{k}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {preview.map((p) => (
                  <tr key={p.row_number}>
                    <td className="timestamp-cell">{p.row_number}</td>
                    <td>
                      <span className={`status-pill pill-${p.status.toLowerCase()}`}>
                        {p.status}
                      </span>
                    </td>
                    {Object.entries(p.data).map(([k, v]) => (
                      <td key={k} className="timestamp-cell">
                        {String(v ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

