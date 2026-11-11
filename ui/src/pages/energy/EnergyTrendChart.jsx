import React from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { formatCurrency, formatNumber } from '../../utils/formatters';

function CustomDailyTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.date || label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.consumption_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak Hour Load:</span>
          <span className="tooltip-val">{formatNumber(data.peak_hourly_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Daily Cost:</span>
          <span className="tooltip-val">{formatCurrency(data.cost_inr)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Daily CO₂e:</span>
          <span className="tooltip-val">{formatNumber(data.co2e_kg, 2)} kg</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Avg Power Factor:</span>
          <span className="tooltip-val">{data.avg_power_factor ? Number(data.avg_power_factor).toFixed(4) : '—'}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function EnergyTrendChart({ dailyTrend = [] }) {
  const chartData = (dailyTrend || []).map((item) => ({
    ...item,
    consumption_num: Number(item.consumption_kwh),
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));

  // Find peak day and minimum day
  let peakDay = null;
  let minDay = null;
  if (chartData.length > 0) {
    peakDay = chartData.reduce((prev, curr) => (curr.consumption_num > prev.consumption_num ? curr : prev), chartData[0]);
    minDay = chartData.reduce((prev, curr) => (curr.consumption_num < prev.consumption_num ? curr : prev), chartData[0]);
  }

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Energy Consumption Trend</h3>
          <p className="section-desc">
            Aggregated factory load across 92 operating days with peak interval telemetry and time-series profiling.
          </p>
        </div>
        {peakDay && (
          <div className="section-tag-group">
            <span className="section-tag info">
              Peak: {peakDay.date} ({formatNumber(peakDay.consumption_num, 0)} kWh)
            </span>
            <span className="section-tag process">
              Min: {minDay.date} ({formatNumber(minDay.consumption_num, 0)} kWh)
            </span>
          </div>
        )}
      </div>

      <div className="chart-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Daily Plant Electrical Load (kWh)</h4>
            <span className="chart-card-subtitle">
              Measured by factory submeters • Time series resolution: Daily aggregate
            </span>
          </div>
          <div className="chart-legend-custom">
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-purple)' }}></span>
              Daily Consumption
            </span>
          </div>
        </div>

        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="energyTrendGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--brand-purple)" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="var(--brand-purple)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
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
              <Tooltip content={<CustomDailyTooltip />} />
              <Area
                type="monotone"
                dataKey="consumption_num"
                stroke="var(--brand-purple)"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#energyTrendGrad)"
                name="Consumption (kWh)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
