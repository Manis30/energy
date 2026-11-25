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

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

function CustomDailyTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.date ? formatDate(data.date) : label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">
            {hasNumber(data.consumption_kwh) ? `${formatNumber(data.consumption_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        {hasNumber(data.peak_hourly_kwh) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Peak hour:</span>
            <span className="tooltip-val">{formatNumber(data.peak_hourly_kwh, 2)} kWh</span>
          </div>
        )}
        {hasNumber(data.cost_inr) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Est. cost:</span>
            <span className="tooltip-val">{formatCurrency(data.cost_inr)}</span>
          </div>
        )}
        {hasNumber(data.avg_power_factor) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Average PF:</span>
            <span className="tooltip-val">{Number(data.avg_power_factor).toFixed(4)}</span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

export default function EnergyTrendChart({
  dailyTrend = [],
  dataAvailable = false,
  dateRange,
  selectedPlant,
  selectedShift = 'ALL',
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
    peakDay = validChartData.reduce(
      (prev, curr) => (curr.consumption_num > prev.consumption_num ? curr : prev),
      validChartData[0]
    );
    minDay = validChartData.reduce(
      (prev, curr) => (curr.consumption_num < prev.consumption_num ? curr : prev),
      validChartData[0]
    );
  }

  const plantLabel = selectedPlant
    ? selectedPlant === 'IN-TN-01'
      ? 'Plant IN-TN-01 (Tamil Nadu)'
      : selectedPlant === 'IN-KA-01'
        ? 'Plant IN-KA-01 (Karnataka)'
        : `Plant ${selectedPlant}`
    : 'All Plants (Consolidated)';

  // Determine tick interval based on number of days
  const tickInterval = validChartData.length > 60 ? 7 : validChartData.length > 20 ? 3 : 0;

  return (
    <div className="dashboard-section" style={{ marginBottom: '1.25rem' }}>
      <div className="section-header">
        <div className="section-title-group">
          <h3 className="section-title">Daily Energy Consumption</h3>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">
            {plantLabel}
          </span>
          {selectedShift && selectedShift !== 'ALL' && (
            <span className="section-tag process">
              Shift {selectedShift}
            </span>
          )}
          {peakDay && (
            <span className="section-tag process">
              Peak: {formatDate(peakDay.date)} ({formatNumber(peakDay.consumption_num, 0)} kWh)
            </span>
          )}
          {minDay && (
            <span className="section-tag utility">
              Min: {formatDate(minDay.date)} ({formatNumber(minDay.consumption_num, 0)} kWh)
            </span>
          )}
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-card-header">
          <div className="chart-title-wrap">
            <h4 className="chart-card-title">Daily Electrical Usage (kWh)</h4>
          </div>
          <div className="chart-legend-custom">
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-purple)' }}></span>
              Daily Consumption
            </span>
          </div>
        </div>

        {!dataAvailable || chartData.length === 0 || validChartData.length === 0 ? (
          <div className="chart-empty-state" style={{ minHeight: '220px' }}>
            {!dataAvailable
              ? 'Historical trend data could not be retrieved from the server.'
              : chartData.length === 0
                ? 'No daily trend records returned for the selected filter period.'
                : 'Daily records were returned without valid consumption values.'}
          </div>
        ) : (
          <div
            className="chart-wrapper"
            role="group"
            aria-label="Daily energy consumption area chart in kilowatt-hours by date"
          >
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={validChartData} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="energyTrendGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--brand-purple)" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="var(--brand-purple)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
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
                <Tooltip content={<CustomDailyTooltip />} />
                <Area
                  type="monotone"
                  dataKey="consumption_num"
                  stroke="var(--brand-purple)"
                  strokeWidth={2.2}
                  fillOpacity={1}
                  fill="url(#energyTrendGrad)"
                  name="Consumption (kWh)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
