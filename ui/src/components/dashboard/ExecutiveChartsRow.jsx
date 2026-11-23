import React from 'react';
import { Link } from 'react-router-dom';
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
} from 'recharts';
import { formatNumber, formatPercent, formatCurrency } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

function EnergyTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip exec-chart-tooltip">
        <div className="tooltip-title">{data.date || label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val">
            {hasNumber(data.consumption_kwh)
              ? `${formatNumber(data.consumption_kwh, 2)} kWh`
              : 'Unavailable'}
          </span>
        </div>
        {hasNumber(data.peak_hourly_kwh) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Peak Hour:</span>
            <span className="tooltip-val">{formatNumber(data.peak_hourly_kwh, 2)} kWh</span>
          </div>
        )}
        {hasNumber(data.cost_inr) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Est. Cost:</span>
            <span className="tooltip-val">{formatCurrency(data.cost_inr)}</span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

function ProductionTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const actual = data.actual_qty;
    const good = data.good_qty;
    const reject =
      data.reject_qty ??
      (hasNumber(actual) && hasNumber(good) ? Math.max(0, actual - good) : null);
    const scrapRate =
      data.reject_rate ??
      (hasNumber(actual) && actual > 0 && hasNumber(reject) ? reject / actual : null);

    return (
      <div className="custom-chart-tooltip exec-chart-tooltip">
        <div className="tooltip-title">{data.date || label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val">
            {hasNumber(actual) ? `${formatNumber(actual)} units` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val">
            {hasNumber(good) ? `${formatNumber(good)} units` : 'Unavailable'}
          </span>
        </div>
        {hasNumber(reject) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Scrap / Rejects:</span>
            <span className="tooltip-val">
              {formatNumber(reject)} units{' '}
              {scrapRate != null ? `(${formatPercent(scrapRate, 1)})` : ''}
            </span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

export function ExecutiveChartsRow({
  energyTrend = [],
  productionTrend = [],
  energyAvailable = true,
  productionAvailable = true,
  loading = false,
  resolvedDateRange,
}) {
  // Format energy data
  const energyData = (energyTrend || []).map((item) => ({
    ...item,
    consumption_kwh_num: hasNumber(item.consumption_kwh) ? Number(item.consumption_kwh) : null,
    displayDate: item.date ? item.date.slice(5) : '', // 'MM-DD'
  }));
  const hasEnergyValues = energyData.some((item) => hasNumber(item.consumption_kwh_num));

  // Format production data
  const prodData = (productionTrend || []).map((item) => ({
    ...item,
    actual_num: hasNumber(item.actual_qty) ? Number(item.actual_qty) : null,
    good_num: hasNumber(item.good_qty) ? Number(item.good_qty) : null,
    displayDate: item.date ? item.date.slice(5) : '',
  }));
  const hasProdValues = prodData.some(
    (item) => hasNumber(item.actual_num) || hasNumber(item.good_num)
  );

  const rangeLabel = resolvedDateRange?.label || 'selected period';

  return (
    <div className="dashboard-charts-grid">
      {/* 1. Daily Energy Consumption */}
      <div className="chart-card executive-chart-card">
        <div className="chart-card-header executive-chart-header">
          <div className="chart-title-wrap">
            <h3 className="chart-card-title">Daily Energy Consumption</h3>
          </div>
          <div className="chart-header-right">
            <Link to="/energy-analytics" className="chart-header-action" title="Open Energy Analytics">
              <span>Energy Analytics</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </Link>
          </div>
        </div>

        <div className="chart-wrapper executive-chart-wrapper" role="group" aria-label="Daily energy consumption trend area chart in kWh">
          {loading ? (
            <div className="chart-skeleton-box" aria-hidden="true">
              <div className="skeleton-chart-bars" />
            </div>
          ) : !energyAvailable || energyData.length === 0 || !hasEnergyValues ? (
            <div className="chart-empty-state">
              {!energyAvailable
                ? 'Energy telemetry feed is currently offline.'
                : `No energy records returned for ${rangeLabel}.`}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={215}>
              <AreaChart data={energyData} margin={{ top: 8, right: 14, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="execEnergyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--brand-purple, #6f3dba)" stopOpacity={0.32} />
                    <stop offset="95%" stopColor="var(--brand-purple, #6f3dba)" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, rgba(0,0,0,0.06))" vertical={false} />
                <XAxis
                  dataKey="displayDate"
                  stroke="var(--chart-axis, #94a3b8)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis, #94a3b8)', fontFamily: 'var(--font-family)' }}
                  tickLine={false}
                  interval={energyData.length > 30 ? 6 : energyData.length > 14 ? 3 : 1}
                />
                <YAxis
                  stroke="var(--chart-axis, #94a3b8)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis, #94a3b8)', fontFamily: 'var(--font-family)' }}
                  tickLine={false}
                  tickFormatter={(val) => (val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val)}
                />
                <Tooltip content={<EnergyTooltip />} />
                <Area
                  type="monotone"
                  dataKey="consumption_kwh_num"
                  stroke="var(--brand-purple, #6f3dba)"
                  strokeWidth={2.4}
                  dot={energyData.length <= 5 ? { r: 5, fill: 'var(--brand-purple, #6f3dba)' } : false}
                  activeDot={{ r: 6 }}
                  fillOpacity={1}
                  fill="url(#execEnergyGrad)"
                  name="Energy (kWh)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* 2. Daily Production Output */}
      <div className="chart-card executive-chart-card">
        <div className="chart-card-header executive-chart-header">
          <div className="chart-title-wrap">
            <h3 className="chart-card-title">Daily Production Output</h3>
          </div>
          <div className="chart-header-right">
            <div className="chart-legend-compact" aria-hidden="true">
              <span className="legend-badge actual">
                <span className="legend-dot actual" />
                Actual
              </span>
              <span className="legend-badge good">
                <span className="legend-dot good" />
                Good
              </span>
            </div>
            <Link to="/production-analytics" className="chart-header-action" title="Open Production Analytics">
              <span>Production Analytics</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </Link>
          </div>
        </div>

        <div className="chart-wrapper executive-chart-wrapper" role="group" aria-label="Daily production output bar chart comparing actual and good units">
          {loading ? (
            <div className="chart-skeleton-box" aria-hidden="true">
              <div className="skeleton-chart-bars" />
            </div>
          ) : !productionAvailable || prodData.length === 0 || !hasProdValues ? (
            <div className="chart-empty-state">
              {!productionAvailable
                ? 'Production telemetry feed is currently offline.'
                : `No production records returned for ${rangeLabel}.`}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={215}>
              <BarChart data={prodData} margin={{ top: 8, right: 14, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, rgba(0,0,0,0.06))" vertical={false} />
                <XAxis
                  dataKey="displayDate"
                  stroke="var(--chart-axis, #94a3b8)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis, #94a3b8)', fontFamily: 'var(--font-family)' }}
                  tickLine={false}
                  interval={prodData.length > 30 ? 6 : prodData.length > 14 ? 3 : 1}
                />
                <YAxis
                  stroke="var(--chart-axis, #94a3b8)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis, #94a3b8)', fontFamily: 'var(--font-family)' }}
                  tickLine={false}
                  tickFormatter={(val) => (val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val)}
                />
                <Tooltip content={<ProductionTooltip />} />
                <Bar
                  dataKey="actual_num"
                  fill="var(--brand-blue, #4d8eeb)"
                  radius={[3, 3, 0, 0]}
                  maxBarSize={prodData.length <= 3 ? 42 : 28}
                  name="Actual Units"
                />
                <Bar
                  dataKey="good_num"
                  fill="var(--status-success, #10b981)"
                  radius={[3, 3, 0, 0]}
                  maxBarSize={prodData.length <= 3 ? 42 : 28}
                  name="Good Units"
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

export default ExecutiveChartsRow;
