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
          <span className="tooltip-label">Defects / Scrap:</span>
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

export default function ProductionTrendChart({ dailyTrend = [] }) {
  const chartData = (dailyTrend || []).map((item) => ({
    ...item,
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));

  // Find peak output day and lowest output day
  let peakDay = null;
  let minDay = null;
  if (chartData.length > 0) {
    peakDay = chartData.reduce((prev, curr) => (curr.actual_qty > prev.actual_qty ? curr : prev), chartData[0]);
    minDay = chartData.reduce((prev, curr) => (curr.actual_qty < prev.actual_qty ? curr : prev), chartData[0]);
  }

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Production Output & Scrap Trend</h3>
          <p className="section-desc">
            Aggregated factory manufacturing output and defect occurrences across 92 operating days.
          </p>
        </div>
        {peakDay && (
          <div className="section-tag-group">
            <span className="section-tag info">
              Peak: {peakDay.date} ({formatNumber(peakDay.actual_qty)} units)
            </span>
            <span className="section-tag scrap">
              Min: {minDay.date} ({formatNumber(minDay.actual_qty)} units)
            </span>
          </div>
        )}
      </div>

      <div className="chart-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Daily Units Produced (Actual vs Good vs Defective)</h4>
            <span className="chart-card-subtitle">
              Measured across all active manufacturing lines • Temporal resolution: Daily aggregate
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
              Scrap Units
            </span>
          </div>
        </div>

        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height={320}>
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
              <Bar dataKey="reject_qty" fill="var(--brand-orange)" radius={[2, 2, 0, 0]} name="Scrap Units" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

