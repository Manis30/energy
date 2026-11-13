import React from 'react';

export default function PowerFactorAnomalySection({ lpfData }) {
  const threshold = lpfData?.threshold ? Number(lpfData.threshold) : 0.90;
  const violationCount = lpfData?.total_anomalies_detected ?? null;
  const isWithinThreshold = violationCount === 0;

  if (!lpfData) {
    return (
      <div className="dashboard-section">
        <div className="section-header">
          <div>
            <h3 className="section-title">Power Factor Anomaly Audit</h3>
            <p className="section-desc">
              Surveillance of power quality against the application-configured detection threshold of {threshold.toFixed(2)}.
            </p>
          </div>
        </div>
        <div className="chart-empty-state">Power factor anomaly telemetry is currently unavailable.</div>
      </div>
    );
  }

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Power Factor Anomaly Audit</h3>
          <p className="section-desc">
            Continuous surveillance of power quality against the application-configured monitoring threshold of {threshold.toFixed(2)}.
          </p>
        </div>
        <div className="section-tag-group">
          <span className={`section-tag ${isWithinThreshold ? 'quality' : 'scrap'}`}>
            {isWithinThreshold
              ? `Zero readings below ${threshold.toFixed(2)} threshold`
              : `${violationCount} readings below ${threshold.toFixed(2)} threshold`}
          </span>
        </div>
      </div>

      <div className="chart-card pf-anomaly-card">
        <div className="pf-compliance-content">
          <div className="pf-compliance-badge-large">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span>
              {isWithinThreshold
                ? `Zero readings below the configured ${threshold.toFixed(2)} detection threshold`
                : `${violationCount} readings below the configured ${threshold.toFixed(2)} detection threshold`}
            </span>
          </div>

          <div className="pf-stat-summary-row">
            <div className="pf-stat-item">
              <span className="pf-stat-label">Detection Cutoff</span>
              <span className="pf-stat-value">PF &lt; {threshold.toFixed(2)}</span>
              <span className="pf-stat-sub">Application monitoring threshold</span>
            </div>
            <div className="pf-stat-item">
              <span className="pf-stat-label">Monitored Scope</span>
              <span className="pf-stat-value">All Meters</span>
              <span className="pf-stat-sub">Process & utility submeters</span>
            </div>
            <div className="pf-stat-item">
              <span className="pf-stat-label">Flagged Exceptions</span>
              <span className={`pf-stat-value ${isWithinThreshold ? 'text-success' : 'text-danger'}`}>
                {violationCount !== null ? violationCount : '—'}
              </span>
              <span className="pf-stat-sub">
                {isWithinThreshold ? 'Zero events detected' : 'Under-threshold readings'}
              </span>
            </div>
            <div className="pf-stat-item success">
              <span className="pf-stat-label">Threshold Status</span>
              <span className="pf-stat-value text-success">
                {isWithinThreshold ? 'Nominal' : 'Action Required'}
              </span>
              <span className="pf-stat-sub">Relative to configured threshold</span>
            </div>
          </div>

          <div className="pf-audit-notice-box">
            <div className="notice-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <div className="notice-text">
              <strong>Telemetry Verification:</strong> Across queried telemetry records, {isWithinThreshold ? 'zero power factor measurements' : `${violationCount} power factor measurements`} fell below the configured {threshold.toFixed(2)} application detection threshold. Billing surcharges and regulatory compliance cannot be assessed without site-specific utility tariff contracts.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
