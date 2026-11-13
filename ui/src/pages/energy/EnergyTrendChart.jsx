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
import { formatCurrency, formatDate, formatNumber } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

function CustomDailyTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.date || label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">
            {hasNumber(data.consumption_kwh) ? `${formatNumber(data.consumption_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak hourly consumption:</span>
          <span className="tooltip-val">
            {hasNumber(data.peak_hourly_kwh) ? `${formatNumber(data.peak_hourly_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Dataset-calculated cost:</span>
          <span className="tooltip-val">{hasNumber(data.cost_inr) ? formatCurrency(data.cost_inr) : 'Unavailable'}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Daily CO₂e:</span>
          <span className="tooltip-val">
            {hasNumber(data.co2e_kg) ? `${formatNumber(data.co2e_kg, 2)} kg CO₂e estimate` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Avg Power Factor:</span>
          <span className="tooltip-val">{hasNumber(data.avg_power_factor) ? Number(data.avg_power_factor).toFixed(4) : 'Unavailable'}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function EnergyTrendChart({
  dailyTrend = [],
  dataAvailable = false,
  dateRange,
}) {
  const chartData = (dailyTrend || []).map((item) => ({
    ...item,
    consumption_num: hasNumber(item.consumption_kwh) ? Number(item.consumption_kwh) : null,
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));
  const validChartData = chartData.filter((item) => hasNumber(item.consumption_num));

  let peakDay = null;
  let minDay = null;
  if (validChartData.length > 0) {
    peakDay = validChartData.reduce((prev, curr) => (
      curr.consumption_num > prev.consumption_num ? curr : prev
    ), validChartData[0]);
    minDay = validChartData.reduce((prev, curr) => (
      curr.consumption_num < prev.consumption_num ? curr : prev
    ), validChartData[0]);
  }
  const rangeDuration = dateRange
    ? Math.floor((Date.parse(`${dateRange.end_date}T00:00:00Z`) - Date.parse(`${dateRange.start_date}T00:00:00Z`)) / 86400000) + 1
    : null;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Energy Consumption Trend</h3>
          <p className="section-desc">
            {dateRange && rangeDuration > 0
              ? `Observed daily totals from ${formatDate(dateRange.start_date)} to ${formatDate(dateRange.end_date)} (${rangeDuration} calendar days; ${chartData.length} returned records, ${validChartData.length} with energy values).`
              : 'No date range is available from the returned daily trend records.'}
          </p>
        </div>
        {peakDay && (
          <div className="section-tag-group">
            <span className="section-tag info">
              Highest returned daily total: {peakDay.date} ({formatNumber(peakDay.consumption_num, 0)} kWh)
            </span>
            <span className="section-tag process">
              Lowest returned daily total: {minDay.date} ({formatNumber(minDay.consumption_num, 0)} kWh)
            </span>
          </div>
        )}
      </div>

      <div className="chart-card">
        <div className="chart-card-header">
          <div>
            <h4 className="chart-card-title">Daily Plant Energy Consumption (kWh)</h4>
            <span className="chart-card-subtitle">
              Daily aggregates from returned meter data • Historical reference, not an expected-energy baseline
            </span>
          </div>
          <div className="chart-legend-custom">
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-purple)' }}></span>
              Daily Consumption
            </span>
          </div>
        </div>

        {!dataAvailable || chartData.length === 0 || validChartData.length === 0 ? (
          <div className="chart-empty-state">
            {!dataAvailable
              ? 'Historical trend data could not be retrieved; no period comparison is available.'
              : chartData.length === 0
                ? 'No daily trend records were returned for this period.'
                : 'Daily records were returned without usable consumption values.'}
          </div>
        ) : (
        <div
          className="chart-wrapper"
          role="group"
          aria-label="Daily energy consumption area chart in kilowatt-hours by date"
        >
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={validChartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
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
        )}
        <div className="chart-card-footer">
          <span className="chart-legend-hint">
            Changes in total kWh alone do not establish improved or reduced efficiency or achieved savings. Production volume and operating conditions can affect consumption; the trend is not normalized for them. The API does not expose expected interval counts or a completeness indicator.
          </span>
        </div>
      </div>
    </div>
  );
}

