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
    const isSMT = data.line_type?.toUpperCase().includes('SMT');
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.line_id} ({data.plant_id})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Process Stage:</span>
          <span className="tooltip-val">{data.line_type} ({isSMT ? 'Boards' : 'Phones'})</span>
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

export default function ProductionByLine({
  byLine = [],
  dataAvailable = true,
  selectedLine = null,
  onSelectLine = null,
}) {
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
          <h3 className="section-title">Production Line Performance</h3>
          <p className="section-desc">
            Line throughput, quality yield, and reported downtime across manufacturing stages.
          </p>
        </div>
        <div className="section-tag-group">
          {selectedLine && (
            <span className="section-tag process">
              Filtered: Line {selectedLine}
            </span>
          )}
          <span className="section-tag info">
            {dataAvailable ? `${byLine.length} monitored lines` : 'Line data unavailable'}
          </span>
          <span className="section-tag boundary-warning">
            SMT &amp; FAL Represent Distinct Stages
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
                <span className="legend-box" style={{ background: 'var(--status-success, #10b981)' }}></span>
                Good
              </span>
            </div>
          </div>

          <div
            className="chart-wrapper"
            role="group"
            aria-label="Production bar chart comparing actual and good output per line"
          >
            {!dataAvailable || chartData.length === 0 ? (
              <div className="chart-empty-state">
                {!dataAvailable
                  ? 'Production-by-line data is unavailable from the server.'
                  : 'No line records returned for the selected filter period.'}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
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
                  <Bar dataKey="good_num" fill="var(--status-success, #10b981)" radius={[0, 4, 4, 0]} name="Good Units" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Right: Detailed Line Table */}
        <div className="chart-card line-table-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Production Line Details</h4>
              <span className="chart-card-subtitle">Click a line to isolate in filters</span>
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
                  <th className="text-right">Yield</th>
                  <th className="text-right">Downtime</th>
                </tr>
              </thead>
              <tbody>
                {!dataAvailable || byLine.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center text-muted" style={{ padding: '2rem' }}>
                      {!dataAvailable ? 'Line data unavailable' : 'No line records returned'}
                    </td>
                  </tr>
                ) : (
                  (byLine || []).map((line) => {
                    const isSMT = line.line_type?.toUpperCase().includes('SMT');
                    const isSelected = selectedLine === line.line_id;
                    return (
                      <tr
                        key={line.line_id}
                        onClick={() => onSelectLine && onSelectLine(isSelected ? null : line.line_id)}
                        style={{
                          cursor: onSelectLine ? 'pointer' : 'default',
                          backgroundColor: isSelected ? 'var(--bg-active, rgba(111, 61, 186, 0.12))' : undefined,
                        }}
                        title={onSelectLine ? `Click to ${isSelected ? 'clear filter' : `filter by Line ${line.line_id}`}` : undefined}
                      >
                        <td>
                          <span className="font-semibold" style={{ color: isSelected ? 'var(--brand-purple)' : undefined }}>
                            {line.line_id}
                          </span>
                        </td>
                        <td>
                          <span className="badge-plant">{line.plant_id}</span>
                        </td>
                        <td>
                          <span className={`area-category-badge ${isSMT ? 'process' : 'utility'}`}>
                            {line.line_type} ({isSMT ? 'Boards' : 'Phones'})
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
                  })
                )}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: '0.85rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            * Note: SMT lines produce circuit boards, while Final Assembly (FAL) lines produce finished phones. These units represent distinct process stages and are not interchangeable.
          </div>
        </div>
      </div>
    </div>
  );
}
