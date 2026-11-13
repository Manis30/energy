import React from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

export default function AnomalySection({ anomaliesData, dataAvailable = true }) {
  const totalAnomalies = hasNumber(anomaliesData?.total_anomalies_detected)
    ? Number(anomaliesData.total_anomalies_detected)
    : null;
  const zscoreStats = anomaliesData?.statistical_zscore;
  const rollingStats = anomaliesData?.rolling_baseline;
  const pfStats = anomaliesData?.low_power_factor;
  const standbyStats = anomaliesData?.zero_production_standby;

  // Extract top/recent anomalies across detectors for display table
  const statAnomalies = zscoreStats?.anomalies || [];
  const rollingAnomalies = rollingStats?.anomalies || [];
  const standbyAnomalies = standbyStats?.anomalies || [];

  // Combine and sample top severe anomalies
  const combinedSample = [
    ...rollingAnomalies.slice(0, 3),
    ...statAnomalies.slice(0, 3),
  ].sort((a, b) => (
    (hasNumber(b.deviation_score) ? Math.abs(Number(b.deviation_score)) : -1)
    - (hasNumber(a.deviation_score) ? Math.abs(Number(a.deviation_score)) : -1)
  ));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Automated Operational Anomaly Monitoring</h3>
          <p className="section-desc">
            Returned detector flags from energy, power-factor, and zero-output analytics. Flags are not confirmed equipment faults or proof of avoidable waste.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag anomaly-count">
            {totalAnomalies === null
              ? 'Detector flag count unavailable'
              : `${totalAnomalies} detector flag(s) · may overlap`}
          </span>
        </div>
      </div>

      {!dataAvailable && (
        <div className="chart-empty-state">
          Anomaly analysis request failed. No conclusion about the presence or absence of anomalies is available.
        </div>
      )}

      {/* 4 Summary Stat Cards */}
      <div className="anomaly-summary-grid">
        <div className="anomaly-stat-card">
          <div className="anomaly-stat-icon purple">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 20V10"/>
              <path d="M12 20V4"/>
              <path d="M6 20v-6"/>
            </svg>
          </div>
          <div className="anomaly-stat-info">
            <span className="anomaly-stat-label">Statistical Z-Score (Spikes/Drops)</span>
            <span className="anomaly-stat-val">
              {hasNumber(zscoreStats?.total_anomalies_detected)
                ? formatNumber(zscoreStats.total_anomalies_detected)
                : 'Unavailable'}
            </span>
            <span className="anomaly-stat-sub">
              {hasNumber(zscoreStats?.threshold_z)
                ? `|Z| ≥ ${Number(zscoreStats.threshold_z).toFixed(1)}σ`
                : 'Z-score threshold unavailable'}
            </span>
          </div>
        </div>

        <div className="anomaly-stat-card">
          <div className="anomaly-stat-icon blue">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div className="anomaly-stat-info">
            <span className="anomaly-stat-label">Rolling Baseline Deviations</span>
            <span className="anomaly-stat-val">
              {hasNumber(rollingStats?.total_anomalies_detected)
                ? formatNumber(rollingStats.total_anomalies_detected)
                : 'Unavailable'}
            </span>
            <span className="anomaly-stat-sub">
              {hasNumber(rollingStats?.window_size_hours)
                ? `Prior ${formatNumber(rollingStats.window_size_hours)}-hour window (current excluded)`
                : 'Rolling window duration unavailable'}
            </span>
          </div>
        </div>

        <div className="anomaly-stat-card">
          <div className="anomaly-stat-icon green">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div className="anomaly-stat-info">
            <span className="anomaly-stat-label">Power Factor Threshold Monitoring</span>
            <span className={`anomaly-stat-val ${hasNumber(pfStats?.total_anomalies_detected) && Number(pfStats.total_anomalies_detected) > 0 ? 'text-danger' : ''}`}>
              {hasNumber(pfStats?.total_anomalies_detected)
                ? `${formatNumber(pfStats.total_anomalies_detected)} low-PF flag(s)`
                : 'Unavailable'}
            </span>
            <span className="anomaly-stat-sub">
              {hasNumber(pfStats?.threshold) ? `Application threshold: PF < ${Number(pfStats.threshold).toFixed(2)}` : 'Threshold unavailable'}
            </span>
          </div>
        </div>

        <div className="anomaly-stat-card">
          <div className="anomaly-stat-icon orange">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2"/>
              <line x1="9" y1="9" x2="15" y2="15"/>
              <line x1="15" y1="9" x2="9" y2="15"/>
            </svg>
          </div>
          <div className="anomaly-stat-info">
            <span className="anomaly-stat-label">Energy During Zero-Output Intervals</span>
            <span className="anomaly-stat-val">
              {hasNumber(standbyStats?.total_standby_energy_kwh)
                ? `${formatNumber(standbyStats.total_standby_energy_kwh, 2)} kWh`
                : 'Unavailable'}
            </span>
            <span className="anomaly-stat-sub">
              {hasNumber(standbyStats?.total_stoppage_minutes)
                ? `${formatNumber(standbyStats.total_stoppage_minutes)} min reported downtime in flagged intervals; this does not establish avoidable waste`
                : 'Zero-output observation context unavailable'}
            </span>
          </div>
        </div>
      </div>

      {/* Recent Significant Anomalies Table */}
      <div className="anomaly-table-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Recent Significant Deviations</h4>
            <span className="chart-card-subtitle">
              Returned statistical/rolling observations for human review; references are detector-specific, not expected-energy baselines.
            </span>
          </div>
          <span className="anomaly-audit-note">
            Automated Audit • Read-Only
          </span>
        </div>

        <div className="table-responsive">
          <table className="anomaly-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Plant & Meter</th>
                <th>Anomaly Type</th>
                <th>Severity</th>
                <th>Measured Value</th>
                <th>Detector Reference</th>
                <th>Deviation</th>
                <th>Deterministic Explanation</th>
              </tr>
            </thead>
            <tbody>
              {!dataAvailable || combinedSample.length === 0 ? (
                <tr>
                  <td colSpan="8" className="empty-table-cell">
                    {!dataAvailable
                      ? 'Anomaly details unavailable.'
                      : 'No statistical or rolling detail records were returned; other detector flags may still exist.'}
                  </td>
                </tr>
              ) : (
                combinedSample.map((item, idx) => (
                  <tr key={idx} className={`severity-row ${item.severity?.toLowerCase()}`}>
                    <td className="timestamp-cell">{formatDateTime(item.timestamp)}</td>
                    <td className="meter-cell">
                      <span className="badge-plant">{item.plant_id}</span>
                      <span className="badge-meter">{item.meter_id || item.line_id}</span>
                    </td>
                    <td>
                      <span className="type-badge">{item.anomaly_type?.replace(/_/g, ' ')}</span>
                    </td>
                    <td>
                      <span className={`severity-badge ${item.severity?.toLowerCase()}`}>
                        {item.severity}
                      </span>
                    </td>
                    <td className="numeric-cell">
                      {hasNumber(item.actual_value) ? `${formatNumber(item.actual_value, 2)} kWh` : 'Unavailable'}
                    </td>
                    <td className="numeric-cell">
                      {hasNumber(item.baseline_value) ? `${formatNumber(item.baseline_value, 2)} kWh` : 'Unavailable'}
                    </td>
                    <td className="numeric-cell font-mono">
                      {hasNumber(item.deviation_score)
                        ? Number(item.deviation_score) > 0
                          ? `+${Number(item.deviation_score).toFixed(2)}σ`
                          : `${Number(item.deviation_score).toFixed(2)}σ`
                        : 'Unavailable'}
                    </td>
                    <td className="explanation-cell" title={item.explanation}>
                      {item.explanation}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

