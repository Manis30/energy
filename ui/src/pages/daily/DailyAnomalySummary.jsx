import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

export default function DailyAnomalySummary({ anomaliesData }) {
  const [filterSeverity, setFilterSeverity] = useState('ALL');

  const totalAnomalies = anomaliesData ? anomaliesData.total_anomalies_detected : 0;
  const statData = anomaliesData?.statistical_zscore;
  const rollData = anomaliesData?.rolling_baseline;
  const lpfData = anomaliesData?.low_power_factor;
  const standbyData = anomaliesData?.zero_production_standby;

  const statAnomalies = statData?.anomalies || [];
  const rollAnomalies = rollData?.anomalies || [];
  const lpfAnomalies = lpfData?.anomalies || [];
  const standbyAnomalies = standbyData?.anomalies || [];

  // Combine and deduplicate or list all detector occurrences with detector tags
  const allIncidents = [
    ...statAnomalies.map((a) => ({ ...a, detector: 'Statistical Z-Score' })),
    ...rollAnomalies.map((a) => ({ ...a, detector: 'Rolling Baseline' })),
    ...lpfAnomalies.map((a) => ({ ...a, detector: 'Low Power Factor' })),
    ...standbyAnomalies.map((a) => ({ ...a, detector: 'Zero-Production Standby' })),
  ];

  // Severity counts
  let criticalCount = 0;
  let highCount = 0;
  let mediumCount = 0;
  let lowCount = 0;

  allIncidents.forEach((item) => {
    const sev = (item.severity || 'LOW').toUpperCase();
    if (sev === 'CRITICAL') criticalCount++;
    else if (sev === 'HIGH') highCount++;
    else if (sev === 'MEDIUM') mediumCount++;
    else lowCount++;
  });

  const filteredIncidents = filterSeverity === 'ALL'
    ? allIncidents
    : allIncidents.filter((item) => (item.severity || 'LOW').toUpperCase() === filterSeverity);

  return (
    <div className="dashboard-section daily-anomaly-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Anomaly Summary</h3>
          <p className="section-desc">
            Automated exception detection across statistical Z-score, rolling baseline, low power factor, and idle standby energy.
          </p>
        </div>
        <div className="section-tag-group">
          <span className={`section-tag ${totalAnomalies > 0 ? 'anomaly-count' : 'info'}`}>
            {totalAnomalies} Total Flagged Records
          </span>
        </div>
      </div>

      {/* Top 4 Detector Summary Cards */}
      <div className="daily-detector-grid">
        {/* Detector 1: Statistical Z-Score */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Statistical Z-Score</span>
            <span className={`detector-status-pill ${statData?.total_anomalies_detected > 0 ? 'alert' : 'nominal'}`}>
              {statData?.total_anomalies_detected > 0 ? `${statData.total_anomalies_detected} Flagged` : 'Nominal'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(statData?.total_anomalies_detected || 0)}
            <span className="detector-unit">records</span>
          </div>
          <div className="detector-meta">
            <span>Threshold: |Z| ≥ {statData?.threshold_z || '3.0'}σ</span>
            <span>Min Samples: {statData?.min_observations || 10}</span>
          </div>
          <div className="detector-desc">
            Flags extreme deviations relative to historical meter distribution.
          </div>
        </div>

        {/* Detector 2: Rolling Baseline */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Rolling Baseline</span>
            <span className={`detector-status-pill ${rollData?.total_anomalies_detected > 0 ? 'alert' : 'nominal'}`}>
              {rollData?.total_anomalies_detected > 0 ? `${rollData.total_anomalies_detected} Flagged` : 'Nominal'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(rollData?.total_anomalies_detected || 0)}
            <span className="detector-unit">records</span>
          </div>
          <div className="detector-meta">
            <span>Window: {rollData?.window_size_hours || 24} hours</span>
            <span>Threshold: {rollData?.threshold_z || '3.0'}σ</span>
          </div>
          <div className="detector-desc">
            Detects dynamic shifts against preceding 24-hour historical window.
          </div>
        </div>

        {/* Detector 3: Low Power Factor */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Low Power Factor</span>
            <span className={`detector-status-pill ${lpfData?.total_anomalies_detected > 0 ? 'alert' : 'nominal'}`}>
              {lpfData?.total_anomalies_detected > 0 ? `${lpfData.total_anomalies_detected} Events` : 'Within threshold'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(lpfData?.total_anomalies_detected || 0)}
            <span className="detector-unit">events</span>
          </div>
          <div className="detector-meta">
            <span>Detection Threshold: &lt; {lpfData?.threshold || '0.90'} PF</span>
            <span>Application Threshold Check: Active</span>
          </div>
          <div className="detector-desc">
            Monitors hourly power factor against application detection threshold (0.90).
          </div>
        </div>

        {/* Detector 4: Zero-Production Standby */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Zero-Production Standby</span>
            <span className={`detector-status-pill ${standbyData?.total_events_detected > 0 ? 'notice' : 'nominal'}`}>
              {standbyData?.total_events_detected > 0 ? `${standbyData.total_events_detected} Stoppages` : 'None'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(standbyData?.total_standby_energy_kwh || 0, 1)}
            <span className="detector-unit">kWh recorded</span>
          </div>
          <div className="detector-meta">
            <span>Events: {standbyData?.total_events_detected || 0}</span>
            <span>Stoppage: {formatNumber(standbyData?.total_stoppage_minutes || 0)} min</span>
          </div>
          <div className="detector-desc">
            Process-meter energy recorded during zero-output line stoppages.
          </div>
        </div>
      </div>

      {/* Severity Breakdown Bar */}
      <div className="daily-severity-bar">
        <div className="severity-bar-title">Severity Distribution:</div>
        <div className="severity-tags-group">
          <button
            type="button"
            className={`severity-filter-btn ${filterSeverity === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('ALL')}
          >
            All ({allIncidents.length})
          </button>
          <button
            type="button"
            className={`severity-filter-btn crit ${filterSeverity === 'CRITICAL' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('CRITICAL')}
          >
            Critical ({criticalCount})
          </button>
          <button
            type="button"
            className={`severity-filter-btn high ${filterSeverity === 'HIGH' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('HIGH')}
          >
            High ({highCount})
          </button>
          <button
            type="button"
            className={`severity-filter-btn med ${filterSeverity === 'MEDIUM' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('MEDIUM')}
          >
            Medium ({mediumCount})
          </button>
          <button
            type="button"
            className={`severity-filter-btn low ${filterSeverity === 'LOW' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('LOW')}
          >
            Low ({lowCount})
          </button>
        </div>
      </div>

      {/* Incident Detail Table */}
      <div className="daily-incident-table-wrapper">
        {filteredIncidents.length === 0 ? (
          <div className="no-anomalies-banner">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <div>
              <strong>No Anomalies Detected in Filter Selection</strong>
              <p>All monitored meters and production lines operated within nominal tolerances on this date.</p>
            </div>
          </div>
        ) : (
          <div className="custom-table-container">
            <table className="custom-table daily-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Meter / Line</th>
                  <th>Detector Module</th>
                  <th>Severity</th>
                  <th>Recorded vs Baseline</th>
                  <th>Operational Finding</th>
                </tr>
              </thead>
              <tbody>
                {filteredIncidents.map((incident, idx) => {
                  const sev = (incident.severity || 'LOW').toUpperCase();
                  const targetEntity = incident.line_id
                    ? `${incident.line_id} (${incident.meter_id || 'MTR'})`
                    : (incident.meter_id || incident.plant_id || 'System');
                  return (
                    <tr key={`inc-${idx}-${incident.timestamp}-${incident.meter_id}`}>
                      <td className="timestamp-cell font-mono">
                        {formatDateTime(incident.timestamp)}
                      </td>
                      <td className="entity-cell">
                        <strong>{targetEntity}</strong>
                        {incident.plant_id && <span className="cell-sublabel">{incident.plant_id}</span>}
                      </td>
                      <td>
                        <span className="detector-badge">{incident.detector}</span>
                      </td>
                      <td>
                        <span className={`severity-badge ${sev.toLowerCase()}`}>
                          {sev}
                        </span>
                      </td>
                      <td className="val-cell font-mono">
                        <div className="val-primary">
                          {formatNumber(incident.actual_value, 2)} kWh
                        </div>
                        {incident.detector === 'Zero-Production Standby' ? (
                          <div className="val-secondary">
                            Output: 0 units ({incident.context_flags?.downtime_min || 60}m stoppage)
                          </div>
                        ) : incident.baseline_value ? (
                          <div className="val-secondary">
                            Base: {formatNumber(incident.baseline_value, 2)} kWh
                          </div>
                        ) : null}
                      </td>
                      <td className="explanation-cell">
                        <span className="explanation-text">{incident.explanation}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Engineering Integrity Disclaimer Notice */}
      <div className="daily-disclaimer-box anomaly-disclaimer">
        <div className="disclaimer-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <div className="disclaimer-content">
          <h4 className="disclaimer-title">Anomaly Interpretation & Baseline Governance</h4>
          <p className="disclaimer-text">
            <strong>Detector Model Overlap:</strong> The four anomaly detectors (Statistical Z-Score, Rolling Baseline, Low Power Factor, and Zero-Production Standby) evaluate electrical telemetry through differing statistical windows. Flagged occurrences may overlap on the same underlying physical event and must not be summed as independent machine breakdowns.
          </p>
          <p className="disclaimer-text" style={{ marginTop: '0.4rem' }}>
            <strong>Standby Power Categorization:</strong> Standby energy registered during production stoppages represents baseline electrical draw required for machine readiness, cleanroom controls, and safety systems. It is not classified as confirmed avoidable waste without validated submeter engineering baseline studies.
          </p>
        </div>
      </div>
    </div>
  );
}

