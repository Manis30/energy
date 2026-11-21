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

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

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
    const isCompressor = data.meter_id === 'MTR-COMPRESSOR';
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">
          {data.meter_id} ({data.area})
          {isCompressor && (
            <div style={{ fontSize: '0.72rem', color: 'var(--brand-purple)', fontWeight: 500, marginTop: '2px' }}>
              Compressor electricity consumption (kWh) — electrical input distinct from air delivery
            </div>
          )}
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">
            {hasNumber(data.consumption_kwh) ? `${formatNumber(data.consumption_kwh, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Energy Share:</span>
          <span className="tooltip-val">
            {hasNumber(data.percentage_of_total) ? formatPercent(data.percentage_of_total) : 'Unavailable'}
          </span>
        </div>
        {hasNumber(data.peak_kwh) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Peak hour load:</span>
            <span className="tooltip-val">{formatNumber(data.peak_kwh, 2)} kWh</span>
          </div>
        )}
        {hasNumber(data.cost_inr) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Dataset cost:</span>
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

  const topMeter = sortedMeters.length > 0 ? sortedMeters[0] : null;

  return (
    <div className="dashboard-section" style={{ marginBottom: '1.25rem' }}>
      <div className="section-header">
        <div className="section-title-group">
          <h3 className="section-title">Energy Consumption by Meter</h3>
        </div>
        <div className="section-tag-group">
          {topMeter && hasNumber(topMeter.consumption_kwh) && (
            <span className="section-tag process">
              Highest: {topMeter.meter_id} ({formatNumber(topMeter.consumption_kwh, 0)} kWh)
            </span>
          )}
          <span className="section-tag info">
            {dataAvailable ? `${byMeter.length} monitored meters` : 'Meter data unavailable'}
          </span>
        </div>
      </div>

      <div className="meters-overview-grid">
        {/* Left: Ranked Horizontal Bar Chart */}
        <div className="chart-card meter-chart-card">
          <div className="chart-card-header">
            <div className="chart-title-wrap">
              <h4 className="chart-card-title">Submeter Consumption Ranking</h4>
            </div>
            <div className="chart-legend-custom">
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--brand-purple)' }}></span>
                Interval kWh
              </span>
            </div>
          </div>

          <div
            className="chart-wrapper meter-chart-wrapper"
            role="group"
            aria-label="Submeter energy consumption horizontal bar chart in kilowatt-hours by meter"
          >
            {!dataAvailable || chartData.length === 0 || validChartData.length === 0 ? (
              <div className="chart-empty-state" style={{ minHeight: '230px' }}>
                {!dataAvailable
                  ? 'Meter telemetry is unavailable from the server.'
                  : chartData.length === 0
                    ? 'No meter records returned for the selected period.'
                    : 'Meter records were returned without usable energy values.'}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={validChartData}
                  layout="vertical"
                  margin={{ top: 6, right: 20, left: 0, bottom: 4 }}
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
                    width={115}
                    interval={0}
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
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Right: Detailed Meter Table */}
        <div className="chart-card meter-table-card">
          <div className="chart-card-header">
            <div className="chart-title-wrap">
              <h4 className="chart-card-title">Submeter Telemetry Breakdown</h4>
            </div>
          </div>

          <div
            className="table-responsive meter-table-scroll-container"
            tabIndex={0}
            role="region"
            aria-label="Detailed submeter telemetry table"
          >
            <table className="energy-submeter-table">
              <thead>
                <tr>
                  <th>Meter</th>
                  <th>Area</th>
                  <th className="text-right">Interval Energy</th>
                  <th className="text-right">Share</th>
                  <th className="text-right">Peak Load</th>
                  <th className="text-right">Est. Cost</th>
                  <th className="text-center">Avg PF</th>
                </tr>
              </thead>
              <tbody>
                {!dataAvailable || sortedMeters.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center text-muted" style={{ padding: '1.5rem' }}>
                      {!dataAvailable ? 'Meter data unavailable' : 'No meter records returned'}
                    </td>
                  </tr>
                ) : (
                  sortedMeters.map((meter) => {
                    const isProcess = meter.area === 'SMT' || meter.area === 'FAL';
                    const isUtility = ['COMPRESSOR', 'CHILLER', 'HVAC'].includes(meter.area);
                    const meterType = isProcess ? 'Process' : isUtility ? 'Utility' : 'Other';
                    return (
                      <tr key={meter.meter_id}>
                        <td>
                          <span className="meter-badge-cell">
                            <span
                              className="meter-dot"
                              style={{ background: METER_COLOR_MAP[meter.meter_id] || 'var(--brand-purple)' }}
                            ></span>
                            <div>
                              <span className="font-semibold">{meter.meter_id}</span>
                              {meter.meter_id === 'MTR-COMPRESSOR' && (
                                <div style={{ fontSize: '0.67rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                                  Compressor electricity consumption (kWh)
                                </div>
                              )}
                            </div>
                          </span>
                        </td>
                        <td>
                          <span className={`area-category-badge ${isProcess ? 'process' : isUtility ? 'utility' : ''}`}>
                            {meter.area || '—'} ({meterType})
                          </span>
                        </td>
                        <td className="text-right font-mono font-semibold">
                          {hasNumber(meter.consumption_kwh) ? `${formatNumber(meter.consumption_kwh, 2)} kWh` : '—'}
                        </td>
                        <td className="text-right font-mono">
                          {hasNumber(meter.percentage_of_total) ? formatPercent(meter.percentage_of_total) : '—'}
                        </td>
                        <td className="text-right font-mono">
                          {hasNumber(meter.peak_kwh) ? `${formatNumber(meter.peak_kwh, 2)} kWh` : '—'}
                        </td>
                        <td className="text-right font-mono">
                          {hasNumber(meter.cost_inr) ? formatCurrency(meter.cost_inr) : '—'}
                        </td>
                        <td className="text-center font-mono">
                          {hasNumber(meter.avg_power_factor) ? Number(meter.avg_power_factor).toFixed(4) : '—'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
