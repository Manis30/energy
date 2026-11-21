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
import { formatNumber, formatPercent } from '../../utils/formatters';

const DOWNTIME_COLOR_MAP = {
  EQUIPMENT_FAULT: 'var(--status-danger, #ef4444)',
  CHANGEOVER: 'var(--brand-purple)',
  FEEDER_JAM: 'var(--brand-orange)',
  NO_MATERIAL: 'var(--chart-cat-1, #4d8eeb)',
  MICRO_STOP: 'var(--chart-cat-4, #0e9c86)',
  NONE: 'var(--text-muted, #718096)',
};

function CustomDowntimeTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.cleanReason}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Total Duration:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.total_downtime_min)} min</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Duration (hours):</span>
          <span className="tooltip-val font-mono">
            {data.total_downtime_min !== null && Number.isFinite(Number(data.total_downtime_min))
              ? `${(Number(data.total_downtime_min) / 60).toFixed(1)} hrs`
              : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Event Count:</span>
          <span className="tooltip-val">{formatNumber(data.event_count)} occurrences</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Zero-Output Events:</span>
          <span className="tooltip-val text-danger">{formatNumber(data.zero_output_events)}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function ProductionDowntimeSection({
  downtimeData = [],
  totalDowntimeMin = null,
  dataAvailable = true,
}) {
  const hasTotalDowntime =
    totalDowntimeMin !== null && totalDowntimeMin !== undefined && Number.isFinite(Number(totalDowntimeMin));
  const totalDowntime = hasTotalDowntime ? Number(totalDowntimeMin) : null;

  const chartData = (downtimeData || []).map((d) => {
    let clean = d.downtime_reason?.replace(/_/g, ' ');
    if (d.downtime_reason === 'NONE') clean = 'Routine / Other';
    const hasDuration =
      d.total_downtime_min !== null && d.total_downtime_min !== undefined && Number.isFinite(Number(d.total_downtime_min));
    return {
      ...d,
      cleanReason: clean,
      duration_min: d.total_downtime_min,
      share_pct: hasDuration && totalDowntime !== null && totalDowntime > 0
        ? (Number(d.total_downtime_min) / totalDowntime) * 100
        : null,
    };
  });

  const totalDowntimeHours = totalDowntime !== null ? (totalDowntime / 60).toFixed(1) : null;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Downtime &amp; Stoppage Analysis</h3>
          <p className="section-desc">
            Reported operational downtime by logged stoppage reason category and zero-output event count.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag scrap">
            {totalDowntime !== null
              ? `Total Downtime: ${formatNumber(totalDowntime)} min (${totalDowntimeHours} hrs)`
              : 'Downtime unavailable'}
          </span>
        </div>
      </div>

      <div className="downtime-overview-grid">
        {/* Left: Ranked Horizontal Bar Chart */}
        <div className="chart-card downtime-chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Downtime Duration by Logged Reason</h4>
              <span className="chart-card-subtitle">Reported stoppage minutes across lines</span>
            </div>
          </div>

          <div
            className="chart-wrapper"
            role="group"
            aria-label="Downtime bar chart in minutes by reported reason"
          >
            {!dataAvailable || chartData.length === 0 ? (
              <div className="chart-empty-state">
                {!dataAvailable
                  ? 'Downtime telemetry is unavailable from the server.'
                  : 'No downtime records returned for the selected filter period.'}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={chartData}
                  layout="vertical"
                  margin={{ top: 10, right: 30, left: 30, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
                  <XAxis
                    type="number"
                    stroke="var(--chart-axis)"
                    tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                    tickLine={false}
                    tickFormatter={(val) => `${(val / 60).toFixed(0)}h`}
                  />
                  <YAxis
                    type="category"
                    dataKey="cleanReason"
                    stroke="var(--chart-axis)"
                    tick={{ fontSize: 11, fill: 'var(--chart-axis)', fontWeight: 600 }}
                    tickLine={false}
                    width={140}
                  />
                  <Tooltip content={<CustomDowntimeTooltip />} />
                  <Bar dataKey="duration_min" radius={[0, 4, 4, 0]}>
                    {chartData.map((entry) => (
                      <Cell
                        key={entry.downtime_reason}
                        fill={DOWNTIME_COLOR_MAP[entry.downtime_reason] || 'var(--brand-orange)'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Right: Detailed Stoppage Table */}
        <div className="chart-card downtime-table-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Stoppage Reasons &amp; Zero-Output Events</h4>
              <span className="chart-card-subtitle">Reported occurrences and stoppage duration</span>
            </div>
          </div>

          <div className="table-responsive">
            <table className="production-line-table">
              <thead>
                <tr>
                  <th>Logged Reason</th>
                  <th className="text-right">Duration</th>
                  <th className="text-right">Share</th>
                  <th className="text-right">Occurrences</th>
                  <th className="text-right">Zero-Output</th>
                </tr>
              </thead>
              <tbody>
                {!dataAvailable || chartData.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="text-center text-muted" style={{ padding: '2rem' }}>
                      {!dataAvailable ? 'Downtime data unavailable' : 'No downtime records returned'}
                    </td>
                  </tr>
                ) : (
                  chartData.map((item) => (
                    <tr key={item.downtime_reason}>
                      <td>
                        <span className="downtime-reason-cell">
                          <span
                            className="downtime-dot"
                            style={{ background: DOWNTIME_COLOR_MAP[item.downtime_reason] || 'var(--brand-orange)' }}
                          ></span>
                          <span className="font-semibold">{item.cleanReason}</span>
                        </span>
                      </td>
                      <td className="text-right font-mono font-semibold">
                        {formatNumber(item.total_downtime_min)} min
                      </td>
                      <td className="text-right font-mono">
                        {formatPercent(item.share_pct)}
                      </td>
                      <td className="text-right font-mono">
                        {formatNumber(item.event_count)}
                      </td>
                      <td className="text-right font-mono text-danger font-semibold">
                        {formatNumber(item.zero_output_events)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: '0.85rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            * Note: Logged stoppage reasons represent reported machine operator records. Root cause analysis is not inferred, and hypothetical lost production volume is not calculated.
          </div>
        </div>
      </div>
    </div>
  );
}
