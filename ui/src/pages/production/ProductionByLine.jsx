import React, { useState, useMemo } from 'react';
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

/**
 * Section 3: Production line performance
 * Full-width table grouped by Final Assembly (phones) and SMT (boards).
 * Columns: Line | Plant | Actual units | Good units | Yield | Downtime.
 * Supports Table (default) and Chart view toggle.
 * Groups chart comparisons by process stage so boards and phones are clearly distinguished.
 */
export default function ProductionByLine({
  byLine = [],
  dataAvailable = true,
  selectedLine = null,
  onSelectLine = null,
}) {
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'chart'

  // Segregate lines by process stage
  const falLines = useMemo(() => {
    return (byLine || []).filter(
      (l) => l.line_type?.toUpperCase().includes('ASSEMBLY') || l.line_id?.startsWith('FAL')
    );
  }, [byLine]);

  const smtLines = useMemo(() => {
    return (byLine || []).filter(
      (l) => l.line_type?.toUpperCase().includes('SMT') || l.line_id?.startsWith('SMT')
    );
  }, [byLine]);

  const falChartData = useMemo(() => {
    return falLines.map((l) => ({
      ...l,
      actual_num: l.actual_qty,
      good_num: l.good_qty,
    }));
  }, [falLines]);

  const smtChartData = useMemo(() => {
    return smtLines.map((l) => ({
      ...l,
      actual_num: l.actual_qty,
      good_num: l.good_qty,
    }));
  }, [smtLines]);

  const renderTableRow = (line) => {
    const isSelected = selectedLine === line.line_id;
    return (
      <tr
        key={line.line_id}
        className={`line-row ${isSelected ? 'selected' : ''}`}
        onClick={() => onSelectLine && onSelectLine(isSelected ? null : line.line_id)}
        title={
          onSelectLine
            ? isSelected
              ? `Click to clear filter for Line ${line.line_id}`
              : `Click to filter by Line ${line.line_id}`
            : undefined
        }
      >
        <td className="line-id-cell">
          <span className="line-id-text">{line.line_id}</span>
          {isSelected && <span className="selected-filter-badge">Filtered</span>}
        </td>
        <td className="plant-id-cell">
          <span className="plant-id-text">{line.plant_id}</span>
        </td>
        <td className="text-right num-cell">
          {formatNumber(line.actual_qty)}
        </td>
        <td className="text-right num-cell text-success">
          {formatNumber(line.good_qty)}
        </td>
        <td className="text-right num-cell">
          {formatPercent(line.good_rate)}
        </td>
        <td className="text-right num-cell">
          {formatNumber(line.downtime_min)} min
          <span className="sub-hours-text">
            {' '}({line.downtime_min != null ? (Number(line.downtime_min) / 60).toFixed(1) : '0.0'} hrs)
          </span>
        </td>
      </tr>
    );
  };

  return (
    <div className="dashboard-section line-performance-panel">
      {/* 1. Header with View Toggle (Table / Chart) */}
      <div className="section-header">
        <div>
          <h3 className="section-title">Production line performance</h3>
          <p className="section-desc">
            Line throughput, quality yield, and reported downtime grouped by manufacturing process stage.
          </p>
        </div>

        <div className="line-header-actions">
          {selectedLine && (
            <button
              type="button"
              className="line-filter-clear-pill"
              onClick={() => onSelectLine && onSelectLine(null)}
              title="Click to clear line filter"
            >
              Filtered: Line {selectedLine} ✕
            </button>
          )}

          <div className="line-view-toggle" role="group" aria-label="Line performance view toggle">
            <button
              type="button"
              className={`line-view-toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
              onClick={() => setViewMode('table')}
            >
              Table
            </button>
            <button
              type="button"
              className={`line-view-toggle-btn ${viewMode === 'chart' ? 'active' : ''}`}
              onClick={() => setViewMode('chart')}
            >
              Chart
            </button>
          </div>
        </div>
      </div>

      {/* 2. Content: Table View (Default) */}
      {viewMode === 'table' ? (
        <div className="line-table-wrapper">
          <table className="full-width-line-table">
            <thead>
              <tr>
                <th>Line</th>
                <th>Plant</th>
                <th className="text-right">Actual units</th>
                <th className="text-right">Good units</th>
                <th className="text-right">Yield</th>
                <th className="text-right">Downtime</th>
              </tr>
            </thead>
            <tbody>
              {!dataAvailable || (falLines.length === 0 && smtLines.length === 0) ? (
                <tr>
                  <td colSpan="6" className="text-center text-muted" style={{ padding: '2rem' }}>
                    {!dataAvailable ? 'Line performance data unavailable' : 'No line records found'}
                  </td>
                </tr>
              ) : (
                <>
                  {/* Group 1: Final Assembly (phones) */}
                  <tr className="stage-group-header-row">
                    <td colSpan="6">
                      <div className="stage-group-title">
                        <span className="stage-name">Final Assembly (phones)</span>
                        <span className="stage-desc">— Finished Goods Gate</span>
                      </div>
                    </td>
                  </tr>
                  {falLines.length > 0 ? (
                    falLines.map(renderTableRow)
                  ) : (
                    <tr>
                      <td colSpan="6" className="text-center text-muted" style={{ padding: '0.85rem' }}>
                        No Final Assembly records for active filter
                      </td>
                    </tr>
                  )}

                  {/* Group 2: SMT (boards) */}
                  <tr className="stage-group-header-row">
                    <td colSpan="6">
                      <div className="stage-group-title">
                        <span className="stage-name">SMT (boards)</span>
                        <span className="stage-desc">— Surface Mount Technology Circuit Boards</span>
                      </div>
                    </td>
                  </tr>
                  {smtLines.length > 0 ? (
                    smtLines.map(renderTableRow)
                  ) : (
                    <tr>
                      <td colSpan="6" className="text-center text-muted" style={{ padding: '0.85rem' }}>
                        No SMT line records for active filter
                      </td>
                    </tr>
                  )}
                </>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        /* 3. Content: Chart View (Grouped by Stage) */
        <div className="line-charts-grouped-container">
          <div className="line-chart-legend">
            <span className="legend-item">
              <span className="legend-box" style={{ background: 'var(--brand-navy, #1e293b)' }}></span>
              Actual units
            </span>
            <span className="legend-item">
              <span className="legend-box" style={{ background: '#10b981' }}></span>
              Good units
            </span>
          </div>

          {/* Subpanel 1: Final Assembly (Phones) */}
          <div className="stage-chart-subpanel">
            <div className="stage-chart-subhead">
              <span className="stage-chart-title">Final Assembly (phones)</span>
              <span className="stage-chart-subtitle">Finished goods lines (FAL-L1, FAL-L2)</span>
            </div>
            {falChartData.length === 0 ? (
              <div className="chart-empty-msg">No Final Assembly lines available</div>
            ) : (
              <div style={{ width: '100%', height: Math.max(120, falChartData.length * 48) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={falChartData}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, #e2e8f0)" horizontal={false} />
                    <XAxis
                      type="number"
                      stroke="var(--chart-axis, #94a3b8)"
                      tick={{ fontSize: 11, fill: 'var(--chart-axis, #94a3b8)' }}
                      tickLine={false}
                      tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                    />
                    <YAxis
                      type="category"
                      dataKey="line_id"
                      stroke="var(--chart-axis, #94a3b8)"
                      tick={{ fontSize: 12, fill: 'var(--text-primary)', fontWeight: 600 }}
                      tickLine={false}
                      width={80}
                    />
                    <Tooltip content={<CustomLineTooltip />} />
                    <Bar dataKey="actual_num" fill="var(--brand-navy, #1e293b)" radius={[0, 4, 4, 0]} name="Actual Units" />
                    <Bar dataKey="good_num" fill="#10b981" radius={[0, 4, 4, 0]} name="Good Units" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Subpanel 2: SMT (Boards) */}
          <div className="stage-chart-subpanel" style={{ marginTop: '1rem' }}>
            <div className="stage-chart-subhead">
              <span className="stage-chart-title">SMT (boards)</span>
              <span className="stage-chart-subtitle">Surface Mount circuit board lines (SMT-L1, SMT-L2)</span>
            </div>
            {smtChartData.length === 0 ? (
              <div className="chart-empty-msg">No SMT lines available</div>
            ) : (
              <div style={{ width: '100%', height: Math.max(120, smtChartData.length * 48) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={smtChartData}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, #e2e8f0)" horizontal={false} />
                    <XAxis
                      type="number"
                      stroke="var(--chart-axis, #94a3b8)"
                      tick={{ fontSize: 11, fill: 'var(--chart-axis, #94a3b8)' }}
                      tickLine={false}
                      tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                    />
                    <YAxis
                      type="category"
                      dataKey="line_id"
                      stroke="var(--chart-axis, #94a3b8)"
                      tick={{ fontSize: 12, fill: 'var(--text-primary)', fontWeight: 600 }}
                      tickLine={false}
                      width={80}
                    />
                    <Tooltip content={<CustomLineTooltip />} />
                    <Bar dataKey="actual_num" fill="var(--brand-navy, #1e293b)" radius={[0, 4, 4, 0]} name="Actual Units" />
                    <Bar dataKey="good_num" fill="#10b981" radius={[0, 4, 4, 0]} name="Good Units" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
