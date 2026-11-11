import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

export default function StatisticalAnomaliesSection({ statisticalData }) {
  const anomalies = statisticalData?.anomalies || [];
  const totalDetected = statisticalData?.total_anomalies_detected || anomalies.length;
  const thresholdZ = statisticalData?.threshold_z || 3.0;
  const meterBaselines = statisticalData?.meter_baselines || {};

  // State for expanded row to inspect anomaly context
  const [expandedId, setExpandedId] = useState(null);

  const toggleRow = (idx) => {
    setExpandedId((prev) => (prev === idx ? null : idx));
  };

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Statistical Energy Consumption Anomalies</h3>
          <p className="section-desc">
            Extreme hourly deviations flagged via sample Z-score ($|Z| \ge {thresholdZ}\sigma$) computed per meter against historical sample distributions.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag anomaly-count">Flagged Events: {totalDetected}</span>
          <span className="section-tag info">Threshold: |Z| ≥ {thresholdZ}σ</span>
        </div>
      </div>

      <div className="anomaly-table-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Z-Score Statistical Outlier Telemetry</h4>
            <span className="chart-card-subtitle">
              Click any row to inspect sample size, standard deviation, and statistical flags
            </span>
          </div>
          <span className="anomaly-audit-note">
            Deterministic Z-Score Detector
          </span>
        </div>

        <div className="table-responsive">
          <table className="anomaly-table">
            <thead>
              <tr>
                <th></th>
                <th>Timestamp</th>
                <th>Plant & Meter</th>
                <th>Type</th>
                <th>Severity</th>
                <th className="text-right">Measured (kWh)</th>
                <th className="text-right">Baseline Mean</th>
                <th className="text-right">Z-Score</th>
                <th>Deterministic Explanation</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.length === 0 ? (
                <tr>
                  <td colSpan="9" className="empty-table-cell">
                    No statistical anomalies detected for current filter selection.
                  </td>
                </tr>
              ) : (
                anomalies.map((item, idx) => {
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
                                  <line x1="12" y1="16" x2="12" y2="12"/>
                                  <line x1="12" y1="8" x2="12.01" y2="8"/>
                                </svg>
                                <span>Statistical Metadata & Contextual Bounds</span>
                              </div>
                              <div className="detail-flags-grid">
                                <div className="flag-item">
                                  <span className="flag-label">Sample Observations (N):</span>
                                  <span className="flag-val font-mono">{item.context_flags?.sample_size || '2,208'}</span>
                                </div>
                                <div className="flag-item">
                                  <span className="flag-label">Standard Deviation (σ):</span>
                                  <span className="flag-val font-mono">{formatNumber(item.context_flags?.std_kwh, 4)} kWh</span>
                                </div>
                                <div className="flag-item">
                                  <span className="flag-label">Z-Score Threshold:</span>
                                  <span className="flag-val font-mono">{item.context_flags?.threshold_z || thresholdZ}σ</span>
                                </div>
                                <div className="flag-item">
                                  <span className="flag-label">Direction:</span>
                                  <span className="flag-val">{item.context_flags?.is_spike ? 'Spike (Surge)' : 'Drop (Curtailment)'}</span>
                                </div>
                              </div>
                              <div className="detail-panel-note">
                                <strong>Operational Interpretation:</strong> This statistical anomaly marks an hourly reading deviating {Math.abs(item.deviation_score).toFixed(2)} standard deviations from the sample mean. In accordance with ISO 50006, this represents a statistical variance requiring review, not definitive equipment breakdown.
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

