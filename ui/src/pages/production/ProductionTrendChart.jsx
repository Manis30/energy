import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { formatDate, formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

function CustomDailyProdTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.date ? formatDate(data.date) : label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val text-success">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rejected Units:</span>
          <span className="tooltip-val text-danger">
            {formatNumber(data.reject_qty)} units ({formatPercent(data.reject_rate)})
          </span>
        </div>
        {hasNumber(data.good_rate) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Quality Yield:</span>
            <span className="tooltip-val">{formatPercent(data.good_rate)}</span>
          </div>
        )}
        {hasNumber(data.downtime_min) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Reported Downtime:</span>
            <span className="tooltip-val">{formatNumber(data.downtime_min)} min</span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

export default function ProductionTrendChart({
  dailyTrend = [],
  dataAvailable = true,
  selectedPlant,
  selectedLine,
}) {
  const chartData = (dailyTrend || []).map((item) => ({
    ...item,
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));

  const validOutputDays = chartData.filter((item) => hasNumber(item.actual_qty));

  let peakDay = null;
  let minDay = null;
  if (validOutputDays.length > 0) {
    peakDay = validOutputDays.reduce(
      (prev, curr) => (Number(curr.actual_qty) > Number(prev.actual_qty) ? curr : prev),
      validOutputDays[0]
    );
    minDay = validOutputDays.reduce(
      (prev, curr) => (Number(curr.actual_qty) < Number(prev.actual_qty) ? curr : prev),
      validOutputDays[0]
    );
  }

  const scopeLabel = selectedLine
    ? `Line ${selectedLine}`
    : selectedPlant
      ? `Plant ${selectedPlant}`
      : 'All Plants (Consolidated)';

  const tickInterval = chartData.length > 60 ? 7 : chartData.length > 20 ? 3 : 0;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Production Trend</h3>
          <p className="section-desc">
            Daily throughput for {scopeLabel}. Actual output contains good and rejected units (non-additive series).
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">{scopeLabel}</span>
          {peakDay && hasNumber(peakDay.actual_qty) && (
            <span className="section-tag process">
              Peak: {formatDate(peakDay.date)} ({formatNumber(peakDay.actual_qty)} units)
            </span>
          )}
          {minDay && hasNumber(minDay.actual_qty) && (
            <span className="section-tag utility">
              Min: {formatDate(minDay.date)} ({formatNumber(minDay.actual_qty)} units)
            </span>
          )}
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Daily Actual, Good &amp; Rejected Units</h4>
            <span className="chart-card-subtitle">
              Daily aggregates across active lines · Actual = Good + Rejected
            </span>
          </div>
          <div className="chart-legend-custom">
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-blue)' }}></span>
              Actual Output
            </span>
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--status-success, #10b981)' }}></span>
              Good Units
            </span>
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-orange)' }}></span>
              Rejected Units
            </span>
          </div>
        </div>

        <div
          className="chart-wrapper"
          role="group"
          aria-label="Daily production bar chart showing actual, good, and rejected output units by date"
        >
          {!dataAvailable || chartData.length === 0 || validOutputDays.length === 0 ? (
            <div className="chart-empty-state">
              {!dataAvailable
                ? 'Daily production trend data could not be retrieved from the server.'
                : chartData.length === 0
                  ? 'No daily production records returned for the selected filter period.'
                  : 'Daily records were returned without valid actual output values.'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                <XAxis
                  dataKey="displayDate"
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                  interval={tickInterval}
                />
                <YAxis
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                  tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip content={<CustomDailyProdTooltip />} />
                <Bar dataKey="actual_qty" fill="var(--brand-blue)" radius={[2, 2, 0, 0]} name="Actual Output" />
                <Bar dataKey="good_qty" fill="var(--status-success, #10b981)" radius={[2, 2, 0, 0]} name="Good Units" />
                <Bar dataKey="reject_qty" fill="var(--brand-orange)" radius={[2, 2, 0, 0]} name="Rejected Units" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
