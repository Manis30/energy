import React, { useMemo } from 'react';
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatDate, formatNumber } from '../../utils/formatters';
import './EnergyProductionRelationship.css';

const isValidDate = (value) => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
};

const toNonNegativeNumber = (value) => {
  if (typeof value === 'string' && value.trim() === '') return null;
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
};

function makeDailyMap(records, valueField) {
  const byDate = new Map();
  let invalidDateCount = 0;
  let duplicateDateCount = 0;

  (Array.isArray(records) ? records : []).forEach((record) => {
    if (!isValidDate(record?.date)) {
      invalidDateCount += 1;
      return;
    }

    if (byDate.has(record.date)) {
      const previous = byDate.get(record.date);
      if (!previous.duplicate) duplicateDateCount += 1;
      byDate.set(record.date, { duplicate: true, value: null });
      return;
    }

    byDate.set(record.date, {
      duplicate: false,
      value: toNonNegativeNumber(record?.[valueField]),
    });
  });

  return { byDate, invalidDateCount, duplicateDateCount };
}

function getPearsonCorrelation(observations) {
  if (observations.length < 3) {
    return { value: null, reason: 'At least 3 matched dates are required.' };
  }

  const energyValues = observations.map((item) => item.consumption_kwh);
  const outputValues = observations.map((item) => item.actual_qty);
  if (new Set(energyValues).size < 2 || new Set(outputValues).size < 2) {
    return { value: null, reason: 'Both measures need variation across matched dates.' };
  }

  const energyMean = energyValues.reduce((sum, value) => sum + value, 0) / energyValues.length;
  const outputMean = outputValues.reduce((sum, value) => sum + value, 0) / outputValues.length;
  let covariance = 0;
  let energyVariance = 0;
  let outputVariance = 0;

  observations.forEach((item) => {
    const energyDelta = item.consumption_kwh - energyMean;
    const outputDelta = item.actual_qty - outputMean;
    covariance += energyDelta * outputDelta;
    energyVariance += energyDelta * energyDelta;
    outputVariance += outputDelta * outputDelta;
  });

  const denominator = Math.sqrt(energyVariance * outputVariance);
  if (!Number.isFinite(denominator) || denominator === 0) {
    return { value: null, reason: 'Correlation is undefined because the matched values do not vary.' };
  }

  return {
    value: Math.max(-1, Math.min(1, covariance / denominator)),
    reason: '',
  };
}

function RelationshipTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const observation = payload[0]?.payload;
  if (!observation) return null;

  return (
    <div className="energy-relationship-tooltip">
      <strong>{formatDate(observation.date)}</strong>
      <span>Energy consumption: {formatNumber(observation.consumption_kwh, 2)} kWh</span>
      <span>Actual production output: {formatNumber(observation.actual_qty, 0)} units</span>
    </div>
  );
}

function formatCell(entry, unit, decimals) {
  if (!entry) return 'No record';
  if (entry.duplicate) return 'Ambiguous duplicate records';
  if (entry.value === null) return 'Value unavailable';
  return `${formatNumber(entry.value, decimals)} ${unit}`;
}

function getRowStatus(energyEntry, productionEntry) {
  if (!energyEntry && !productionEntry) return 'No records';
  if (!energyEntry) return 'No energy record';
  if (!productionEntry) return 'No production record';
  if (energyEntry.duplicate || productionEntry.duplicate) return 'Ambiguous duplicate records';
  if (energyEntry.value === null || productionEntry.value === null) return 'Value unavailable';
  return 'Matched';
}

export default function EnergyProductionRelationship({
  energyTrend = [],
  productionTrend = [],
  energyAvailable = false,
  productionAvailable = false,
  selectedPlant,
  dataScope,
}) {
  const energyData = useMemo(() => makeDailyMap(energyTrend, 'consumption_kwh'), [energyTrend]);
  const productionData = useMemo(() => makeDailyMap(productionTrend, 'actual_qty'), [productionTrend]);

  const dates = useMemo(() => [...new Set([
    ...energyData.byDate.keys(),
    ...productionData.byDate.keys(),
  ])].sort(), [energyData.byDate, productionData.byDate]);

  const rows = useMemo(() => dates.map((date) => {
    const energyEntry = energyData.byDate.get(date) || null;
    const productionEntry = productionData.byDate.get(date) || null;
    const matched = Boolean(
      energyEntry
      && productionEntry
      && !energyEntry.duplicate
      && !productionEntry.duplicate
      && energyEntry.value !== null
      && productionEntry.value !== null
    );

    return {
      date,
      energyEntry,
      productionEntry,
      matched,
      consumption_kwh: matched ? energyEntry.value : null,
      actual_qty: matched ? productionEntry.value : null,
      status: getRowStatus(energyEntry, productionEntry),
    };
  }), [dates, energyData.byDate, productionData.byDate]);

  const matchedRows = useMemo(() => rows.filter((row) => row.matched), [rows]);
  const correlation = useMemo(() => getPearsonCorrelation(matchedRows), [matchedRows]);
  const chartRows = useMemo(() => matchedRows.map((row) => ({
    ...row,
    x: row.actual_qty,
    y: row.consumption_kwh,
  })), [matchedRows]);
  const energyMissingCount = rows.filter((row) => !row.energyEntry).length;
  const productionMissingCount = rows.filter((row) => !row.productionEntry).length;
  const energyRecordCount = Array.isArray(energyTrend) ? energyTrend.length : 0;
  const productionRecordCount = Array.isArray(productionTrend) ? productionTrend.length : 0;
  const matchedDateRange = matchedRows.length > 0
    ? `${formatDate(matchedRows[0].date)} – ${formatDate(matchedRows[matchedRows.length - 1].date)}`
    : null;
  const scopeMatches = dataScope === selectedPlant;
  const invalidDateSummary = [
    energyData.invalidDateCount > 0
      ? `${energyData.invalidDateCount} energy record(s) had invalid dates.`
      : '',
    productionData.invalidDateCount > 0
      ? `${productionData.invalidDateCount} production record(s) had invalid dates.`
      : '',
  ].filter(Boolean).join(' ');

  return (
    <section className="dashboard-section energy-production-relationship">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Energy vs Production Relationship</h3>
          <p className="section-desc">
            Explore how daily plant energy consumption and actual production output move together. This describes association, not causation or efficiency.
          </p>
        </div>
        <span className="energy-relationship-scope">{selectedPlant || 'All plants'}</span>
      </div>

      {!scopeMatches ? (
        <p className="energy-relationship-state" role="status" aria-live="polite">
          Loading energy and production trends for the selected plant scope.
        </p>
      ) : !energyAvailable ? (
        <p className="energy-relationship-state" role="status">
          Daily energy trend is unavailable; the comparison and correlation are unavailable.
        </p>
      ) : !productionAvailable ? (
        <p className="energy-relationship-state" role="status">
          Daily production trend is unavailable; the comparison and correlation are unavailable.
        </p>
      ) : dates.length === 0 ? (
        <div className="energy-relationship-state" role="status">
          {energyRecordCount === 0 && productionRecordCount === 0
            ? 'Neither API returned daily records for this plant scope. Matched dates: 0. Correlation is unavailable because there are no matched observations.'
            : 'No valid reporting dates were returned, so the daily records cannot be aligned. Matched dates: 0. Correlation is unavailable.'}
          {invalidDateSummary && ` ${invalidDateSummary}`}
        </div>
      ) : (
        <>
          <div className="energy-relationship-summary" role="group" aria-label="Comparison evidence summary">
            <div>
              <span>Matched dates</span>
              <strong>{matchedRows.length}</strong>
              <small>{matchedDateRange || 'No dates matched'}</small>
            </div>
            <div>
              <span>Dates without energy records</span>
              <strong>{energyMissingCount}</strong>
              <small>Production-only dates in the returned data</small>
            </div>
            <div>
              <span>Dates without production records</span>
              <strong>{productionMissingCount}</strong>
              <small>Energy-only dates in the returned data</small>
            </div>
            <div>
              <span>Pearson correlation (r)</span>
              <strong>{correlation.value === null ? 'Unavailable' : correlation.value.toFixed(3)}</strong>
              <small>
                {correlation.value === null
                  ? correlation.reason
                  : 'Descriptive association only; not causation or an efficiency score.'}
              </small>
            </div>
          </div>

          {(energyData.invalidDateCount > 0 || productionData.invalidDateCount > 0
            || energyData.duplicateDateCount > 0 || productionData.duplicateDateCount > 0) && (
            <p className="energy-relationship-state" role="status">
              {energyData.invalidDateCount > 0
                && `${energyData.invalidDateCount} energy record(s) with invalid dates were omitted. `}
              {productionData.invalidDateCount > 0
                && `${productionData.invalidDateCount} production record(s) with invalid dates were omitted. `}
              {energyData.duplicateDateCount > 0
                && `${energyData.duplicateDateCount} energy date(s) with duplicate records are ambiguous. `}
              {productionData.duplicateDateCount > 0
                && `${productionData.duplicateDateCount} production date(s) with duplicate records are ambiguous.`}
            </p>
          )}

          {matchedRows.length === 0 ? (
            <p className="energy-relationship-state" role="status">
              No dates had a unique, usable energy value and production value in both trends. Missing or unavailable values were not treated as zero.
            </p>
          ) : (
            <div className="energy-relationship-chart-card">
              <div className="energy-relationship-chart-heading">
                <h4>Matched daily observations</h4>
                <p>
                  X-axis: actual production output (units, good plus rejected); Y-axis: daily energy consumption (kWh). Each point is one matched date.
                </p>
              </div>
              <div
                className="energy-relationship-chart"
                role="group"
                aria-label="Scatter plot of daily actual production output in units against daily energy consumption in kilowatt-hours for matched dates"
              >
                <ResponsiveContainer width="100%" height={300}>
                  <ScatterChart margin={{ top: 16, right: 18, bottom: 18, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                    <XAxis
                      type="number"
                      dataKey="x"
                      name="Actual production output"
                      unit=" units"
                      tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                      stroke="var(--chart-axis)"
                      tickLine={false}
                      tickFormatter={(value) => formatNumber(value, 0)}
                    />
                    <YAxis
                      type="number"
                      dataKey="y"
                      name="Energy consumption"
                      unit=" kWh"
                      tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                      stroke="var(--chart-axis)"
                      tickLine={false}
                      width={64}
                      tickFormatter={(value) => formatNumber(value, 0)}
                    />
                    <Tooltip content={<RelationshipTooltip />} />
                    <Scatter data={chartRows} fill="var(--brand-purple)" name="Matched dates" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <p className="energy-relationship-chart-note">
                Daily energy consumption (kWh) and actual production output (units; good plus rejected) are shown for {matchedRows.length} matching date(s) in {selectedPlant || 'all plants'} scope.
              </p>
            </div>
          )}

          <details className="energy-relationship-details">
            <summary>View daily records and unmatched dates ({rows.length})</summary>
            <div className="energy-relationship-table-wrap">
              <table className="energy-relationship-table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Energy consumption</th>
                    <th scope="col">Actual production output</th>
                    <th scope="col">Comparison status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.date}>
                      <th scope="row">{formatDate(row.date)}</th>
                      <td>{formatCell(row.energyEntry, 'kWh', 2)}</td>
                      <td>{formatCell(row.productionEntry, 'units', 0)}</td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {matchedDateRange && (
              <p className="energy-relationship-table-note">
                Matched date range: {matchedDateRange}. All rows are from the same requested plant scope; dates are joined exactly, with no interpolation.
              </p>
            )}
          </details>

          <p className="energy-relationship-disclaimer">
            The comparison uses only dates with usable values in both daily trends. A correlation coefficient is descriptive and does not establish causation, predict future consumption, or measure efficiency.
          </p>
        </>
      )}
    </section>
  );
}
