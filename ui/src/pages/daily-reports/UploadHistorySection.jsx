import React, { useState, useEffect, useCallback } from 'react';
import { dailyReportsApi } from '../../services/dailyReportsApi';
import { formatDate } from '../../utils/formatters';

export default function UploadHistorySection({ refreshTrigger }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [dateFilter, setDateFilter] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dailyReportsApi.getUploadHistory({
        reportType: typeFilter || undefined,
        reportingDate: dateFilter || undefined,
        limit: 50,
      });
      setHistory(data || []);
    } catch (err) {
      console.error('Failed to load upload history:', err);
      setError(err.message || 'Unable to load upload history from database.');
    } finally {
      setLoading(false);
    }
  }, [typeFilter, dateFilter]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshTrigger]);

  const toggleExpand = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const formatTimestamp = (ts) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } catch {
      return String(ts);
    }
  };

  return (
    <div className="reports-section-card">
      <div className="reports-card-header">
        <div>
          <h2 className="reports-card-title">Upload History & Import Audit Log</h2>
          <p className="reports-card-subtitle">
            Immutable log of all operational report uploads, record counts, and database commits.
          </p>
        </div>
        <button
          type="button"
          className="reports-secondary-btn"
          onClick={fetchHistory}
          disabled={loading}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10"/>
            <polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          Refresh Audit Log
        </button>
      </div>

      {/* History Filters */}
      <div className="history-filters-bar">
        <div className="filter-item">
          <label className="filter-label">Filter Category:</label>
          <div className="custom-select-wrapper">
            <select
              className="factory-scope-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">All Categories</option>
              <option value="ENERGY">Energy Telemetry</option>
              <option value="PRODUCTION">Production Facts</option>
            </select>
            <span className="select-arrow" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </span>
          </div>
        </div>

        <div className="filter-item">
          <label className="filter-label">Reporting Date:</label>
          <input
            type="date"
            className="reports-date-input"
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
          />
          {dateFilter && (
            <button
              type="button"
              className="clear-date-btn"
              onClick={() => setDateFilter('')}
              title="Clear date filter"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="dashboard-loading-state" style={{ minHeight: '180px' }}>
          <div className="loading-spinner" />
          <div className="loading-subtitle">Querying upload audit records...</div>
        </div>
      ) : error ? (
        <div className="reports-error-banner">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{error}</span>
        </div>
      ) : history.length === 0 ? (
        <div className="reports-empty-panel">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          <p>No upload history records found matching criteria.</p>
        </div>
      ) : (
        <div className="table-responsive">
          <table className="anomaly-table">
            <thead>
              <tr>
                <th style={{ width: '150px' }}>Uploaded At</th>
                <th style={{ width: '130px' }}>Upload ID</th>
                <th style={{ width: '100px' }}>Category</th>
                <th style={{ width: '110px' }}>Reporting Date</th>
                <th>File / Source</th>
                <th style={{ textAlign: 'right' }}>Total</th>
                <th style={{ textAlign: 'right', color: 'var(--status-success)' }}>Imported</th>
                <th style={{ textAlign: 'right', color: 'var(--status-warning)' }}>Duplicates</th>
                <th style={{ textAlign: 'right', color: 'var(--status-danger)' }}>Rejected</th>
                <th style={{ width: '100px' }}>Mode</th>
                <th style={{ width: '90px' }}>Status</th>
                <th style={{ width: '50px' }}>Details</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => (
                <React.Fragment key={item.id}>
                  <tr>
                    <td className="timestamp-cell">{formatTimestamp(item.uploaded_at)}</td>
                    <td className="timestamp-cell">
                      <code>{item.upload_id}</code>
                    </td>
                    <td>
                      <span className={`category-tag cat-${item.report_type.toLowerCase()}`}>
                        {item.report_type}
                      </span>
                    </td>
                    <td>
                      <strong>{formatDate(item.reporting_date)}</strong>
                    </td>
                    <td>
                      <div className="history-file-title" title={item.filename}>
                        {item.filename}
                      </div>
                      {item.sheet_name && (
                        <div className="history-file-sub">Sheet: {item.sheet_name}</div>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }} className="timestamp-cell">
                      {item.total_rows}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--status-success)' }}>
                      {item.valid_rows}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--status-warning)' }}>
                      {item.duplicate_rows}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--status-danger)' }}>
                      {item.rejected_rows}
                    </td>
                    <td>
                      <span className="mode-tag">{item.mode === 'OVERWRITE_CORRECTION' ? 'Correction' : 'Incremental'}</span>
                    </td>
                    <td>
                      <span className={`status-pill pill-${item.status.toLowerCase()}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="details-expand-btn"
                        onClick={() => toggleExpand(item.id)}
                        title="View audit details"
                      >
                        {expandedId === item.id ? '▲' : '▼'}
                      </button>
                    </td>
                  </tr>
                  {expandedId === item.id && (
                    <tr className="history-expanded-row">
                      <td colSpan="12">
                        <div className="audit-details-box">
                          <div className="audit-header">Audit Metadata & Diagnostics:</div>
                          <pre className="audit-json">
                            {(() => {
                              try {
                                return JSON.stringify(JSON.parse(item.audit_details || '{}'), null, 2);
                              } catch {
                                return item.audit_details || 'No detailed log recorded.';
                              }
                            })()}
                          </pre>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

