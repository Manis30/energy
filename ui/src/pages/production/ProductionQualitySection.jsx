import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

export default function ProductionQualitySection({ summary }) {
  const actualQty = summary?.actual_qty ?? null;
  const goodQty = summary?.good_qty ?? null;
  const rejectQty = summary?.reject_qty ?? null;
  const reworkQty = summary?.rework_qty ?? null;
  const goodRate = summary?.good_rate ?? null;
  const rejectRate = summary?.reject_rate ?? null;
  const reworkRate = summary?.rework_rate ?? null;
  const balanceValid = summary?.quantity_balance_valid;
  const hasBalanceResult = typeof balanceValid === 'boolean';
  const hasBalanceValues = [actualQty, goodQty, rejectQty].every((value) => (
    value !== null && Number.isFinite(Number(value))
  ));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Quality & Mathematical Quantity Balance</h3>
          <p className="section-desc">
            Returned production quantities and quality rates, with the API-reported actual = good + rejected balance check.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag quality">
            {goodRate == null ? 'First-Pass Yield unavailable' : `First-Pass Yield: ${formatPercent(goodRate)}`}
          </span>
          <span className="section-tag scrap">
            {rejectRate == null ? 'Reject Rate unavailable' : `Reject Rate: ${formatPercent(rejectRate)}`}
          </span>
        </div>
      </div>

      <div className="quality-reconciliation-card">
        <div className="quality-reconciliation-header">
          <div>
            <h4 className="chart-card-title">Mathematical Quantity Balance Verification</h4>
            <span className="chart-card-subtitle">
              Dataset relationship: actual output = good output + rejected output; rework is separate
            </span>
          </div>
          <span className={`verified-balance-pill ${balanceValid === true ? 'valid' : balanceValid === false ? 'invalid' : 'unavailable'}`}>
            {hasBalanceResult
              ? `API-reported quantity balance ${balanceValid ? 'valid' : 'not valid'}`
              : 'Quantity-balance check unavailable'}
            {hasBalanceValues && `: ${formatNumber(actualQty)} = ${formatNumber(goodQty)} + ${formatNumber(rejectQty)}`}
          </span>
        </div>

        <div className="quality-metrics-row">
          <div className="quality-metric-item">
            <span className="quality-metric-label">Total Actual Output</span>
            <span className="quality-metric-val">{formatNumber(actualQty)}</span>
            <span className="quality-metric-pct">Total reported actual quantity</span>
          </div>

          <div className="quality-metric-item success">
            <span className="quality-metric-label">First-Pass Good Units</span>
            <span className="quality-metric-val">{formatNumber(goodQty)}</span>
            <span className="quality-metric-pct">
              {goodRate == null ? 'First-pass yield unavailable' : `${formatPercent(goodRate)} reported yield (good / actual)`}
            </span>
          </div>

          <div className="quality-metric-item danger">
            <span className="quality-metric-label">Rejected Units</span>
            <span className="quality-metric-val">{formatNumber(rejectQty)}</span>
            <span className="quality-metric-pct">
              {rejectRate == null ? 'Reject rate unavailable' : `${formatPercent(rejectRate)} reported reject rate`}
            </span>
          </div>

          <div className="quality-metric-item warning">
            <span className="quality-metric-label">Reworked Units</span>
            <span className="quality-metric-val">{formatNumber(reworkQty)}</span>
            <span className="quality-metric-pct">
              {reworkRate == null ? 'Rework rate unavailable' : `${formatPercent(reworkRate)} reported rework rate (separate quantity)`}
            </span>
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
              {goodRate == null
                ? 'First-pass yield is unavailable because no value was returned.'
                : <>The returned first-pass yield (<strong>{formatPercent(goodRate)}</strong>) is reported as good output divided by actual output.</>}
              {' '}Overall Equipment Effectiveness (OEE) is <strong>not calculated</strong>; the required production schedules, operating-time calendar, and ideal cycle times are not established by the available data.
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
              Rework is a separate reported quantity{reworkQty == null ? ' and is unavailable for this selection' : <> (<strong>{formatNumber(reworkQty)}</strong> units)</>}. Do not add it to actual or rejected output without a validated accounting rule.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

