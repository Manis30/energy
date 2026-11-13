import React, { useState } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';

function formatSeverity(severity) {
  return severity ? severity.toLowerCase() : 'unclassified';
}

function formatContextValue(value) {
  if (value === null || value === undefined || value === '') return 'Unavailable';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function AlertEvidence({ alert }) {
  const isPowerFactor = alert.anomaly_type === 'LOW_POWER_FACTOR';
  const isStandby = alert.anomaly_type === 'ZERO_PRODUCTION_STANDBY_ENERGY';
  const isZScore = alert.anomaly_type?.startsWith('ENERGY_STATISTICAL_')
    || alert.anomaly_type?.startsWith('ROLLING_BASELINE_');
  const unit = isPowerFactor ? ' PF' : ' kWh';

  return (
    <div className="alert-detail-content">
      <div className="alert-evidence-grid">
        <div>
          <span>Measured</span>
          <strong>{formatNumber(alert.actual_value, 4)}{unit}</strong>
        </div>
        {!isStandby && (
          <div>
            <span>Reference mean / threshold</span>
            <strong>{formatNumber(alert.baseline_value, 4)}{unit}</strong>
          </div>
        )}
        <div>
          <span>{isZScore ? 'Z-score' : isStandby ? 'Standby energy' : isPowerFactor ? 'Power factor deficit' : 'Deviation score'}</span>
          <strong>{formatNumber(alert.deviation_score, 4)}{isZScore ? 'σ' : isStandby ? ' kWh' : ''}</strong>
        </div>
        {alert.source && (
          <div>
            <span>Detector</span>
            <strong>{alert.source}</strong>
          </div>
        )}
      </div>
      {alert.explanation && <p className="alert-explanation">{alert.explanation}</p>}
      {Object.keys(alert.context_flags || {}).length > 0 && (
        <details className="alert-context">
          <summary>Calculation context and evidence</summary>
          <dl>
            {Object.entries(alert.context_flags).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replace(/_/g, ' ')}</dt>
                <dd>{formatContextValue(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

export default function AlertList({ alerts }) {
  const [expandedKey, setExpandedKey] = useState(null);

  return (
    <div className="alert-list">
      {alerts.map((alert) => {
        const expanded = expandedKey === alert.alertKey;
        const source = alert.meter_id || alert.line_id;
        const detailsId = `alert-details-${alert.alertKey.replace(/\s+/g, '-')}`;
        return (
          <article
            key={alert.alertKey}
            className={`alert-item ${formatSeverity(alert.severity)}`}
          >
            <button
              type="button"
              className="alert-item-summary"
              onClick={() => setExpandedKey((current) => current === alert.alertKey ? null : alert.alertKey)}
              aria-expanded={expanded}
              aria-controls={detailsId}
            >
              <span className={`alert-severity-indicator ${formatSeverity(alert.severity)}`} />
              <span className="alert-time">{formatDateTime(alert.timestamp)}</span>
              <span className={`alert-severity-label ${formatSeverity(alert.severity)}`}>
                {alert.severity || 'Unclassified'}
              </span>
              <span className="alert-category">{(alert.anomaly_type || 'Uncategorized').replace(/_/g, ' ')}</span>
              <span className="alert-location">
                {alert.plant_id || 'Plant unavailable'}
                {source ? ` · ${source}` : ''}
              </span>
              <span className="alert-source">{alert.source}</span>
              <span className="alert-measurement">
                {formatNumber(alert.actual_value, 2)}
                {alert.anomaly_type === 'LOW_POWER_FACTOR' ? ' PF' : ' kWh'}
              </span>
              <span className={`alert-disclosure ${expanded ? 'expanded' : ''}`} aria-hidden="true">⌄</span>
            </button>
            <div id={detailsId} hidden={!expanded}>
              {expanded && <AlertEvidence alert={alert} />}
            </div>
          </article>
        );
      })}
    </div>
  );
}
