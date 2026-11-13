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
import { formatNumber, formatPercent } from '../../utils/formatters';

function CustomDailyProdTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.date || label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">First-Pass Good:</span>
          <span className="tooltip-val text-success">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rejected Units:</span>
          <span className="tooltip-val text-danger">{formatNumber(data.reject_qty)} units ({formatPercent(data.reject_rate)})</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Quality Yield:</span>
          <span className="tooltip-val">{formatPercent(data.good_rate)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Downtime:</span>
          <span className="tooltip-val">{formatNumber(data.downtime_min)} min</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function ProductionTrendChart({ dailyTrend = [], dataAvailable = true }) {
  const chartData = (dailyTrend || []).map((item) => ({
    ...item,
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));
  const validOutputDays = chartData.filter((item) => (
    item.actual_qty !== null
    && item.actual_qty !== undefined
    && Number.isFinite(Number(item.actual_qty))
  ));
  const returnedDates = chartData
    .map((item) => item.date)
    .filter((date) => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();

  let peakDay = null;
  let minDay = null;
  if (validOutputDays.length > 0) {
    peakDay = validOutputDays.reduce((prev, curr) => (
      Number(curr.actual_qty) > Number(prev.actual_qty) ? curr : prev
    ), validOutputDays[0]);
    minDay = validOutputDays.reduce((prev, curr) => (
      Number(curr.actual_qty) < Number(prev.actual_qty) ? curr : prev
    ), validOutputDays[0]);
  }

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Production Output & Rejected Quantity Trend</h3>
          <p className="section-desc">
            {dataAvailable
              ? `${chartData.length} returned daily record(s)${returnedDates.length > 0 ? `, ${returnedDates[0]} to ${returnedDates[returnedDates.length - 1]}` : ''}.`
              : 'Daily production trend data is unavailable.'}
          </p>
        </div>
        {peakDay && (
          <div className="section-tag-group">
            <>
            <span className="section-tag info">
              Peak returned actual output: {peakDay.date} ({formatNumber(peakDay.actual_qty)} units)
            </span>
            <span className="section-tag scrap">
              Lowest returned actual output: {minDay.date} ({formatNumber(minDay.actual_qty)} units)
            </span>
            </>
          </div>
        )}
      </div>

      <div className="chart-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Daily Actual, Good &amp; Rejected Units</h4>
            <span className="chart-card-subtitle">
              Returned daily aggregates. Actual includes good and rejected units; these series are not additive.
            </span>
          </div>
          <div className="chart-legend-custom">
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-blue)' }}></span>
              Actual Output
            </span>
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--chart-cat-4)' }}></span>
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
          aria-label="Daily production bar chart showing actual, good, and rejected output units by date; actual includes good and rejected output"
        >
          {!dataAvailable || chartData.length === 0 || validOutputDays.length === 0 ? (
            <div className="chart-empty-state">
              {!dataAvailable
                ? 'Daily production trend request failed.'
                : chartData.length === 0
                  ? 'No daily production records were returned.'
                  : 'Daily records were returned without a usable actual-output value.'}
            </div>
          ) : <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
              <XAxis
                dataKey="displayDate"
                stroke="var(--chart-axis)"
                tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                tickLine={false}
                interval={7}
              />
              <YAxis
                stroke="var(--chart-axis)"
                tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                tickLine={false}
                tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomDailyProdTooltip />} />
              <Bar dataKey="actual_qty" fill="var(--brand-blue)" radius={[2, 2, 0, 0]} name="Actual Output" />
              <Bar dataKey="good_qty" fill="var(--chart-cat-4)" radius={[2, 2, 0, 0]} name="Good Units" />
              <Bar dataKey="reject_qty" fill="var(--brand-orange)" radius={[2, 2, 0, 0]} name="Rejected Units" />
            </BarChart>
          </ResponsiveContainer>}
        </div>
      </div>
    </div>
  );
}

