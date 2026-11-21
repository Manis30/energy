import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

function formatContextValue(key, value) {
  if (value === null || value === undefined || value === '') return 'Unavailable';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'string' && (key.endsWith('_start') || key.endsWith('_end') || key.includes('timestamp'))) {
    return formatDateTime(value);
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function AlertEvidence({ alert }) {
  const isPowerFactor = alert.anomaly_type === 'LOW_POWER_FACTOR';
  const isStandby = alert.anomaly_type === 'ZERO_PRODUCTION_STANDBY_ENERGY';
  const isZScore = alert.anomaly_type?.startsWith('ENERGY_STATISTICAL_')
    || alert.anomaly_type?.startsWith('ROLLING_BASELINE_');
  const unit = isPowerFactor ? ' PF' : ' kWh';
  const hasBaseline = alert.baseline_value !== null && alert.baseline_value !== undefined;

  return (
    <div className="iac-evidence-expanded">
      <div className="iac-evidence-grid">
        <div className="iac-evidence-stat">
          <span className="iac-evidence-label">Measured Value</span>
          <strong className="iac-evidence-val">
            {alert.actual_value !== null && alert.actual_value !== undefined
              ? `${formatNumber(alert.actual_value, 4)}${unit}`
              : 'Unavailable'}
          </strong>
        </div>
        <div className="iac-evidence-stat">
          <span className="iac-evidence-label">Reference Mean / Threshold</span>
          <strong className="iac-evidence-val">
            {isStandby
              ? 'No baseline (Zero output standby)'
              : hasBaseline
                ? `${formatNumber(alert.baseline_value, 4)}${unit}`
                : 'Baseline unavailable'}
          </strong>
        </div>
        <div className="iac-evidence-stat">
          <span className="iac-evidence-label">
            {isZScore ? 'Z-Score' : isStandby ? 'Standby Energy' : isPowerFactor ? 'Power Factor Deficit' : 'Deviation Score'}
          </span>
          <strong className="iac-evidence-val">
            {alert.deviation_score !== null && alert.deviation_score !== undefined
              ? `${formatNumber(alert.deviation_score, 4)}${isZScore ? 'σ' : isStandby ? ' kWh' : ''}`
              : 'Unavailable'}
          </strong>
        </div>
        {alert.source && (
          <div className="iac-evidence-stat">
            <span className="iac-evidence-label">Detector Algorithm</span>
            <strong className="iac-evidence-val">{alert.source}</strong>
          </div>
        )}
      </div>
      {alert.explanation && (
        <p className="iac-evidence-explanation">{alert.explanation}</p>
      )}
      {Object.keys(alert.context_flags || {}).length > 0 && (
        <details className="iac-evidence-context">
          <summary>Calculation Context & Detection Evidence</summary>
          <dl className="iac-evidence-dl">
            {Object.entries(alert.context_flags).map(([key, value]) => (
              <div key={key} className="iac-evidence-row">
                <dt>{key.replace(/_/g, ' ')}</dt>
                <dd>{formatContextValue(key, value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

export default function AlertList({ alerts = [] }) {
  const [expandedKey, setExpandedKey] = useState(null);

  if (!alerts || alerts.length === 0) {
    return (
      <div className="iac-empty-state" style={{ padding: '3rem 1.5rem' }}>
        <p style={{ color: 'var(--text-muted)' }}>
          No surveillance signals match the current filter criteria.
        </p>
      </div>
    );
  }

  return (
    <div className="iac-table-wrapper">
      <table className="iac-table iac-surveillance-table" aria-label="Surveillance Suite Signals Table">
        <thead>
          <tr>
            <th style={{ width: '160px' }}>Timestamp</th>
            <th style={{ width: '120px' }}>Severity</th>
            <th>Signal / Anomaly Type</th>
            <th style={{ width: '120px' }}>Plant</th>
            <th style={{ width: '140px' }}>Meter or Asset</th>
            <th style={{ width: '160px' }}>Measured Value</th>
            <th style={{ width: '70px', textAlign: 'center' }}>Details</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert, index) => {
            const key = alert.alertKey || `${alert.timestamp}-${alert.plant_id}-${alert.meter_id || alert.line_id || index}`;
            const isExpanded = expandedKey === key;
            const assetName = alert.meter_id || alert.line_id || alert.source || 'Facility-wide';
            const isPowerFactor = alert.anomaly_type === 'LOW_POWER_FACTOR';
            const unit = isPowerFactor ? ' PF' : ' kWh';
            const sevClass = (alert.severity || 'low').toLowerCase();

            return (
              <React.Fragment key={key}>
                <tr
                  className={`iac-surveillance-row ${isExpanded ? 'is-expanded' : ''}`}
                  onClick={() => setExpandedKey(isExpanded ? null : key)}
                  tabIndex={0}
                  role="button"
                  aria-expanded={isExpanded}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setExpandedKey(isExpanded ? null : key);
                    }
                  }}
                >
                  <td className="iac-table-date">
                    {formatDateTime(alert.timestamp)}
                  </td>
                  <td>
                    <span className={`badge-iac badge-sev-${sevClass}`}>
                      <span className="badge-dot" />
                      {alert.severity || 'LOW'}
                    </span>
                  </td>
                  <td>
                    <div className="iac-table-title-group">
                      <span className="iac-table-title">
                        {(alert.anomaly_type || 'Uncategorized').replace(/_/g, ' ')}
                      </span>
                      {alert.source && (
                        <span className="iac-table-id">{alert.source}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className="iac-table-plant-badge">
                      {alert.plant_id || 'IN-TN-01'}
                    </span>
                  </td>
                  <td>
                    <span className="iac-table-asset">
                      {assetName}
                    </span>
                  </td>
                  <td>
                    <div className="iac-surveillance-measurement">
                      <span className="iac-measure-val">
                        {alert.actual_value !== null && alert.actual_value !== undefined
                          ? `${formatNumber(alert.actual_value, 2)}${unit}`
                          : 'Unavailable'}
                      </span>
                      {alert.baseline_value !== null && alert.baseline_value !== undefined && (
                        <span className="iac-measure-baseline">
                          Base: {formatNumber(alert.baseline_value, 2)}{unit}
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      type="button"
                      className={`iac-row-expand-btn ${isExpanded ? 'is-expanded' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedKey(isExpanded ? null : key);
                      }}
                      aria-label={isExpanded ? 'Collapse evidence details' : 'Expand evidence details'}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="iac-evidence-expanded-row">
                    <td colSpan={7}>
                      <AlertEvidence alert={alert} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
