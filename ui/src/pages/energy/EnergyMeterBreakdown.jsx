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

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

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
          <span className="tooltip-label">Interval energy:</span>
          <span className="tooltip-val font-bold">
            {hasNumber(data.consumption_kwh) ? `${formatNumber(data.consumption_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Share of returned energy:</span>
          <span className="tooltip-val">
            {hasNumber(data.percentage_of_total) ? formatPercent(data.percentage_of_total) : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak hourly consumption:</span>
          <span className="tooltip-val">
            {hasNumber(data.peak_kwh) ? `${formatNumber(data.peak_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Dataset-calculated cost:</span>
          <span className="tooltip-val">{hasNumber(data.cost_inr) ? formatCurrency(data.cost_inr) : 'Unavailable'}</span>
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

export default function EnergyMeterBreakdown({ byMeter = [], dataAvailable = true }) {
  const sortedMeters = [...(byMeter || [])].sort(
    (a, b) => (hasNumber(b.consumption_kwh) ? Number(b.consumption_kwh) : -Infinity)
      - (hasNumber(a.consumption_kwh) ? Number(a.consumption_kwh) : -Infinity)
  );

  const chartData = sortedMeters.map((m) => ({
    ...m,
    consumption_num: hasNumber(m.consumption_kwh) ? Number(m.consumption_kwh) : null,
  }));
  const validChartData = chartData.filter((item) => hasNumber(item.consumption_num));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Consumption by Submeter</h3>
          <p className="section-desc">
            Returned hourly-interval energy totals by submeter. These kWh totals are not normalized for production volume or operating conditions, so they are not like-for-like efficiency comparisons.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">
            {dataAvailable ? `${byMeter.length} returned meter record(s)` : 'Meter data unavailable'}
          </span>
        </div>
      </div>

      <div className="meters-overview-grid">
        {/* Left: Ranked Bar Chart */}
        <div className="chart-card meter-chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Submeter Consumption by Meter</h4>
              <span className="chart-card-subtitle">Total interval consumption (kWh) by meter for the returned period</span>
            </div>
          </div>

          <div
            className="chart-wrapper"
            role="group"
            aria-label="Submeter energy consumption bar chart in kilowatt-hours by meter; detailed values are also in the adjacent table"
          >
            {!dataAvailable || chartData.length === 0 || validChartData.length === 0 ? (
              <div className="chart-empty-state">
                {!dataAvailable
                  ? 'Meter data is unavailable.'
                  : chartData.length === 0
                    ? 'No meter records were returned.'
                    : 'Meter records were returned without usable energy values.'}
              </div>
            ) : <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={validChartData}
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
                  {validChartData.map((entry) => (
                    <Cell
                      key={entry.meter_id}
                      fill={METER_COLOR_MAP[entry.meter_id] || 'var(--brand-purple)'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>}
          </div>
        </div>

        {/* Right: Detailed Meter Table */}
        <div className="chart-card meter-table-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Returned Telemetry by Submeter</h4>
              <span className="chart-card-subtitle">Interval energy, peak hourly consumption, and dataset-calculated cost</span>
            </div>
          </div>

          <div className="table-responsive">
            <table className="energy-submeter-table">
              <thead>
                <tr>
                  <th>Meter ID</th>
                  <th>Functional Area</th>
                  <th className="text-right">Interval Energy</th>
                  <th className="text-right">Returned Energy Share</th>
                  <th className="text-right">Peak Hourly Consumption</th>
                  <th className="text-right">Dataset Cost</th>
                  <th className="text-center">Avg PF</th>
                </tr>
              </thead>
              <tbody>
                {!dataAvailable || sortedMeters.length === 0 ? (
                  <tr>
                    <td colSpan="7">
                      {!dataAvailable ? 'Meter data unavailable' : 'No meter records were returned'}
                    </td>
                  </tr>
                ) : sortedMeters.map((meter) => {
                  const isProcess = meter.area === 'SMT' || meter.area === 'FAL';
                  const isUtility = ['COMPRESSOR', 'CHILLER', 'HVAC'].includes(meter.area);
                  const meterType = isProcess ? 'Process' : isUtility ? 'Utility' : 'Unclassified';
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
                        <span className={`area-category-badge ${isProcess ? 'process' : isUtility ? 'utility' : ''}`}>
                          {meter.area || 'Area unavailable'} ({meterType})
                        </span>
                      </td>
                      <td className="text-right font-mono font-semibold">
                        {hasNumber(meter.consumption_kwh) ? `${formatNumber(meter.consumption_kwh, 2)} kWh` : 'Unavailable'}
                      </td>
                      <td className="text-right font-mono">
                        {hasNumber(meter.percentage_of_total) ? formatPercent(meter.percentage_of_total) : 'Unavailable'}
                      </td>
                      <td className="text-right font-mono">
                        {hasNumber(meter.peak_kwh) ? `${formatNumber(meter.peak_kwh, 2)} kWh` : 'Unavailable'}
                      </td>
                      <td className="text-right font-mono">
                        {hasNumber(meter.cost_inr) ? formatCurrency(meter.cost_inr) : 'Unavailable'}
                      </td>
                      <td className="text-center font-mono">
                        {hasNumber(meter.avg_power_factor) ? Number(meter.avg_power_factor).toFixed(4) : 'Unavailable'}
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

