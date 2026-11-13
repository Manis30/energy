import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  Legend,
} from 'recharts';
import { formatCurrency, formatDate, formatNumber, formatPercent } from '../../utils/formatters';

const METER_COLORS = {
  'MTR-SMT': '#6f3dba',
  'MTR-FAL': '#4d8eeb',
  'MTR-CHILLER': '#06b6d4',
  'MTR-COMPRESSOR': '#f59e0b',
  'MTR-HVAC': '#ec4899',
};

const AREA_COLORS = {
  'SMT': '#6f3dba',
  'FAL': '#4d8eeb',
  'CHILLER': '#06b6d4',
  'COMPRESSOR': '#f59e0b',
  'HVAC': '#ec4899',
};

function CustomMeterTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.meter_id} ({data.area})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.consumption_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Share of Plant:</span>
          <span className="tooltip-val">{formatPercent(data.percentage_of_total)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Spend:</span>
          <span className="tooltip-val">{formatCurrency(data.cost_inr)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Peak Hourly Energy:</span>
          <span className="tooltip-val">{formatNumber(data.peak_kwh, 2)} kWh</span>
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

function CustomAreaTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.name} Area</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Classification:</span>
          <span className="tooltip-val">{data.classification}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.value, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Share:</span>
          <span className="tooltip-val">{formatPercent(data.percentage)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Spend:</span>
          <span className="tooltip-val">{formatCurrency(data.cost)}</span>
        </div>
      </div>
    );
  }
  return null;
}

function CustomLineTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.line_id} ({data.line_type})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val text-success">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Scrap Units:</span>
          <span className="tooltip-val text-danger">{formatNumber(data.reject_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rework Units:</span>
          <span className="tooltip-val">{formatNumber(data.rework_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Downtime:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.downtime_min)} min</span>
        </div>
      </div>
    );
  }
  return null;
}

function CustomTrendTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{formatDate(data.date)}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Total Energy:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.consumption_kwh, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Cost:</span>
          <span className="tooltip-val">{formatCurrency(data.cost_inr)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">CO₂e:</span>
          <span className="tooltip-val">{formatNumber(data.co2e_kg, 2)} kg</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Avg PF:</span>
          <span className="tooltip-val">{data.avg_power_factor ? Number(data.avg_power_factor).toFixed(4) : '—'}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function DailyChartsSection({
  byMeter = [],
  byArea = [],
  byLine = [],
  dailyTrend = [],
  selectedDate,
  trendPeriod,
  trendAvailable = false,
}) {
  // Meter chart data
  const meterChartData = [...(byMeter || [])].sort(
    (a, b) => Number(b.consumption_kwh) - Number(a.consumption_kwh)
  );

  // Area pie data
  const areaChartData = (byArea || []).map((a) => ({
    name: a.area,
    value: Number(a.consumption_kwh),
    percentage: a.percentage_of_total,
    cost: a.cost_inr,
    classification: (a.area === 'SMT' || a.area === 'FAL') ? 'Process Energy' : 'Facility Utilities',
  }));

  // Line chart data
  const lineChartData = (byLine || []).map((l) => ({
    ...l,
    actual_num: Number(l.actual_qty),
    good_num: Number(l.good_qty),
    reject_num: Number(l.reject_qty),
    downtime_num: Number(l.downtime_min),
  }));

  // Trend data
  const trendChartData = (dailyTrend || []).map((t) => ({
    ...t,
    consumption_num: Number(t.consumption_kwh),
    isSelected: t.date === selectedDate,
  }));
  const trendDates = trendChartData
    .map((item) => item.date)
    .filter((date) => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();
  const trendDuration = trendPeriod
    ? Math.floor((Date.parse(`${trendPeriod.end_date}T00:00:00Z`) - Date.parse(`${trendPeriod.start_date}T00:00:00Z`)) / 86400000) + 1
    : null;

  return (
    <div className="dashboard-section daily-charts-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Energy & Operational Trends</h3>
          <p className="section-desc">
            Granular meter-level breakdown, area distribution, production line throughput, and 7-day contextual energy trend.
          </p>
        </div>
      </div>

      <div className="daily-charts-grid">
        {/* Chart 1: Energy Consumption by Meter */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Energy Consumption by Submeter</h4>
              <p className="chart-card-subtitle">Returned daily kWh totals by meter; meter scopes are not normalized for efficiency comparison</p>
            </div>
          </div>
          <div className="chart-body" role="group" aria-label="Daily submeter energy bar chart in kilowatt-hours by meter">
            {meterChartData.length === 0 ? (
              <div className="chart-empty-state">No meter data recorded for this date</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={meterChartData} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                  <XAxis
                    dataKey="meter_id"
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => `${(val / 1000).toFixed(1)}k`}
                  />
                  <Tooltip content={<CustomMeterTooltip />} />
                  <Bar dataKey="consumption_kwh" name="Energy (kWh)" radius={[4, 4, 0, 0]}>
                    {meterChartData.map((entry) => (
                      <Cell
                        key={`cell-${entry.meter_id}`}
                        fill={METER_COLORS[entry.meter_id] || '#6f3dba'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-card-footer">
            <span className="chart-legend-hint">SMT, FAL, and utility meter totals may reflect different production scopes and operating conditions.</span>
          </div>
        </div>

        {/* Chart 2: Energy by Production Area */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Energy Share by Production Area</h4>
              <p className="chart-card-subtitle">Relative proportion of process manufacturing vs plant utilities</p>
            </div>
          </div>
          <div className="chart-body" role="group" aria-label="Daily energy share pie chart by returned area in kilowatt-hours">
            {areaChartData.length === 0 ? (
              <div className="chart-empty-state">No area data recorded for this date</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Tooltip content={<CustomAreaTooltip />} />
                  <Pie
                    data={areaChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={3}
                    dataKey="value"
                    nameKey="name"
                  >
                    {areaChartData.map((entry) => (
                      <Cell
                        key={`area-cell-${entry.name}`}
                        fill={AREA_COLORS[entry.name] || '#4d8eeb'}
                      />
                    ))}
                  </Pie>
                  <Legend
                    verticalAlign="bottom"
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: '0.75rem', paddingTop: '10px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-card-footer">
            <span className="chart-legend-hint">Delineates SMT & FAL from Chiller, Compressor, and HVAC</span>
          </div>
        </div>

        {/* Chart 3: Production Throughput by Line */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Production Output & Quality by Line</h4>
              <p className="chart-card-subtitle">Actual vs Good unit volumes across SMT and Final Assembly lines</p>
            </div>
          </div>
          <div className="chart-body" role="group" aria-label="Daily production bar chart comparing actual, good, and rejected output by line; production stages use different units">
            {lineChartData.length === 0 ? (
              <div className="chart-empty-state">No line production records for this date</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={lineChartData} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                  <XAxis
                    dataKey="line_id"
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => `${(val / 1000).toFixed(1)}k`}
                  />
                  <Tooltip content={<CustomLineTooltip />} />
                  <Legend
                    verticalAlign="top"
                    align="right"
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: '0.75rem', paddingBottom: '8px' }}
                  />
                  <Bar dataKey="actual_num" name="Actual Units" fill="#6f3dba" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="good_num" name="Good Units" fill="#10b981" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="reject_num" name="Scrap Units" fill="#ef4444" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-card-footer">
            <span className="chart-legend-hint">SMT units represent circuit boards; FAL units represent finished phones</span>
          </div>
        </div>

        {/* Chart 4: Trailing 7-Day Contextual Trend */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">7-Day Energy Consumption Context</h4>
              <p className="chart-card-subtitle">
                Requested window: {trendPeriod && trendDuration > 0
                  ? `${formatDate(trendPeriod.start_date)} – ${formatDate(trendPeriod.end_date)} (${trendDuration} calendar days)`
                  : 'unavailable'}; {trendChartData.length} returned daily records
                {trendDates.length > 0 && ` from ${formatDate(trendDates[0])} to ${formatDate(trendDates[trendDates.length - 1])}`}.
              </p>
            </div>
          </div>
          <div className="chart-body" role="group" aria-label="Daily energy consumption area chart in kilowatt-hours over the returned trend period">
            {!trendAvailable || trendChartData.length === 0 ? (
              <div className="chart-empty-state">
                {!trendAvailable
                  ? 'The historical trend request failed; no period context is available.'
                  : 'No daily trend records were returned for this period.'}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={trendChartData} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                  <defs>
                    <linearGradient id="dailyTrendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4d8eeb" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#4d8eeb" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                  <XAxis
                    dataKey="date"
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(val) => {
                      const parts = val.split('-');
                      return `${parts[1]}/${parts[2]}`;
                    }}
                  />
                  <YAxis
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    domain={['auto', 'auto']}
                    tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                  />
                  <Tooltip content={<CustomTrendTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="consumption_num"
                    name="Daily kWh"
                    stroke="#4d8eeb"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#dailyTrendGrad)"
                    dot={(props) => {
                      const isSel = props.payload.isSelected;
                      return (
                        <circle
                          key={`dot-${props.payload.date}`}
                          cx={props.cx}
                          cy={props.cy}
                          r={isSel ? 5 : 3}
                          fill={isSel ? '#6f3dba' : '#4d8eeb'}
                          stroke="#ffffff"
                          strokeWidth={isSel ? 2 : 1}
                        />
                      );
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-card-footer">
            <span className="chart-legend-hint">
              Purple marker indicates the selected date ({selectedDate}); other points are historical daily totals. This is context only—not an expected-energy baseline or normalized comparison. Production volume and operating conditions may affect total kWh; changes alone do not prove efficiency changes or savings.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
