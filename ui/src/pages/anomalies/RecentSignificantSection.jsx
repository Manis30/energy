import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

export default function RecentSignificantSection({ statData, rollingData }) {
  const statList = statData?.anomalies || [];
  const rollList = rollingData?.anomalies || [];

  // Combine and sort by deviation magnitude (|deviation_score| descending)
  const allSignificant = [...statList, ...rollList].sort(
    (a, b) => Math.abs(b.deviation_score) - Math.abs(a.deviation_score)
  );

  const [expandedId, setExpandedId] = useState(null);

  const toggleRow = (idx) => {
    setExpandedId((prev) => (prev === idx ? null : idx));
  };

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Highest-Magnitude Statistical Exceptions</h3>
          <p className="section-desc">
            Ranked view of the largest statistical deviations recorded across all meters and monitoring windows.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag scrap">Top 15 Significant Events</span>
        </div>
      </div>

      <div className="anomaly-table-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Priority Investigation Queue</h4>
            <span className="chart-card-subtitle">
              Ranked strictly by mathematical Z-score deviation magnitude (|Z| descending)
            </span>
          </div>
          <span className="anomaly-audit-note">
            Automated Exception Ranking
          </span>
        </div>

        <div className="table-responsive">
          <table className="anomaly-table">
            <thead>
              <tr>
                <th></th>
                <th>Timestamp</th>
                <th>Plant & Meter</th>
                <th>Detector</th>
                <th>Severity</th>
                <th className="text-right">Measured (kWh)</th>
                <th className="text-right">Baseline Mean</th>
                <th className="text-right">Magnitude</th>
                <th>Deterministic Explanation</th>
              </tr>
            </thead>
            <tbody>
              {allSignificant.length === 0 ? (
                <tr>
                  <td colSpan="9" className="empty-table-cell">
                    No significant anomalies to display.
                  </td>
                </tr>
              ) : (
                allSignificant.slice(0, 15).map((item, idx) => {
                  const isExpanded = expandedId === idx;
                  const isCritical = item.severity === 'CRITICAL';
                  const zFormatted = item.deviation_score > 0
                    ? `+${item.deviation_score.toFixed(2)}σ`
                    : `${item.deviation_score.toFixed(2)}σ`;

                  return (
                    <React.Fragment key={idx}>
                      <tr
                        className={`anomaly-data-row severity-row ${item.severity?.toLowerCase()} ${isExpanded ? 'is-expanded' : ''}`}
                        onClick={() => toggleRow(idx)}
                        style={{ cursor: 'pointer' }}
                        title="Click to view detailed context flags"
                      >
                        <td className="expand-indicator-cell">
                          <span className={`expand-chevron ${isExpanded ? 'open' : ''}`}>›</span>
                        </td>
                        <td className="timestamp-cell">{formatDateTime(item.timestamp)}</td>
                        <td className="meter-cell">
                          <span className="badge-plant">{item.plant_id}</span>
                          <span className="badge-meter">{item.meter_id || item.line_id}</span>
                        </td>
                        <td>
                          <span className="type-badge">
                            {item.anomaly_type?.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td>
                          <span className={`severity-badge ${item.severity?.toLowerCase()}`}>
                            {item.severity}
                          </span>
                        </td>
                        <td className="numeric-cell text-right font-mono font-semibold">
                          {formatNumber(item.actual_value, 2)}
                        </td>
                        <td className="numeric-cell text-right font-mono">
                          {formatNumber(item.baseline_value, 2)}
                        </td>
                        <td className="numeric-cell text-right font-mono font-bold">
                          {zFormatted}
                        </td>
                        <td className="explanation-cell" title={item.explanation}>
                          {item.explanation}
                        </td>
                      </tr>

                      {/* Expandable Detail Panel */}
                      {isExpanded && (
                        <tr className="anomaly-detail-row">
                          <td colSpan="9">
                            <div className="anomaly-detail-panel">
                              <div className="detail-panel-title">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <circle cx="12" cy="12" r="10"/>
                                  <line x1="12" y1="8" x2="12" y2="12"/>
                                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                                </svg>
                                <span>Detection Flags & Operational Metadata</span>
                              </div>
                              <div className="detail-flags-grid">
                                {Object.entries(item.context_flags || {}).map(([key, val]) => (
                                  <div key={key} className="flag-item">
                                    <span className="flag-label">{key.replace(/_/g, ' ')}:</span>
                                    <span className="flag-val font-mono">
                                      {typeof val === 'boolean' ? (val ? 'True' : 'False') : String(val)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                              <div className="detail-panel-note">
                                <strong>Deterministic Investigation Guidance:</strong> This measurement was identified with statistical certainty as a deviation from expected interval load. Review line production logs and utility logs during this exact hour to determine operational context.
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
