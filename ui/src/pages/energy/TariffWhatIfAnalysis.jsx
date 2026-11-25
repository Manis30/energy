import React, { useState } from 'react';
import { formatCurrency, formatDate, formatNumber, formatPercent } from '../../utils/formatters';
import './TariffWhatIfAnalysis.css';

const MAX_SAFE_AMOUNT = Number.MAX_SAFE_INTEGER;

const hasNumber = (value) => value !== null
  && value !== undefined
  && !(typeof value === 'string' && value.trim() === '')
  && Number.isFinite(Number(value));

export default function TariffWhatIfAnalysis({
  energySummary,
  summaryAvailable = false,
  dateRange,
  selectedPlant,
  selectedShift = 'ALL',
}) {
  const [tariffInput, setTariffInput] = useState('');
  const rawTariff = tariffInput.trim();
  const tariff = rawTariff === '' ? null : Number(rawTariff);
  const tariffError = rawTariff !== '' && (
    !Number.isFinite(tariff)
    || tariff < 0
    || tariff > MAX_SAFE_AMOUNT
  )
    ? 'Enter a non-negative tariff within the safe numeric range.'
    : '';

  const consumption = hasNumber(energySummary?.total_consumption_kwh)
    ? Number(energySummary.total_consumption_kwh)
    : null;
  const referenceCost = hasNumber(energySummary?.total_cost_inr)
    ? Number(energySummary.total_cost_inr)
    : null;
  const validConsumption = summaryAvailable
    && consumption !== null
    && consumption >= 0
    && consumption <= MAX_SAFE_AMOUNT;
  const validReferenceCost = summaryAvailable
    && referenceCost !== null
    && referenceCost >= 0
    && referenceCost <= MAX_SAFE_AMOUNT;
  const canCalculate = validConsumption
    && tariff !== null
    && !tariffError;
  const calculatedScenarioCost = canCalculate ? consumption * tariff : null;
  const scenarioCost = calculatedScenarioCost !== null
    && Number.isFinite(calculatedScenarioCost)
    && calculatedScenarioCost <= MAX_SAFE_AMOUNT
    ? calculatedScenarioCost
    : null;
  const scenarioCostOverflowed = canCalculate && scenarioCost === null;
  const costDifference = scenarioCost !== null && validReferenceCost
    ? scenarioCost - referenceCost
    : null;
  const percentageDifference = costDifference !== null && referenceCost > 0
    ? (costDifference / referenceCost) * 100
    : null;
  const safePercentageDifference = percentageDifference !== null
    && Number.isFinite(percentageDifference)
    && Math.abs(percentageDifference) <= MAX_SAFE_AMOUNT
    ? percentageDifference
    : null;

  const dateCoverage = dateRange
    ? `${formatDate(dateRange.start_date)} – ${formatDate(dateRange.end_date)}`
    : 'Unavailable from returned daily trend data';
  const scope = selectedPlant ? `Plant ${selectedPlant}` : 'All plants';

  const differenceLabel = (value, formatter) => {
    if (value === null) return 'Unavailable';
    const sign = value > 0 ? '+' : value < 0 ? '−' : '';
    return `${sign}${formatter(Math.abs(value))}`;
  };

  return (
    <details className="tariff-what-if">
      <summary className="tariff-what-if-summary">
        <div>
          <h3 className="tariff-what-if-title">Tariff What-if Analysis</h3>
          <span className="tariff-what-if-subtitle">Explore a hypothetical flat-rate cost using returned energy consumption</span>
        </div>
        <svg className="tariff-what-if-chevron" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </summary>

      <div className="tariff-what-if-content">
        <p className="tariff-what-if-scope">
          {scope} · Returned daily-trend coverage: {dateCoverage}. This view has no separate date-range selector.
        </p>
        <p className="tariff-what-if-disclaimer">
          This is a hypothetical scenario only. The entered rate does not change the stored tariff or historical calculations.
          It excludes time-of-use rates, demand charges, taxes, penalties, and fixed charges.
        </p>
        {selectedShift && selectedShift !== 'ALL' && (
          <p className="tariff-what-if-disclaimer" style={{ color: '#b45309', fontWeight: 600 }}>
            Notice: Contractual tariff what-if modeling applies to facility-wide utility billing (available only for all shifts combined).
          </p>
        )}

        <div className="tariff-what-if-layout">
          <div className="tariff-what-if-input-panel">
            <label htmlFor="tariff-what-if-rate">Hypothetical electricity tariff</label>
            <div className={`tariff-what-if-input-wrap${tariffError ? ' has-error' : ''}`}>
              <span aria-hidden="true">₹</span>
              <input
                id="tariff-what-if-rate"
                type="number"
                min="0"
                max={MAX_SAFE_AMOUNT}
                step="any"
                inputMode="decimal"
                value={tariffInput}
                onChange={(event) => setTariffInput(event.target.value)}
                aria-invalid={Boolean(tariffError)}
                aria-describedby="tariff-what-if-help tariff-what-if-error"
                placeholder="e.g. 8.50"
              />
              <span className="tariff-what-if-unit">INR/kWh</span>
            </div>
            <p id="tariff-what-if-help" className="tariff-what-if-help">
              Enter a non-negative rate. Zero is valid; the scenario uses the value as entered. Extremely large values outside the safe numeric range are rejected.
            </p>
            <p id="tariff-what-if-error" className="tariff-what-if-error" role="status" aria-live="polite">
              {tariffError || (scenarioCostOverflowed
                ? 'The scenario amount exceeds the safe numeric range and cannot be displayed.'
                : '')}
            </p>
            <button
              type="button"
              className="tariff-what-if-reset"
              onClick={() => setTariffInput('')}
              disabled={tariffInput === ''}
            >
              Reset tariff
            </button>
          </div>

          <div className="tariff-what-if-results">
            <section className="tariff-what-if-result-group" aria-labelledby="tariff-what-if-reference-title">
              <h4 id="tariff-what-if-reference-title">Historical reference</h4>
              <div className="tariff-what-if-metric">
                <span>Reference energy consumption</span>
                <strong>
                  {validConsumption ? `${formatNumber(consumption, 2)} kWh` : 'Unavailable'}
                </strong>
              </div>
              <div className="tariff-what-if-metric">
                <span>Dataset-calculated cost</span>
                <strong>{validReferenceCost ? formatCurrency(referenceCost) : 'Unavailable'}</strong>
              </div>
              {!summaryAvailable && (
                <p className="tariff-what-if-unavailable">Energy summary could not be retrieved.</p>
              )}
              {summaryAvailable && !validConsumption && (
                <p className="tariff-what-if-unavailable">Energy consumption is unavailable or invalid; it is not treated as zero.</p>
              )}
            </section>

            <section className="tariff-what-if-result-group hypothetical" aria-labelledby="tariff-what-if-scenario-title">
              <h4 id="tariff-what-if-scenario-title">Hypothetical scenario</h4>
              <p className="tariff-what-if-formula">Scenario cost = reference kWh × entered INR/kWh</p>
              <div className="tariff-what-if-metric">
                <span>Scenario cost</span>
                <strong>{scenarioCost === null ? 'Not calculated' : formatCurrency(scenarioCost)}</strong>
              </div>
              <div className="tariff-what-if-metric">
                <span>Cost difference vs dataset cost</span>
                <strong>{differenceLabel(costDifference, (value) => formatCurrency(value))}</strong>
              </div>
              <div className="tariff-what-if-metric">
                <span>Percentage difference vs dataset cost</span>
                <strong>{differenceLabel(safePercentageDifference, (value) => formatPercent(value))}</strong>
              </div>
              <p className="tariff-what-if-unavailable">
                {scenarioCost === null
                  ? tariffError || (scenarioCostOverflowed
                    ? 'Scenario is outside the safe numeric range.'
                    : !validConsumption
                      ? 'A valid reference energy total is required.'
                      : 'Enter a hypothetical tariff to calculate the scenario.')
                  : !validReferenceCost
                    ? 'Difference unavailable because the dataset-calculated cost is unavailable.'
                    : referenceCost === 0
                      ? 'Percentage difference unavailable because the dataset-calculated cost is zero.'
                      : 'A positive difference means the scenario is higher; a negative difference is not a claim of achieved savings.'}
              </p>
            </section>
          </div>
        </div>
      </div>
    </details>
  );
}
