import React from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from 'recharts';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

const METER_COLORS = {
  'MTR-SMT': 'var(--brand-purple)',
  'MTR-FAL': 'var(--brand-blue)',
  'MTR-HVAC': 'var(--brand-orange)',
  'MTR-COMPRESSOR': 'var(--chart-cat-4)',
  'MTR-CHILLER': 'var(--brand-cyan)',
};

const AREA_COLORS = {
  'SMT': 'var(--brand-purple)',
  'FINAL_ASSEMBLY': 'var(--brand-blue)',
  'UTILITIES': 'var(--brand-orange)',
};

function CustomAreaTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val">
            {hasNumber(data.consumption_kwh) ? `${formatNumber(data.consumption_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak Hour:</span>
          <span className="tooltip-val">
            {hasNumber(data.peak_hourly_kwh) ? `${formatNumber(data.peak_hourly_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Dataset-calculated cost:</span>
          <span className="tooltip-val">
            {hasNumber(data.cost_inr) ? `₹${formatNumber(data.cost_inr, 2)}` : 'Unavailable'}
          </span>
        </div>
      </div>
    );
  }
  return null;
}

function CustomBarTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.meter_id} ({data.area})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Total Energy:</span>
          <span className="tooltip-val">{formatNumber(data.consumption_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Factory Share:</span>
          <span className="tooltip-val">{formatPercent(data.percentage_of_total)}</span>
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

export default function EnergySection({
  dailyTrend = [],
  byMeter = [],
  byArea = [],
  trendAvailable = true,
  meterAvailable = true,
  areaAvailable = true,
}) {
  // Format daily trend data for recharts
  const trendData = (dailyTrend || []).map((item) => ({
    ...item,
    consumption_kwh_num: hasNumber(item.consumption_kwh) ? Number(item.consumption_kwh) : null,
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));
  const trendDates = trendData
    .map((item) => item.date)
    .filter((date) => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();
  const hasTrendValues = trendData.some((item) => hasNumber(item.consumption_kwh_num));

  // Format meters data
  const meterData = (byMeter || []).map((m) => ({
    ...m,
    consumption_kwh_num: hasNumber(m.consumption_kwh) ? Number(m.consumption_kwh) : null,
  }));
  const hasMeterValues = meterData.some((item) => hasNumber(item.consumption_kwh_num));

  // Format area data
  const areaData = (byArea || []).map((a) => {
    let cleanArea = a.area;
    if (a.area === 'SMT') cleanArea = 'SMT Lines (Process)';
    else if (a.area === 'FINAL_ASSEMBLY') cleanArea = 'Final Assembly (Process)';
    else if (a.area === 'UTILITIES') cleanArea = 'Facility Utilities (Plant-wide)';

    return {
      name: cleanArea,
      rawArea: a.area,
      value: hasNumber(a.consumption_kwh) ? Number(a.consumption_kwh) : null,
      share: hasNumber(a.percentage_of_total) ? Number(a.percentage_of_total) : null,
    };
  });

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Consumption Analytics</h3>
          <p className="section-desc">
            Returned daily and meter-level kWh context. Totals are not normalized by production and do not establish savings or efficiency changes.
          </p>
        </div>
      </div>

      <div className="energy-analytics-grid">
        {/* Daily Consumption Trend (Left) */}
        <div className="chart-card trend-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Daily Energy Consumption Trend</h4>
              <span className="chart-card-subtitle">
                {!trendAvailable
                  ? 'Trend request unavailable'
                  : `${trendData.length} returned daily record(s)${trendDates.length > 0 ? ` · ${trendDates[0]} to ${trendDates[trendDates.length - 1]}` : ''} · kWh`}
              </span>
            </div>
          </div>
          <div
            className="chart-wrapper"
            role="group"
            aria-label="Daily energy consumption area chart, in kilowatt-hours, by returned date"
          >
            {!trendAvailable || trendData.length === 0 || !hasTrendValues ? (
              <div className="chart-empty-state">
                {!trendAvailable
                  ? 'Energy trend data is unavailable.'
                  : trendData.length === 0
                    ? 'No energy trend records were returned.'
                    : 'Trend records were returned without usable consumption values.'}
              </div>
            ) : <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={trendData} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="energyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--brand-purple)" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="var(--brand-purple)" stopOpacity={0.0} />
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
                <Tooltip content={<CustomAreaTooltip />} />
                <Area
                  type="monotone"
                  dataKey="consumption_kwh_num"
                  stroke="var(--brand-purple)"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#energyGrad)"
                  name="Energy (kWh)"
                />
              </AreaChart>
            </ResponsiveContainer>}
          </div>
        </div>

        {/* Meters Breakdown (Right Top) */}
        <div className="chart-card meter-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Consumption by Meter</h4>
              <span className="chart-card-subtitle">Ranked submeter draw (kWh)</span>
            </div>
          </div>
          <div
            className="chart-wrapper"
            role="group"
            aria-label="Submeter energy consumption bar chart, in kilowatt-hours, by meter"
          >
            {!meterAvailable || meterData.length === 0 || !hasMeterValues ? (
              <div className="chart-empty-state">
                {!meterAvailable
                  ? 'Meter breakdown is unavailable.'
                  : meterData.length === 0
                    ? 'No meter records were returned.'
                    : 'Meter records were returned without usable consumption values.'}
              </div>
            ) : <ResponsiveContainer width="100%" height={280}>
              <BarChart data={meterData} layout="vertical" margin={{ top: 5, right: 25, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
                <XAxis
                  type="number"
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                  tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                />
                <YAxis
                  type="category"
                  dataKey="meter_id"
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                />
                <Tooltip content={<CustomBarTooltip />} />
                <Bar dataKey="consumption_kwh_num" radius={[0, 4, 4, 0]}>
                  {meterData.map((entry) => (
                    <Cell key={entry.meter_id} fill={METER_COLORS[entry.meter_id] || 'var(--brand-blue)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>}
          </div>
        </div>
      </div>

      {/* Area Breakdown Cards (Bottom row) */}
      <div className="area-summary-container">
        <div className="area-summary-header">
          <h4 className="chart-card-title">Energy Distribution by Factory Area</h4>
          <span className="chart-card-subtitle">Returned area aggregates; facility utility energy remains plant-wide and is not allocated to production lines</span>
        </div>
        <div className="area-cards-row">
          {!areaAvailable || areaData.length === 0 ? (
            <div className="chart-empty-state">
              {!areaAvailable ? 'Energy-by-area data is unavailable.' : 'No area records were returned.'}
            </div>
          ) : areaData.map((area) => (
            <div key={area.name} className="area-card">
              <div className="area-card-top">
                <span className="area-name">{area.name}</span>
                <span className={`area-badge ${area.rawArea === 'UTILITIES' ? 'utility' : 'process'}`}>
                  {area.rawArea === 'UTILITIES' ? 'Facility Support' : 'Core Manufacturing'}
                </span>
              </div>
              <div className="area-value-row">
                <span className="area-kwh">{hasNumber(area.value) ? `${formatNumber(area.value, 2)} kWh` : 'Unavailable'}</span>
                <span className="area-share">{hasNumber(area.share) ? formatPercent(area.share) : 'Unavailable'}</span>
              </div>
              <div className="area-progress-track">
                <div
                  className="area-progress-bar"
                  style={{
                    width: `${hasNumber(area.share) ? Math.min(100, Math.max(0, area.share)) : 0}%`,
                    backgroundColor: AREA_COLORS[area.rawArea] || 'var(--brand-blue)',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

