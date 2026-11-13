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

function CustomLineTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.line_id} ({data.line_type} - {data.plant_id})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Area / Stage:</span>
          <span className="tooltip-val">{data.area}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val text-success">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rejected Units:</span>
          <span className="tooltip-val text-danger">{formatNumber(data.reject_qty)} ({formatPercent(data.reject_rate)})</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rework Units:</span>
          <span className="tooltip-val">{formatNumber(data.rework_qty)}</span>
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

export default function ProductionByLine({ byLine = [], dataAvailable = true }) {
  const chartData = (byLine || []).map((l) => ({
    ...l,
    actual_num: l.actual_qty,
    good_num: l.good_qty,
    reject_num: l.reject_qty,
  }));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Output by Manufacturing Line</h3>
          <p className="section-desc">
            Returned line-level actual and good output, yield, and reported downtime. Compare like line types; units may represent different production stages.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">
            {dataAvailable ? `${byLine.length} returned line record(s)` : 'Line data unavailable'}
          </span>
        </div>
      </div>

      <div className="lines-overview-grid">
        {/* Left: Horizontal Bar Chart */}
        <div className="chart-card line-chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Line Output Comparison</h4>
              <span className="chart-card-subtitle">Actual vs Good units per production line</span>
            </div>
            <div className="chart-legend-custom">
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--brand-navy)' }}></span>
                Actual
              </span>
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--chart-cat-4)' }}></span>
                Good
              </span>
            </div>
          </div>

          <div
            className="chart-wrapper"
            role="group"
            aria-label="Production bar chart comparing actual and good output in returned line units; the table below contains per-line values"
          >
            {!dataAvailable || chartData.length === 0 ? (
              <div className="chart-empty-state">
                {!dataAvailable ? 'Production-by-line data is unavailable.' : 'No production-by-line records were returned.'}
              </div>
            ) : <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 10, right: 30, left: 15, bottom: 5 }}
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
                  dataKey="line_id"
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)', fontWeight: 600 }}
                  tickLine={false}
                  width={90}
                />
                <Tooltip content={<CustomLineTooltip />} />
                <Bar dataKey="actual_num" fill="var(--brand-navy)" radius={[0, 4, 4, 0]} name="Actual Units" />
                <Bar dataKey="good_num" fill="var(--chart-cat-4)" radius={[0, 4, 4, 0]} name="Good Units" />
              </BarChart>
            </ResponsiveContainer>}
          </div>
        </div>

        {/* Right: Detailed Line Table */}
        <div className="chart-card line-table-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Production Line Details</h4>
              <span className="chart-card-subtitle">Line type, location, yield rate, and stoppage metrics</span>
            </div>
          </div>

          <div className="table-responsive">
            <table className="production-line-table">
              <thead>
                <tr>
                  <th>Line ID</th>
                  <th>Plant</th>
                  <th>Process Stage</th>
                  <th className="text-right">Actual Units</th>
                  <th className="text-right">Good Units</th>
                  <th className="text-right">Quality Yield</th>
                  <th className="text-right">Downtime</th>
                </tr>
              </thead>
              <tbody>
                {!dataAvailable || byLine.length === 0 ? (
                  <tr>
                    <td colSpan="7">
                      {!dataAvailable ? 'Production-by-line data unavailable' : 'No line records returned'}
                    </td>
                  </tr>
                ) : (byLine || []).map((line) => {
                  const isSMT = line.line_type?.toUpperCase().includes('SMT');
                  return (
                    <tr key={line.line_id}>
                      <td className="font-semibold">{line.line_id}</td>
                      <td>
                        <span className="badge-plant">{line.plant_id}</span>
                      </td>
                      <td>
                        <span className={`area-category-badge ${isSMT ? 'process' : 'info'}`}>
                          {line.line_type}
                        </span>
                      </td>
                      <td className="text-right font-mono font-semibold">
                        {formatNumber(line.actual_qty)}
                      </td>
                      <td className="text-right font-mono text-success">
                        {formatNumber(line.good_qty)}
                      </td>
                      <td className="text-right font-mono">
                        {formatPercent(line.good_rate)}
                      </td>
                      <td className="text-right font-mono">
                        {formatNumber(line.downtime_min)} min
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

