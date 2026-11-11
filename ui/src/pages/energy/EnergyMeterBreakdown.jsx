import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from 'recharts';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

const METER_COLOR_MAP = {
  'MTR-SMT': 'var(--brand-purple)',
  'MTR-COMPRESSOR': 'var(--chart-cat-4)',
  'MTR-CHILLER': 'var(--brand-cyan)',
  'MTR-FAL': 'var(--brand-blue)',
  'MTR-HVAC': 'var(--brand-orange)',
};

function CustomMeterTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.meter_id} ({data.area})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Total Energy:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.consumption_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Share of Total:</span>
          <span className="tooltip-val">{formatPercent(data.percentage_of_total)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak Hourly Draw:</span>
          <span className="tooltip-val">{formatNumber(data.peak_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Energy Spend:</span>
          <span className="tooltip-val">{formatCurrency(data.cost_inr)}</span>
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

export default function EnergyMeterBreakdown({ byMeter = [] }) {
  // Sort descending by consumption
  const sortedMeters = [...(byMeter || [])].sort(
    (a, b) => Number(b.consumption_kwh) - Number(a.consumption_kwh)
  );

  const chartData = sortedMeters.map((m) => ({
    ...m,
    consumption_num: Number(m.consumption_kwh),
  }));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Consumption by Submeter</h3>
          <p className="section-desc">
            Direct consumption tracking across all 5 monitored factory submeters, ranked by energy intensity.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag process">2 Process Meters</span>
          <span className="section-tag utilities">3 Utility Meters</span>
        </div>
      </div>

      <div className="meters-overview-grid">
        {/* Left: Ranked Bar Chart */}
        <div className="chart-card meter-chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Submeter Consumption Comparison</h4>
              <span className="chart-card-subtitle">Ranked total consumption (kWh) across monitored period</span>
            </div>
          </div>

          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 10, right: 30, left: 20, bottom: 5 }}
              >
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
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)', fontWeight: 600 }}
                  tickLine={false}
                  width={110}
                />
                <Tooltip content={<CustomMeterTooltip />} />
                <Bar dataKey="consumption_num" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.meter_id}
                      fill={METER_COLOR_MAP[entry.meter_id] || 'var(--brand-purple)'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right: Detailed Meter Table */}
        <div className="chart-card meter-table-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Telemetry & Cost Audit by Submeter</h4>
              <span className="chart-card-subtitle">Validated interval readings, demand peaks, and spend</span>
            </div>
          </div>

          <div className="table-responsive">
            <table className="energy-submeter-table">
              <thead>
                <tr>
                  <th>Meter ID</th>
                  <th>Functional Area</th>
                  <th className="text-right">Total Energy</th>
                  <th className="text-right">Share</th>
                  <th className="text-right">Peak Load</th>
                  <th className="text-right">Total Spend</th>
                  <th className="text-center">Avg PF</th>
                </tr>
              </thead>
              <tbody>
                {sortedMeters.map((meter) => {
                  const isProcess = meter.area === 'SMT' || meter.area === 'FAL';
                  return (
                    <tr key={meter.meter_id}>
                      <td>
                        <span className="meter-badge-cell">
                          <span
                            className="meter-dot"
                            style={{ background: METER_COLOR_MAP[meter.meter_id] || 'var(--brand-purple)' }}
                          ></span>
                          <span className="font-semibold">{meter.meter_id}</span>
                        </span>
                      </td>
                      <td>
                        <span className={`area-category-badge ${isProcess ? 'process' : 'utility'}`}>
                          {meter.area} ({isProcess ? 'Process' : 'Utility'})
                        </span>
                      </td>
                      <td className="text-right font-mono font-semibold">
                        {formatNumber(meter.consumption_kwh, 2)} kWh
                      </td>
                      <td className="text-right font-mono">
                        {formatPercent(meter.percentage_of_total)}
                      </td>
                      <td className="text-right font-mono">
                        {formatNumber(meter.peak_kwh, 2)} kWh
                      </td>
                      <td className="text-right font-mono">
                        {formatCurrency(meter.cost_inr)}
                      </td>
                      <td className="text-center font-mono">
                        {meter.avg_power_factor ? Number(meter.avg_power_factor).toFixed(4) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

