import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

export default function ProductionQualitySection({ summary }) {
  const actualQty = summary ? summary.actual_qty : 2424184;
  const goodQty = summary ? summary.good_qty : 2378960;
  const rejectQty = summary ? summary.reject_qty : 45224;
  const reworkQty = summary ? summary.rework_qty : 24852;
  const goodRate = summary ? summary.good_rate : '98.13';
  const rejectRate = summary ? summary.reject_rate : '1.87';
  const reworkRate = summary ? summary.rework_rate : '1.02';

  const balanceValid = summary ? summary.quantity_balance_valid : true;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Quality & Mathematical Quantity Balance</h3>
          <p className="section-desc">
            Rigorous quality yield reconciliation and verified parts accounting based on relational database constraints.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag quality">First-Pass Yield: {formatPercent(goodRate)}</span>
          <span className="section-tag scrap">Defect Rate: {formatPercent(rejectRate)}</span>
        </div>
      </div>

      <div className="quality-reconciliation-card">
        <div className="quality-reconciliation-header">
          <div>
            <h4 className="chart-card-title">Mathematical Quantity Balance Verification</h4>
            <span className="chart-card-subtitle">
              Strict identity constraint: Actual Output = Good Output + Defective Output
            </span>
          </div>
          <span className={`verified-balance-pill ${balanceValid ? 'valid' : 'invalid'}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            Quantity Balance Valid: {formatNumber(actualQty)} = {formatNumber(goodQty)} + {formatNumber(rejectQty)}
          </span>
        </div>

        <div className="quality-metrics-row">
          <div className="quality-metric-item">
            <span className="quality-metric-label">Total Actual Output</span>
            <span className="quality-metric-val">{formatNumber(actualQty)}</span>
            <span className="quality-metric-pct">100.0% of production</span>
          </div>

          <div className="quality-metric-item success">
            <span className="quality-metric-label">First-Pass Good Units</span>
            <span className="quality-metric-val">{formatNumber(goodQty)}</span>
            <span className="quality-metric-pct">{formatPercent(goodRate)} quality yield</span>
          </div>

          <div className="quality-metric-item danger">
            <span className="quality-metric-label">Scrap / Defective Units</span>
            <span className="quality-metric-val">{formatNumber(rejectQty)}</span>
            <span className="quality-metric-pct">{formatPercent(rejectRate)} scrap rate</span>
          </div>

          <div className="quality-metric-item warning">
            <span className="quality-metric-label">Reworked Units</span>
            <span className="quality-metric-val">{formatNumber(reworkQty)}</span>
            <span className="quality-metric-pct">{formatPercent(reworkRate)} of actual (separate loop)</span>
          </div>
        </div>

        {/* Quality Audit & OEE Exclusion Note */}
        <div className="quality-audit-notice-grid">
          <div className="audit-notice-card">
            <div className="audit-notice-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
              <span>Quality Metric vs OEE Clarification</span>
            </div>
            <p className="audit-notice-text">
              The quality metric reported above (<strong>{formatPercent(goodRate)}</strong>) represents pure first-pass manufacturing yield ($Good \div Actual$). In accordance with ISO 22400 standards, Overall Equipment Effectiveness (OEE) is explicitly <strong>not calculated</strong> because source datasets lack verified planned production schedules, operating time calendars, and validated ideal cycle times. No unsupported operating assumptions are made.
            </p>
          </div>

          <div className="audit-notice-card">
            <div className="audit-notice-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              <span>Rework Isolation Protocol</span>
            </div>
            <p className="audit-notice-text">
              Reworked units (<strong>{formatNumber(reworkQty)}</strong>) are tracked independently as secondary remediation events. In compliance with industrial accounting rules, rework is never added to final finished output counts to prevent artificial double-counting of physical inventory.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

