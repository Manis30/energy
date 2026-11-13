import React, { useMemo } from 'react';
import { formatDate, formatNumber } from '../../utils/formatters';
import './EnergyPerformanceExceptions.css';

const MINIMUM_OBSERVATIONS = 8;
const IQR_FENCE_MULTIPLIER = 1.5;

const isValidDate = (value) => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
};

function toNonNegativeNumber(value) {
  if (typeof value === 'string' && value.trim() === '') return null;
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function makeDailyMap(records, valueField) {
  const byDate = new Map();
  let invalidDateCount = 0;

  (Array.isArray(records) ? records : []).forEach((record) => {
    if (!isValidDate(record?.date)) {
      invalidDateCount += 1;
      return;
    }

    if (byDate.has(record.date)) {
      byDate.set(record.date, { duplicate: true, value: null });
      return;
    }

    byDate.set(record.date, {
      duplicate: false,
      value: toNonNegativeNumber(record?.[valueField]),
    });
  });

  const duplicateDateCount = [...byDate.values()].filter((entry) => entry.duplicate).length;
  const unavailableValueCount = [...byDate.values()]
    .filter((entry) => !entry.duplicate && entry.value === null).length;

  return {
    byDate,
    invalidDateCount,
    duplicateDateCount,
    unavailableValueCount,
  };
}

function median(sortedValues) {
  const middle = Math.floor(sortedValues.length / 2);
  return sortedValues.length % 2 === 0
    ? (sortedValues[middle - 1] + sortedValues[middle]) / 2
    : sortedValues[middle];
}

function calculateStatistics(energyMap) {
  const observations = [...energyMap.byDate.entries()]
    .filter(([, entry]) => !entry.duplicate && entry.value !== null)
    .map(([date, entry]) => ({ date, value: entry.value }))
    .sort((left, right) => left.date.localeCompare(right.date));

  if (observations.length < MINIMUM_OBSERVATIONS) {
    return {
      available: false,
      observations,
      median: null,
      q1: null,
      q3: null,
      iqr: null,
      lowerFence: null,
      upperFence: null,
      highExceptions: [],
      lowExceptions: [],
    };
  }

  const sortedValues = observations.map((item) => item.value).sort((left, right) => left - right);
  const half = Math.floor(sortedValues.length / 2);
  const lowerHalf = sortedValues.slice(0, half);
  const upperHalf = sortedValues.slice(Math.ceil(sortedValues.length / 2));
  const q1 = median(lowerHalf);
  const q3 = median(upperHalf);
  const iqr = q3 - q1;
  const lowerFence = q1 - IQR_FENCE_MULTIPLIER * iqr;
  const upperFence = q3 + IQR_FENCE_MULTIPLIER * iqr;

  return {
    available: true,
    observations,
    median: median(sortedValues),
    q1,
    q3,
    iqr,
    lowerFence,
    upperFence,
    highExceptions: observations.filter((item) => item.value > upperFence),
    lowExceptions: observations.filter((item) => item.value > 0 && item.value < lowerFence),
  };
}

function formatKwh(value) {
  return value === null || value === undefined ? 'Unavailable' : `${formatNumber(value, 2)} kWh`;
}

function formatEntry(entry, unit, decimals) {
  if (!entry) return 'No record';
  if (entry.duplicate) return 'Ambiguous duplicate records';
  if (entry.value === null) return 'Value unavailable';
  return `${formatNumber(entry.value, decimals)} ${unit}`;
}

function ExceptionEvidence({ exception, type, statistics }) {
  const referenceFence = type === 'high' ? statistics.upperFence : statistics.lowerFence;
  const referenceLabel = type === 'high' ? 'Upper fence' : 'Lower fence';

  return (
    <li className="energy-exception-item">
      <details>
        <summary>
          <span>{formatDate(exception.date)}</span>
          <strong>{formatKwh(exception.value)}</strong>
        </summary>
        <div className="energy-exception-evidence">
          <span>{referenceLabel}: {formatKwh(referenceFence)}</span>
          <span>Historical median: {formatKwh(statistics.median)}</span>
          <span>Q1: {formatKwh(statistics.q1)} · Q3: {formatKwh(statistics.q3)} · IQR: {formatKwh(statistics.iqr)}</span>
          <span>Based on {statistics.observations.length} valid unique daily observations.</span>
        </div>
      </details>
    </li>
  );
}

function ExceptionCategory({ title, count, children, unavailable = false }) {
  return (
    <details className="energy-exception-category">
      <summary>
        <span>{title}</span>
        <strong>{unavailable ? 'Unavailable' : count}</strong>
      </summary>
      <div className="energy-exception-category-content">{children}</div>
    </details>
  );
}

export default function EnergyPerformanceExceptions({
  energyTrend = [],
  productionTrend = [],
  energyAvailable = false,
  productionAvailable = false,
  selectedPlant,
  dataScope,
}) {
  const energyData = useMemo(() => makeDailyMap(energyTrend, 'consumption_kwh'), [energyTrend]);
  const productionData = useMemo(() => makeDailyMap(productionTrend, 'actual_qty'), [productionTrend]);
  const statistics = useMemo(() => calculateStatistics(energyData), [energyData]);

  const reportingDates = useMemo(() => [...new Set([
    ...energyData.byDate.keys(),
    ...productionData.byDate.keys(),
  ])].sort(), [energyData.byDate, productionData.byDate]);

  const energyWithoutProduction = reportingDates
    .filter((date) => energyData.byDate.has(date) && !productionData.byDate.has(date))
    .map((date) => ({ date, energy: energyData.byDate.get(date) }));
  const productionWithoutEnergy = reportingDates
    .filter((date) => productionData.byDate.has(date) && !energyData.byDate.has(date))
    .map((date) => ({ date, production: productionData.byDate.get(date) }));

  const scopeMatches = dataScope === selectedPlant;
  const statisticsAvailable = energyAvailable && statistics.available;
  const gapsAvailable = energyAvailable && productionAvailable && reportingDates.length > 0;
  const repeatedHighCount = statisticsAvailable && statistics.highExceptions.length >= 2
    ? statistics.highExceptions.length
    : 0;
  const energyDates = [...energyData.byDate.keys()].sort();
  const energyDateRange = energyDates.length > 0
    ? `${formatDate(energyDates[0])} – ${formatDate(energyDates[energyDates.length - 1])}`
    : null;

  return (
    <section className="dashboard-section energy-performance-exceptions">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Energy Performance Exceptions</h3>
          <p className="section-desc">
            Descriptive checks for unusual daily readings and one-sided reporting dates; findings are not confirmed faults or waste.
          </p>
        </div>
        <span className="energy-exceptions-scope">{selectedPlant || 'All plants'}</span>
      </div>

      {!scopeMatches ? (
        <p className="energy-exceptions-state" role="status" aria-live="polite">
          Loading energy and production records for the selected plant scope.
        </p>
      ) : (
        <>
          <div className="energy-exceptions-summary" role="group" aria-label="Exception counts">
            <div>
              <span>Unusually high consumption</span>
              <strong>{statisticsAvailable ? statistics.highExceptions.length : 'Unavailable'}</strong>
            </div>
            <div>
              <span>Unusually low positive consumption</span>
              <strong>{statisticsAvailable ? statistics.lowExceptions.length : 'Unavailable'}</strong>
            </div>
            <div>
              <span>One-sided reporting dates</span>
              <strong>{gapsAvailable ? energyWithoutProduction.length + productionWithoutEnergy.length : 'Unavailable'}</strong>
            </div>
            <div>
              <span>Repeated high-consumption dates</span>
              <strong>{statisticsAvailable ? repeatedHighCount : 'Unavailable'}</strong>
            </div>
          </div>

          <p className="energy-exceptions-period">
            Plant scope: <strong>{selectedPlant || 'All plants'}</strong>
            {energyDateRange && <> · Energy dates returned: <strong>{energyDateRange}</strong></>}
            {energyAvailable && <> · Valid unique energy observations: <strong>{statistics.observations.length}</strong></>}
          </p>

          <details className="energy-exceptions-method">
            <summary>Statistical method and eligibility</summary>
            <div>
              <p>
                High and low exceptions use Tukey fences: Q1 − 1.5 × IQR and Q3 + 1.5 × IQR, where Q1 and Q3 are medians of the lower and upper halves of the sorted valid daily values. A value above the upper fence is unusually high; a positive value below the lower fence is unusually low.
              </p>
              <p>
                At least {MINIMUM_OBSERVATIONS} valid, unique, dated energy observations are required. Zero readings may contribute to the distribution but are never classified as low-consumption exceptions. This is a retrospective description of returned records, not a forecast or expected-energy baseline.
              </p>
            </div>
          </details>

          {!energyAvailable && (
            <p className="energy-exceptions-state" role="status">
              Daily energy trend is unavailable. Statistical exception counts cannot be calculated.
            </p>
          )}

          <div className="energy-exceptions-categories">
            <ExceptionCategory
              title="Unusually high daily consumption"
              count={statistics.highExceptions.length}
              unavailable={!energyAvailable || !statistics.available}
            >
              {!energyAvailable ? (
                <p className="energy-exceptions-state">Unavailable: the daily energy trend request failed or returned no usable response.</p>
              ) : !statistics.available ? (
                <p className="energy-exceptions-state">
                  Insufficient data: {statistics.observations.length} valid unique observations returned; at least {MINIMUM_OBSERVATIONS} are required.
                </p>
              ) : statistics.highExceptions.length === 0 ? (
                <p className="energy-exceptions-state">No daily values exceeded the observed upper fence.</p>
              ) : (
                <>
                  <p className="energy-exceptions-state">
                    These values exceed the historical upper fence of {formatKwh(statistics.upperFence)}. They are statistical exceptions, not confirmed faults or waste.
                  </p>
                  <ul className="energy-exception-list">
                    {statistics.highExceptions.map((item) => (
                      <ExceptionEvidence key={item.date} exception={item} type="high" statistics={statistics} />
                    ))}
                  </ul>
                </>
              )}
            </ExceptionCategory>

            <ExceptionCategory
              title="Unusually low positive consumption"
              count={statistics.lowExceptions.length}
              unavailable={!energyAvailable || !statistics.available}
            >
              {!energyAvailable ? (
                <p className="energy-exceptions-state">Unavailable: the daily energy trend request failed or returned no usable response.</p>
              ) : !statistics.available ? (
                <p className="energy-exceptions-state">
                  Insufficient data: {statistics.observations.length} valid unique observations returned; at least {MINIMUM_OBSERVATIONS} are required.
                </p>
              ) : statistics.lowExceptions.length === 0 ? (
                <p className="energy-exceptions-state">
                  No positive daily values fell below the observed lower fence. Zero readings are not classified as low-consumption exceptions.
                </p>
              ) : (
                <>
                  <p className="energy-exceptions-state">
                    These positive values are below the historical lower fence of {formatKwh(statistics.lowerFence)}.
                  </p>
                  <ul className="energy-exception-list">
                    {statistics.lowExceptions.map((item) => (
                      <ExceptionEvidence key={item.date} exception={item} type="low" statistics={statistics} />
                    ))}
                  </ul>
                </>
              )}
            </ExceptionCategory>

            <ExceptionCategory
              title="Energy and production reporting gaps"
              count={energyWithoutProduction.length + productionWithoutEnergy.length}
              unavailable={!gapsAvailable}
            >
              {!energyAvailable || !productionAvailable ? (
                <p className="energy-exceptions-state">
                  Unavailable: both daily trend requests must succeed to compare reporting dates.
                </p>
              ) : reportingDates.length === 0 ? (
                <p className="energy-exceptions-state">
                  No valid dated records were returned by either trend; reporting coverage cannot be assessed.
                </p>
              ) : energyWithoutProduction.length === 0 && productionWithoutEnergy.length === 0 ? (
                <p className="energy-exceptions-state">No one-sided reporting dates were observed among the returned records. This does not establish completeness outside those dates.</p>
              ) : (
                <div className="energy-exception-gap-lists">
                  {energyWithoutProduction.length > 0 && (
                    <div>
                      <h5>Energy record exists; production record missing ({energyWithoutProduction.length})</h5>
                      <ul>
                        {energyWithoutProduction.map(({ date, energy }) => (
                          <li key={date}>
                            <strong>{formatDate(date)}</strong>
                            <span>{formatEntry(energy, 'kWh', 2)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {productionWithoutEnergy.length > 0 && (
                    <div>
                      <h5>Production record exists; energy record missing ({productionWithoutEnergy.length})</h5>
                      <ul>
                        {productionWithoutEnergy.map(({ date, production }) => (
                          <li key={date}>
                            <strong>{formatDate(date)}</strong>
                            <span>{formatEntry(production, 'units', 0)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </ExceptionCategory>

            <ExceptionCategory
              title="Repeated high-consumption observations"
              count={repeatedHighCount}
              unavailable={!energyAvailable || !statistics.available}
            >
              {!energyAvailable ? (
                <p className="energy-exceptions-state">Unavailable: the daily energy trend request failed or returned no usable response.</p>
              ) : !statistics.available ? (
                <p className="energy-exceptions-state">
                  Insufficient data: at least {MINIMUM_OBSERVATIONS} valid unique observations are required.
                </p>
              ) : statistics.highExceptions.length < 2 ? (
                <p className="energy-exceptions-state">
                  No repeated high-consumption observations: at least two statistical high dates are needed to describe recurrence.
                </p>
              ) : (
                <>
                  <p className="energy-exceptions-state">
                    {statistics.highExceptions.length} dates exceeded the same historical upper fence. Recurrence does not identify a cause or equipment fault.
                  </p>
                  <ul className="energy-exception-list">
                    {statistics.highExceptions.map((item) => (
                      <ExceptionEvidence key={item.date} exception={item} type="high" statistics={statistics} />
                    ))}
                  </ul>
                </>
              )}
            </ExceptionCategory>
          </div>

          {(energyData.invalidDateCount > 0
            || energyData.duplicateDateCount > 0
            || energyData.unavailableValueCount > 0
            || productionData.invalidDateCount > 0
            || productionData.duplicateDateCount > 0
            || productionData.unavailableValueCount > 0) && (
            <details className="energy-exceptions-exclusions">
              <summary>Excluded or unavailable records</summary>
              <ul>
                <li>Energy invalid-date records omitted: {energyData.invalidDateCount}.</li>
                <li>Energy duplicate dates excluded from statistical calculations: {energyData.duplicateDateCount}.</li>
                <li>Unique energy dates with unavailable or invalid consumption: {energyData.unavailableValueCount}.</li>
                <li>Production invalid-date records omitted from date matching: {productionData.invalidDateCount}.</li>
                <li>Production duplicate dates are treated as ambiguous for their reported value: {productionData.duplicateDateCount}.</li>
                <li>Unique production dates with unavailable or invalid output: {productionData.unavailableValueCount}.</li>
              </ul>
            </details>
          )}

          <p className="energy-exceptions-disclaimer">
            These checks describe only the returned daily records in the current plant scope. They do not establish faults, avoidable waste, savings, or causal relationships.
          </p>
        </>
      )}
    </section>
  );
}
