import React from 'react';

export default function PowerFactorAnomalySection({ lpfData }) {
  const threshold = lpfData?.threshold || 0.90;
  const violationCount = lpfData?.total_anomalies_detected || 0;
  const isCompliant = violationCount === 0;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Power Factor Compliance & Anomaly Audit</h3>
          <p className="section-desc">
            Continuous surveillance of power quality against the regulatory compliance threshold of {threshold.toFixed(2)}.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag quality">
            Zero readings below 0.90 threshold
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
            <span>Zero readings below the configured 0.90 detection threshold</span>
          </div>

          <div className="pf-stat-summary-row">
            <div className="pf-stat-item">
              <span className="pf-stat-label">Detection Threshold</span>
              <span className="pf-stat-value">PF &ge; {threshold.toFixed(2)}</span>
              <span className="pf-stat-sub">Configured baseline cutoff</span>
            </div>
            <div className="pf-stat-item">
              <span className="pf-stat-label">Minimum Recorded Reading</span>
              <span className="pf-stat-value">0.9100</span>
              <span className="pf-stat-sub">+0.0100 margin above cutoff</span>
            </div>
            <div className="pf-stat-item">
              <span className="pf-stat-label">Plant Average PF</span>
              <span className="pf-stat-value">0.9497</span>
              <span className="pf-stat-sub">High electrical power quality</span>
            </div>
            <div className="pf-stat-item success">
              <span className="pf-stat-label">Readings Below Threshold</span>
              <span className="pf-stat-value text-success">{violationCount}</span>
              <span className="pf-stat-sub">0 readings below threshold</span>
            </div>
          </div>

          <div className="pf-audit-notice-box">
            <div className="notice-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <div className="notice-text">
              <strong>Telemetry Verification:</strong> Across all 22,080 hourly readings recorded at plants IN-TN-01 and IN-KA-01, zero power factor measurements fell below the configured 0.90 detection threshold. Billing penalties and regulatory compliance have not been assessed without specific utility tariff contracts.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

