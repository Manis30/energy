import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

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
  const hasBalanceValues = [actualQty, goodQty, rejectQty].every((value) => hasNumber(value));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Quality &amp; Balance Verification</h3>
          <p className="section-desc">
            Good-output yield and deterministic quantity balance check across manufacturing operations.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag quality">
            {goodRate !== null ? `Good-Output Yield: ${formatPercent(goodRate)}` : 'Yield unavailable'}
          </span>
          <span className="section-tag scrap">
            {rejectRate !== null ? `Rejection Rate: ${formatPercent(rejectRate)}` : 'Scrap unavailable'}
          </span>
        </div>
      </div>

      <div className="quality-reconciliation-card">
        <div className="quality-reconciliation-header">
          <div>
            <h4 className="chart-card-title">Mathematical Quantity Balance Verification</h4>
            <span className="chart-card-subtitle">
              Deterministic balance check: Actual Output = Good Units + Rejected Units (Rework is isolated)
            </span>
          </div>
          <span
            className={`verified-balance-pill ${
              balanceValid === true ? 'valid' : balanceValid === false ? 'invalid' : 'unavailable'
            }`}
          >
            {hasBalanceResult
              ? balanceValid
                ? '✓ Quantity Balance Verified'
                : '⚠ Balance Mismatch Detected'
              : 'Balance check unavailable'}
            {hasBalanceValues && `: ${formatNumber(actualQty)} = ${formatNumber(goodQty)} + ${formatNumber(rejectQty)}`}
          </span>
        </div>

        <div className="quality-metrics-row">
          <div className="quality-metric-item">
            <span className="quality-metric-label">Total Actual Output</span>
            <span className="quality-metric-val">{formatNumber(actualQty)}</span>
            <span className="quality-metric-pct">Total reported units produced</span>
          </div>

          <div className="quality-metric-item success">
            <span className="quality-metric-label">Good Output Units</span>
            <span className="quality-metric-val">{formatNumber(goodQty)}</span>
            <span className="quality-metric-pct">
              {goodRate !== null ? `${formatPercent(goodRate)} Good-Output Yield (Good / Actual)` : 'Yield unavailable'}
            </span>
          </div>

          <div className="quality-metric-item danger">
            <span className="quality-metric-label">Rejected Units</span>
            <span className="quality-metric-val">{formatNumber(rejectQty)}</span>
            <span className="quality-metric-pct">
              {rejectRate !== null ? `${formatPercent(rejectRate)} Rejection Rate (Reject / Actual)` : 'Rate unavailable'}
            </span>
          </div>

          <div className="quality-metric-item warning">
            <span className="quality-metric-label">Reworked Units</span>
            <span className="quality-metric-val">{formatNumber(reworkQty)}</span>
            <span className="quality-metric-pct">
              {reworkRate !== null
                ? `${formatPercent(reworkRate)} Rework Rate (Separate Quantity)`
                : 'Rework isolated'}
            </span>
          </div>
        </div>

        {/* Compact Quality & OEE Boundary Note */}
        <div className="segregation-callout-box" style={{ marginTop: '1rem' }}>
          <div className="callout-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <span>Quality Accounting &amp; OEE Boundary</span>
          </div>
          <p className="callout-text">
            First-pass yield evaluates good output against total actual output. Standard Overall Equipment Effectiveness (OEE) is not computed because production calendar schedules, availability baselines, and ideal cycle times are not established by this telemetry dataset.
          </p>
        </div>
      </div>
    </div>
  );
}
