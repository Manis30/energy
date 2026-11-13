import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { anomalyApi } from '../services';
import { formatDateTime } from '../utils/formatters';
import './recommendations/recommendations.css';

const DETECTORS = [
  ['Statistical energy', 'statistical_zscore'],
  ['Rolling baseline', 'rolling_baseline'],
  ['Power factor', 'low_power_factor'],
  ['Zero-production standby', 'zero_production_standby'],
];

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'];

function formatValue(value, decimals = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) {
    return 'Unavailable';
  }
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatTimestamp(value) {
  if (!value) return 'Timestamp unavailable';
  return formatDateTime(value);
}

function getFindings(data) {
  return DETECTORS.flatMap(([source, key]) => {
    const records = data?.[key]?.anomalies;
    return (Array.isArray(records) ? records : []).map((finding, index) => ({
      ...finding,
      source,
      id: `${key}-${finding.timestamp}-${finding.plant_id}-${finding.meter_id || finding.line_id || ''}-${index}`,
    }));
  }).sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')));
}

function FindingCard({ finding }) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = `recommendation-details-${finding.id}`;
  const isPowerFactor = finding.anomaly_type === 'LOW_POWER_FACTOR';
  const isStandby = finding.anomaly_type === 'ZERO_PRODUCTION_STANDBY_ENERGY';
  const isZScore = finding.anomaly_type?.startsWith('ENERGY_STATISTICAL_')
    || finding.anomaly_type?.startsWith('ROLLING_BASELINE_');

  return (
    <article className={`recommendation-finding ${finding.severity?.toLowerCase() || 'unclassified'}`}>
      <button
        type="button"
        className="recommendation-finding-toggle"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        aria-controls={detailsId}
      >
        <span className={`recommendation-severity ${finding.severity?.toLowerCase() || 'unclassified'}`}>
          {finding.severity || 'Severity unavailable'}
        </span>
        <span className="recommendation-category">
          {(finding.anomaly_type || 'Category unavailable').replace(/_/g, ' ')}
        </span>
        <span className="recommendation-source">{finding.source}</span>
        <span className="recommendation-timestamp">{formatTimestamp(finding.timestamp)}</span>
        <span className={`recommendation-chevron ${expanded ? 'expanded' : ''}`} aria-hidden="true">⌄</span>
      </button>

      <div className="recommendation-finding-meta">
        <span>{finding.plant_id || 'Plant unavailable'}</span>
        {finding.meter_id && <span>Meter {finding.meter_id}</span>}
        {finding.line_id && <span>Line {finding.line_id}</span>}
        <span className="recommendation-status-note">Informational · Not tracked as an operational action</span>
      </div>

      <div id={detailsId} className="recommendation-finding-details" hidden={!expanded}>
          <div className="recommendation-evidence">
            <div>
              <span>Measured</span>
              <strong>
                {formatValue(finding.actual_value, 4)}
                {isPowerFactor ? '' : ' kWh'}
              </strong>
            </div>
            {!isStandby && (
              <div>
                <span>Baseline / threshold</span>
                <strong>
                  {formatValue(finding.baseline_value, 4)}
                  {isPowerFactor ? '' : ' kWh'}
                </strong>
              </div>
            )}
            <div>
              <span>{isZScore ? 'Z-score' : isPowerFactor ? 'Power factor deficit' : 'Deviation score'}</span>
              <strong>
                {formatValue(finding.deviation_score, 4)}
                {isZScore ? 'σ' : isStandby ? ' kWh' : ''}
              </strong>
            </div>
          </div>
          {finding.explanation && (
            <p className="recommendation-explanation">{finding.explanation}</p>
          )}
          {Object.keys(finding.context_flags || {}).length > 0 && (
            <details className="recommendation-context">
              <summary>Calculation context and evidence</summary>
              <dl>
                {Object.entries(finding.context_flags).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replace(/_/g, ' ')}</dt>
                    <dd>
                      {value === null || value === undefined || value === ''
                        ? 'Unavailable'
                        : typeof value === 'boolean'
                          ? (value ? 'Yes' : 'No')
                          : typeof value === 'object'
                            ? JSON.stringify(value)
                            : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          <div className="recommendation-action-unavailable">
            <strong>Suggested action unavailable</strong>
            <span>The anomaly data source does not provide a recommended corrective action.</span>
          </div>
      </div>
    </article>
  );
}

export default function RecommendationsActions() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadFindings = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      setData(await anomalyApi.getAllAnomalies());
    } catch (err) {
      console.error('Recommendations and Actions data load error:', err);
      setError(err.message || 'Unable to load evidence-backed findings. Verify the backend connection and try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadFindings();
  }, [loadFindings]);

  const findings = useMemo(() => getFindings(data), [data]);
  const severityCounts = useMemo(() => {
    const counts = Object.fromEntries(SEVERITIES.map((severity) => [severity, 0]));
    findings.forEach((finding) => {
      if (Object.prototype.hasOwnProperty.call(counts, finding.severity)) {
        counts[finding.severity] += 1;
      }
    });
    return counts;
  }, [findings]);

  return (
    <div className="recommendations-page">
      <header className="recommendations-header">
        <div>
          <span className="recommendations-eyebrow">Operational follow-up</span>
          <h1>Recommendations &amp; Actions</h1>
          <p>Review evidence-backed energy findings and their operational follow-up readiness.</p>
        </div>
        <button
          type="button"
          className="recommendations-refresh"
          onClick={() => loadFindings(true)}
          disabled={loading || refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh findings'}
        </button>
      </header>

      <section className="recommendations-summary" aria-label="Finding summary">
        <div className="recommendation-summary-card featured">
          <span>Evidence-backed findings</span>
          <strong>{data ? findings.length.toLocaleString('en-IN') : '—'}</strong>
          <small>Records returned by anomaly detectors</small>
        </div>
        {SEVERITIES.map((severity) => (
          <div className={`recommendation-summary-card ${severity.toLowerCase()}`} key={severity}>
            <span>{severity.toLowerCase()}</span>
            <strong>{data ? severityCounts[severity].toLocaleString('en-IN') : '—'}</strong>
          </div>
        ))}
      </section>

      <section className="recommendation-capability-notice" aria-label="Action tracking availability">
        <div>
          <strong>Action management is not available</strong>
          <p>
            Current APIs do not provide persisted corrective actions, owners, due dates, statuses, or resolution details.
            Findings shown here are informational and are not operational action records.
          </p>
        </div>
      </section>

      <section className="recommendations-list-section" aria-busy={loading || refreshing}>
        <div className="recommendations-list-heading">
          <div>
            <h2>Evidence-backed findings</h2>
            <p>Detector results and explanations from the existing anomaly service.</p>
          </div>
          {data && <span>{findings.length.toLocaleString('en-IN')} findings</span>}
        </div>

        {error ? (
          <div className="recommendations-state error" role="alert">
            <strong>Unable to load findings</strong>
            <span>{error}</span>
            <button type="button" onClick={() => loadFindings()}>Try again</button>
          </div>
        ) : loading ? (
          <div className="recommendations-state" role="status">
            <span className="loading-spinner" />
            <strong>Loading evidence-backed findings</strong>
          </div>
        ) : findings.length === 0 ? (
          <div className="recommendations-state" role="status">
            <strong>No evidence-backed findings returned</strong>
            <span>The current anomaly detectors returned no finding records.</span>
          </div>
        ) : (
          <div className="recommendations-list">
            {findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}
          </div>
        )}
      </section>

      <section className="recommendation-hypotheses-notice">
        <div>
          <span className="hypothesis-label">AI-generated hypotheses</span>
          <p>
            The AI Assistant provides conversational answers and tool evidence, not structured recommendation records.
            Its hypotheses are not stored or shown as recommendations here.
          </p>
        </div>
        <span className="hypothesis-unavailable">Not available as structured data</span>
      </section>
    </div>
  );
}
