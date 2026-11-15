import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

const hasNumericValue = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

export default function DailyAnomalySummary({ anomaliesData, dataAvailable = true }) {
  const [filterSeverity, setFilterSeverity] = useState('ALL');

  if (!dataAvailable || !anomaliesData) {
    return (
      <div className="dashboard-section daily-anomaly-section">
        <div className="section-header">
          <div>
            <h3 className="section-title">Daily Anomaly Summary</h3>
            <p className="section-desc">Calculated detector results for the selected date and plant scope.</p>
          </div>
          <span className="daily-value-kind unavailable">Unavailable</span>
        </div>
        <div className="chart-empty-state">
          Anomaly results were not returned. This is not evidence that no anomalies occurred.
        </div>
      </div>
    );
  }

  const totalAnomalies = anomaliesData?.total_anomalies_detected ?? null;
  const statData = anomaliesData?.statistical_zscore;
  const rollData = anomaliesData?.rolling_baseline;
  const lpfData = anomaliesData?.low_power_factor;
  const standbyData = anomaliesData?.zero_production_standby;
  const statCount = statData?.total_anomalies_detected;
  const rollCount = rollData?.total_anomalies_detected;
  const lpfCount = lpfData?.total_anomalies_detected;
  const standbyCount = standbyData?.total_events_detected;
  const statisticalDataLimited = Boolean(
    statData?.insufficient_observations_groups?.length
    || statData?.zero_variance_groups?.length,
  );

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
            Calculated detector results across statistical Z-score, rolling baseline, low power factor, and zero-output energy.
          </p>
        </div>
        <div className="section-tag-group">
          <span className={`section-tag ${hasNumericValue(totalAnomalies) && Number(totalAnomalies) > 0 ? 'anomaly-count' : 'info'}`}>
            {formatNumber(totalAnomalies)} Total Detector Flags
          </span>
        </div>
      </div>

      {/* Top 4 Detector Summary Cards */}
      <div className="daily-detector-grid">
        {/* Detector 1: Statistical Z-Score */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Statistical Z-Score</span>
            <span className={`detector-status-pill ${hasNumericValue(statCount) && Number(statCount) > 0 ? 'alert' : statisticalDataLimited || !statData || !hasNumericValue(statCount) ? 'notice' : 'nominal'}`}>
              {!statData || !hasNumericValue(statCount)
                ? 'Unavailable'
                : Number(statCount) > 0
                  ? `${formatNumber(statCount)} Flagged`
                : statisticalDataLimited
                  ? 'Limited data'
                  : 'No records flagged'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(statCount)}
            <span className="detector-unit">records</span>
          </div>
          <div className="detector-meta">
            <span>Threshold: |Z| ≥ {hasNumericValue(statData?.threshold_z) ? formatNumber(statData.threshold_z, 1) : 'Unavailable'}σ</span>
            <span>Min Samples: {formatNumber(statData?.min_observations)}</span>
          </div>
          <div className="detector-desc">
            Flags extreme deviations relative to the per-meter distribution within the analyzed period.
          </div>
        </div>

        {/* Detector 2: Rolling Baseline */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Rolling Baseline</span>
            <span className={`detector-status-pill ${hasNumericValue(rollCount) && Number(rollCount) > 0 ? 'alert' : !hasNumericValue(rollCount) ? 'notice' : 'nominal'}`}>
              {!hasNumericValue(rollCount) ? 'Unavailable' : Number(rollCount) > 0 ? `${formatNumber(rollCount)} Flagged` : 'No records flagged'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(rollCount)}
            <span className="detector-unit">records</span>
          </div>
          <div className="detector-meta">
            <span>Window: {formatNumber(rollData?.window_size_hours)} hours</span>
            <span>Threshold: {hasNumericValue(rollData?.threshold_z) ? formatNumber(rollData.threshold_z, 1) : 'Unavailable'}σ</span>
          </div>
          <div className="detector-desc">
            Detects dynamic shifts against preceding 24-hour historical window.
          </div>
        </div>

        {/* Detector 3: Low Power Factor */}
        <div className="detector-card">
          <div className="detector-card-header">
            <span className="detector-name">Low Power Factor</span>
            <span className={`detector-status-pill ${hasNumericValue(lpfCount) && Number(lpfCount) > 0 ? 'alert' : !hasNumericValue(lpfCount) ? 'notice' : 'nominal'}`}>
              {!hasNumericValue(lpfCount) ? 'Unavailable' : Number(lpfCount) > 0 ? `${formatNumber(lpfCount)} Events` : 'No events flagged'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(lpfCount)}
            <span className="detector-unit">events</span>
          </div>
          <div className="detector-meta">
            <span>Detection Threshold: &lt; {hasNumericValue(lpfData?.threshold) ? formatNumber(lpfData.threshold, 2) : 'Unavailable'} PF</span>
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
            <span className={`detector-status-pill ${hasNumericValue(standbyCount) && Number(standbyCount) > 0 ? 'notice' : !hasNumericValue(standbyCount) ? 'notice' : 'nominal'}`}>
              {!hasNumericValue(standbyCount) ? 'Unavailable' : Number(standbyCount) > 0 ? `${formatNumber(standbyCount)} Events` : 'None'}
            </span>
          </div>
          <div className="detector-count">
            {formatNumber(standbyData?.total_standby_energy_kwh, 1)}
            <span className="detector-unit">kWh recorded</span>
          </div>
          <div className="detector-meta">
            <span>Events: {formatNumber(standbyCount)}</span>
            <span>Reported downtime: {formatNumber(standbyData?.total_stoppage_minutes)} min</span>
          </div>
          <div className="detector-desc">
            Positive process-meter energy recorded during zero-output intervals; this alone does not establish avoidable waste.
          </div>
        </div>
      </div>

      {/* Severity Breakdown Bar */}
      <div className="daily-severity-bar">
        <div className="severity-bar-title">Severity Distribution:</div>
        <div className="severity-tags-group" role="group" aria-label="Filter anomaly findings by severity">
          <button
            type="button"
            className={`severity-filter-btn ${filterSeverity === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('ALL')}
            aria-pressed={filterSeverity === 'ALL'}
          >
            All ({allIncidents.length})
          </button>
          <button
            type="button"
            className={`severity-filter-btn crit ${filterSeverity === 'CRITICAL' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('CRITICAL')}
            aria-pressed={filterSeverity === 'CRITICAL'}
          >
            Critical ({criticalCount})
          </button>
          <button
            type="button"
            className={`severity-filter-btn high ${filterSeverity === 'HIGH' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('HIGH')}
            aria-pressed={filterSeverity === 'HIGH'}
          >
            High ({highCount})
          </button>
          <button
            type="button"
            className={`severity-filter-btn med ${filterSeverity === 'MEDIUM' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('MEDIUM')}
            aria-pressed={filterSeverity === 'MEDIUM'}
          >
            Medium ({mediumCount})
          </button>
          <button
            type="button"
            className={`severity-filter-btn low ${filterSeverity === 'LOW' ? 'active' : ''}`}
            onClick={() => setFilterSeverity('LOW')}
            aria-pressed={filterSeverity === 'LOW'}
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
              <strong>No anomaly records returned for this selection</strong>
              <p>This reflects the detector results returned for the selected scope; it does not establish overall data completeness.</p>
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
                  <th>Measured Value / Reference</th>
                  <th>Operational Finding</th>
                </tr>
              </thead>
              <tbody>
                {filteredIncidents.map((incident, idx) => {
                  const sev = (incident.severity || 'LOW').toUpperCase();
                  const isPowerFactor = incident.detector === 'Low Power Factor';
                  const referenceLabel = isPowerFactor
                    ? 'Threshold'
                    : incident.detector === 'Statistical Z-Score'
                      ? 'Period mean'
                      : 'Rolling mean';
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
                          {formatNumber(incident.actual_value, 2)} {isPowerFactor ? 'PF' : 'kWh'}
                        </div>
                        {incident.detector === 'Zero-Production Standby' ? (
                          <div className="val-secondary">
                            Output: 0 units · reported downtime: {incident.context_flags?.downtime_min == null
                              ? 'Unavailable'
                              : `${formatNumber(incident.context_flags.downtime_min)} min`}
                          </div>
                        ) : incident.baseline_value !== null && incident.baseline_value !== undefined ? (
                          <div className="val-secondary">
                            {referenceLabel}: {formatNumber(incident.baseline_value, 2)} {isPowerFactor ? 'PF' : 'kWh'}
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
            <strong>Zero-output energy:</strong> Energy recorded during a zero-output interval does not establish a required equipment baseline, machine fault, or avoidable waste. Those conclusions require additional operational evidence and a validated engineering baseline.
          </p>
        </div>
      </div>
    </div>
  );
}

