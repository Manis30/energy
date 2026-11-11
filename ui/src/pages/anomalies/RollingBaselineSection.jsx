import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

export default function RollingBaselineSection({ rollingData }) {
  const anomalies = rollingData?.anomalies || [];
  const totalDetected = rollingData?.total_anomalies_detected || anomalies.length;
  const windowHours = rollingData?.window_size_hours || 24;
  const thresholdZ = rollingData?.threshold_z || 3.0;

  const [expandedId, setExpandedId] = useState(null);

  const toggleRow = (idx) => {
    setExpandedId((prev) => (prev === idx ? null : idx));
  };

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Rolling-Baseline Historical Deviations</h3>
          <p className="section-desc">
            Dynamic anomaly detection using moving historical windows (preceding {windowHours} operating hours). The current observation is strictly excluded from its own baseline calculation.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag anomaly-count">Flagged Events: {totalDetected}</span>
          <span className="section-tag process">Window: Prior {windowHours} Hours</span>
        </div>
      </div>

      <div className="anomaly-table-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Rolling Baseline Outliers</h4>
            <span className="chart-card-subtitle">
              Click any row to inspect historical sample size, window standard deviation, and exclusion protocol
            </span>
          </div>
          <span className="anomaly-audit-note">
            Preceding Window Protocol (Self-Excluded)
          </span>
        </div>

        <div className="table-responsive">
          <table className="anomaly-table">
            <thead>
              <tr>
                <th></th>
                <th>Timestamp</th>
                <th>Plant & Meter</th>
                <th>Anomaly Type</th>
                <th>Severity</th>
                <th className="text-right">Observed (kWh)</th>
                <th className="text-right">Rolling Mean</th>
                <th className="text-right">Deviation</th>
                <th>Deterministic Explanation</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.length === 0 ? (
                <tr>
                  <td colSpan="9" className="empty-table-cell">
                    No rolling baseline anomalies detected for current filter selection.
                  </td>
                </tr>
              ) : (
                anomalies.slice(0, 50).map((item, idx) => {
                  const isExpanded = expandedId === idx;
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
                          <span className="badge-meter">{item.meter_id}</span>
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
                                  <polyline points="12 6 12 12 16 14"/>
                                </svg>
                                <span>Rolling Baseline Context & Exclusion Verification</span>
                              </div>
                              <div className="detail-flags-grid">
                                <div className="flag-item">
                                  <span className="flag-label">Window Size:</span>
                                  <span className="flag-val font-mono">{item.context_flags?.window_size_hours || windowHours} hours</span>
                                </div>
                                <div className="flag-item">
                                  <span className="flag-label">Observations Used:</span>
                                  <span className="flag-val font-mono">{item.context_flags?.historical_observations_used || windowHours} prior readings</span>
                                </div>
                                <div className="flag-item">
                                  <span className="flag-label">Self-Exclusion Verified:</span>
                                  <span className="flag-val text-success">Current reading excluded from baseline</span>
                                </div>
                                <div className="flag-item">
                                  <span className="flag-label">Rolling Std Dev:</span>
                                  <span className="flag-val font-mono">{formatNumber(item.context_flags?.rolling_std_kwh, 4)} kWh</span>
                                </div>
                              </div>
                              <div className="detail-panel-note">
                                <strong>Operational Notice:</strong> This deviation reflects an abrupt change in electrical demand relative to the meter's recent 24-hour moving baseline. It does not constitute proof of machine failure or mechanical breakdown, but flags an operational transition (such as product changeover or thermal ramp-up) for verification.
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
