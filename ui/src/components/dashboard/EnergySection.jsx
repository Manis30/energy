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
          <span className="tooltip-val">{formatNumber(data.consumption_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak Hour:</span>
          <span className="tooltip-val">{formatNumber(data.peak_hourly_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Spend:</span>
          <span className="tooltip-val">₹{formatNumber(data.cost_inr, 2)}</span>
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
          <span className="tooltip-val">{data.avg_power_factor ? Number(data.avg_power_factor).toFixed(4) : '—'}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function EnergySection({ dailyTrend, byMeter, byArea }) {
  // Format daily trend data for recharts
  const trendData = (dailyTrend || []).map((item) => ({
    ...item,
    consumption_kwh_num: Number(item.consumption_kwh),
    displayDate: item.date ? item.date.slice(5) : '', // '08-01'
  }));

  // Format meters data
  const meterData = (byMeter || []).map((m) => ({
    ...m,
    consumption_kwh_num: Number(m.consumption_kwh),
  }));

  // Format area data
  const areaData = (byArea || []).map((a) => {
    let cleanArea = a.area;
    if (a.area === 'SMT') cleanArea = 'SMT Lines (Process)';
    else if (a.area === 'FINAL_ASSEMBLY') cleanArea = 'Final Assembly (Process)';
    else if (a.area === 'UTILITIES') cleanArea = 'Facility Utilities (Plant-wide)';

    return {
      name: cleanArea,
      rawArea: a.area,
      value: Number(a.consumption_kwh),
      share: Number(a.percentage_of_total),
    };
  });

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Consumption Analytics</h3>
          <p className="section-desc">
            Continuous interval energy monitoring across manufacturing processes and non-process facility utility systems.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag process">Process Lines (44.4%)</span>
          <span className="section-tag utilities">Facility Utilities (55.6%)</span>
        </div>
      </div>

      <div className="energy-analytics-grid">
        {/* Daily Consumption Trend (Left) */}
        <div className="chart-card trend-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Daily Energy Consumption Trend</h4>
              <span className="chart-card-subtitle">Aggregate plant load across 92 operating days (kWh)</span>
            </div>
          </div>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={280}>
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
            </ResponsiveContainer>
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
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={280}>
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
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Area Breakdown Cards (Bottom row) */}
      <div className="area-summary-container">
        <div className="area-summary-header">
          <h4 className="chart-card-title">Energy Distribution by Factory Area</h4>
          <span className="chart-card-subtitle">Clear boundary segregation between machine lines and facility utilities</span>
        </div>
        <div className="area-cards-row">
          {areaData.map((area) => (
            <div key={area.name} className="area-card">
              <div className="area-card-top">
                <span className="area-name">{area.name}</span>
                <span className={`area-badge ${area.rawArea === 'UTILITIES' ? 'utility' : 'process'}`}>
                  {area.rawArea === 'UTILITIES' ? 'Facility Support' : 'Core Manufacturing'}
                </span>
              </div>
              <div className="area-value-row">
                <span className="area-kwh">{formatNumber(area.value, 2)} kWh</span>
                <span className="area-share">{formatPercent(area.share)}</span>
              </div>
              <div className="area-progress-track">
                <div
                  className="area-progress-bar"
                  style={{
                    width: `${Math.min(100, Math.max(5, area.share))}%`,
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

