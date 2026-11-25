import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

/**
 * Section 2: Production count check
 * Replaces the nested "Mathematical Quantity Balance Verification" panel with a compact
 * "Production count check" section.
 * - Scope explicitly declared as "All production stages"
 * - Displays single equation: Actual output = Good units + Rejected units
 * - Shows rework separately
 * - Displays "Balanced", actual discrepancy, or "Insufficient data"
 * - Uses "Good-output yield" for good ÷ actual
 * - Accessible disclosure: "How these metrics are calculated"
 */
export default function ProductionQualitySection({ summary, selectedLine = null }) {
  const actualQty = summary?.actual_qty ?? null;
  const goodQty = summary?.good_qty ?? null;
  const rejectQty = summary?.reject_qty ?? null;
  const reworkQty = summary?.rework_qty ?? null;
  const goodRate = summary?.good_rate ?? null;
  const rejectRate = summary?.reject_rate ?? null;
  const reworkRate = summary?.rework_rate ?? null;

  const hasBalanceValues = hasNumber(actualQty) && hasNumber(goodQty) && hasNumber(rejectQty);
  const discrepancy = hasBalanceValues
    ? Number(actualQty) - (Number(goodQty) + Number(rejectQty))
    : null;
  const isBalanced = hasBalanceValues && discrepancy === 0;

  return (
    <div className="dashboard-section production-count-panel">
      {/* 1. Header with Title, Scope, and Balance Status */}
      <div className="section-header">
        <div>
          <h3 className="section-title">Production count check</h3>
          <p className="section-desc">
            Scope: {selectedLine ? `Line ${selectedLine}` : 'All production stages (SMT circuit boards + Final Assembly phones)'}
          </p>
        </div>

        <div className="count-check-status-wrap">
          {hasBalanceValues ? (
            <span
              className={`count-check-badge ${isBalanced ? 'balanced' : 'discrepancy'}`}
            >
              {isBalanced
                ? '✓ Balanced'
                : `⚠ Discrepancy: ${discrepancy > 0 ? `+${formatNumber(discrepancy)}` : formatNumber(discrepancy)} units`}
            </span>
          ) : (
            <span className="count-check-badge insufficient">Insufficient data</span>
          )}
        </div>
      </div>

      {/* 2. Single Mathematical Equation Bar */}
      <div className="equation-bar">
        <div className="equation-formula">
          <span className="formula-label">Equation:</span>{' '}
          <span className="formula-text">Actual output = Good units + Rejected units</span>
          {hasBalanceValues && (
            <span className="formula-calc">
              ({formatNumber(actualQty)} = {formatNumber(goodQty)} + {formatNumber(rejectQty)})
            </span>
          )}
        </div>
        <div className="equation-scope-note">
          Rework is tracked separately and isolated from the output balance.
        </div>
      </div>

      {/* 3. Four Compact Metrics in One Desktop Row */}
      <div className="count-check-strip">
        {/* Metric 1: Actual Output */}
        <div className="count-check-segment">
          <span className="count-check-label">Actual output</span>
          <div className="count-check-value-row">
            <span className="count-check-val">
              {hasNumber(actualQty) ? formatNumber(actualQty) : '—'}
            </span>
            <span className="count-check-unit">units</span>
          </div>
          <span className="count-check-subtext">Total reported units produced</span>
        </div>

        {/* Metric 2: Good Units & Good-Output Yield */}
        <div className="count-check-segment">
          <span className="count-check-label">Good units</span>
          <div className="count-check-value-row">
            <span className="count-check-val">
              {hasNumber(goodQty) ? formatNumber(goodQty) : '—'}
            </span>
            <span className="count-check-unit">units</span>
          </div>
          <span className="count-check-subtext">
            {hasNumber(goodRate)
              ? `${formatPercent(goodRate)} Good-output yield (good ÷ actual)`
              : 'Yield unavailable'}
          </span>
        </div>

        {/* Metric 3: Rejected Units & Scrap Rate */}
        <div className="count-check-segment">
          <span className="count-check-label">Rejected units</span>
          <div className="count-check-value-row">
            <span className="count-check-val">
              {hasNumber(rejectQty) ? formatNumber(rejectQty) : '—'}
            </span>
            <span className="count-check-unit">units</span>
          </div>
          <span className="count-check-subtext">
            {hasNumber(rejectRate)
              ? `${formatPercent(rejectRate)} Rejection rate (reject ÷ actual)`
              : 'Rate unavailable'}
          </span>
        </div>

        {/* Metric 4: Reworked Units (Isolated) */}
        <div className="count-check-segment">
          <span className="count-check-label">Reworked units</span>
          <div className="count-check-value-row">
            <span className="count-check-val">
              {hasNumber(reworkQty) ? formatNumber(reworkQty) : '—'}
            </span>
            <span className="count-check-unit">units</span>
          </div>
          <span className="count-check-subtext">
            {hasNumber(reworkRate)
              ? `${formatPercent(reworkRate)} Reworked · Tracked separately`
              : 'Rework isolated'}
          </span>
        </div>
      </div>

      {/* 4. Accessible Disclosure: How These Metrics Are Calculated */}
      <details className="production-disclosure">
        <summary>How these metrics are calculated</summary>
        <div className="disclosure-grid">
          <div className="disclosure-card">
            <strong>Good-output yield</strong>
            <p>
              Calculated as <code>Good units ÷ Total actual output</code> (
              {hasNumber(goodRate) ? formatPercent(goodRate) : '—'}). Evaluates good units produced against total line throughput.
            </p>
          </div>
          <div className="disclosure-card">
            <strong>First-pass yield requirements</strong>
            <p>
              True first-pass yield requires verifying that each unit passed inspection on the initial run without any intermediate rework or re-testing. In this dataset, rework ({hasNumber(reworkQty) ? formatNumber(reworkQty) : '—'} units) is tracked as an offline segregated metric, so good-output yield is reported.
            </p>
          </div>
          <div className="disclosure-card">
            <strong>OEE limitations</strong>
            <p>
              Standard Overall Equipment Effectiveness (OEE) is not computed because production calendar shifts, ideal cycle times, and operational availability baselines are not established by this telemetry dataset.
            </p>
          </div>
          <div className="disclosure-card">
            <strong>Tariff &amp; emissions assumptions</strong>
            <p>
              Energy cost reflects a standard commercial tariff of ₹8.25/kWh. Carbon emissions reflect a regional grid emissions factor of 0.716 kg CO₂e/kWh based on regional generation mix.
            </p>
          </div>
          <div className="disclosure-card">
            <strong>Quantity balance equation</strong>
            <p>
              <code>Actual output = Good units + Rejected units</code>. Because rework operations take place offline, units undergoing rework are not double-counted in the physical line output balance.
            </p>
          </div>
        </div>
      </details>
    </div>
  );
}
