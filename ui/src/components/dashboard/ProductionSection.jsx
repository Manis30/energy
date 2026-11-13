import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

function CustomProdTrendTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{label}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual:</span>
          <span className="tooltip-val">{formatNumber(data.actual_qty)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val">{formatNumber(data.good_qty)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rejected Units:</span>
          <span className="tooltip-val">{formatNumber(data.reject_qty)} ({formatPercent(data.reject_rate)})</span>
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

function CustomLineTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.line_id} ({data.line_type} - {data.plant_id})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Output:</span>
          <span className="tooltip-val">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Scrap Rate:</span>
          <span className="tooltip-val">{formatPercent(data.reject_rate)}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function ProductionSection({
  dailyTrend = [],
  byLine = [],
  productionSummary,
  trendAvailable = true,
  lineAvailable = true,
  summaryAvailable = true,
}) {
  const trendData = (dailyTrend || []).map((item) => ({
    ...item,
    displayDate: item.date ? item.date.slice(5) : '',
  }));
  const trendDates = trendData
    .map((item) => item.date)
    .filter((date) => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();
  const hasTrendValues = trendData.some((item) => hasNumber(item.actual_qty) || hasNumber(item.good_qty));

  const lineData = (byLine || []).map((l) => ({
    ...l,
    actual_num: l.actual_qty,
    good_num: l.good_qty,
    reject_num: l.reject_qty,
  }));
  const hasLineValues = lineData.some((item) => hasNumber(item.actual_qty) || hasNumber(item.good_qty));

  const actualUnits = productionSummary?.actual_qty ?? null;
  const goodUnits = productionSummary?.good_qty ?? null;
  const rejectUnits = productionSummary?.reject_qty ?? null;
  const reworkUnits = productionSummary?.rework_qty ?? null;
  const downtimeMin = productionSummary?.downtime_min ?? null;
  const balanceValid = productionSummary?.quantity_balance_valid;
  const hasBalanceResult = typeof balanceValid === 'boolean';

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Performance & Quality</h3>
          <p className="section-desc">
            Returned output quantities and API-reported rates. Target achievement is omitted while historical production targets remain unreconciled.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag quality">
            {hasNumber(productionSummary?.good_rate)
              ? `Reported quality yield: ${formatPercent(productionSummary.good_rate)}`
              : 'Quality yield unavailable'}
          </span>
          <span className="section-tag scrap">
            {hasNumber(productionSummary?.reject_rate)
              ? `Reported reject rate: ${formatPercent(productionSummary.reject_rate)}`
              : 'Reject rate unavailable'}
          </span>
        </div>
      </div>

      <div className="production-analytics-grid">
        {/* Daily Production Trend (Left) */}
        <div className="chart-card prod-trend-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Daily Production Output</h4>
              <span className="chart-card-subtitle">
                {trendAvailable
                  ? `${trendData.length} returned daily record(s)${trendDates.length > 0 ? ` · ${trendDates[0]} to ${trendDates[trendDates.length - 1]}` : ''}. Actual includes good and rejected quantities; series are not additive.`
                  : 'Production trend data unavailable'}
              </span>
            </div>
            <div className="chart-legend-custom">
              <span className="legend-item"><span className="legend-box actual"></span>Actual</span>
              <span className="legend-item"><span className="legend-box good"></span>Good</span>
            </div>
          </div>
          <div
            className="chart-wrapper"
            role="group"
            aria-label="Daily production bar chart comparing actual and good output in units by date; actual includes good output"
          >
            {!trendAvailable || trendData.length === 0 || !hasTrendValues ? (
              <div className="chart-empty-state">
                {!trendAvailable
                  ? 'Production trend request failed.'
                  : trendData.length === 0
                    ? 'No production trend records were returned.'
                    : 'Trend records were returned without usable production quantities.'}
              </div>
            ) : <ResponsiveContainer width="100%" height={270}>
              <BarChart data={trendData} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
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
                <Tooltip content={<CustomProdTrendTooltip />} />
                <Bar dataKey="actual_qty" fill="var(--brand-blue)" radius={[2, 2, 0, 0]} name="Actual" />
                <Bar dataKey="good_qty" fill="var(--chart-cat-4)" radius={[2, 2, 0, 0]} name="Good" />
              </BarChart>
            </ResponsiveContainer>}
          </div>
        </div>

        {/* Output by Line (Right) */}
        <div className="chart-card line-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Output Volume by Line</h4>
              <span className="chart-card-subtitle">Actual vs good output by returned line; production stages may use different unit scopes</span>
            </div>
          </div>
          <div
            className="chart-wrapper"
            role="group"
            aria-label="Production bar chart comparing actual and good output by line; production stages may use different units"
          >
            {!lineAvailable || lineData.length === 0 || !hasLineValues ? (
              <div className="chart-empty-state">
                {!lineAvailable
                  ? 'Production-by-line data unavailable.'
                  : lineData.length === 0
                    ? 'No production-by-line records were returned.'
                    : 'Line records were returned without usable production quantities.'}
              </div>
            ) : <ResponsiveContainer width="100%" height={270}>
              <BarChart data={lineData} layout="vertical" margin={{ top: 5, right: 25, left: 20, bottom: 5 }}>
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
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                />
                <Tooltip content={<CustomLineTooltip />} />
                <Bar dataKey="actual_num" fill="var(--brand-navy)" radius={[0, 4, 4, 0]} name="Actual Units" />
                <Bar dataKey="good_num" fill="var(--chart-cat-4)" radius={[0, 4, 4, 0]} name="Good Units" />
              </BarChart>
            </ResponsiveContainer>}
          </div>
        </div>
      </div>

      {/* Quality Reconciliation Summary (Bottom) */}
      <div className="quality-reconciliation-card">
        <div className="quality-reconciliation-header">
          <div>
            <h4 className="chart-card-title">Production Quantity & Quality Summary</h4>
            <span className="chart-card-subtitle">Actual output = good + rejected output; rework remains a separate quantity</span>
          </div>
          <span className={`verified-balance-pill ${balanceValid === true ? 'valid' : balanceValid === false ? 'invalid' : 'unavailable'}`}>
            {!summaryAvailable || !hasBalanceResult
              ? 'Quantity-balance check unavailable'
              : `API-reported quantity balance ${balanceValid ? 'valid' : 'not valid'}`}
          </span>
        </div>

        <div className="quality-metrics-row">
          <div className="quality-metric-item">
            <span className="quality-metric-label">Total Actual</span>
            <span className="quality-metric-val">{formatNumber(actualUnits)}</span>
            <span className="quality-metric-pct">Reported quantity; scope combines returned production lines</span>
          </div>
          <div className="quality-metric-item success">
            <span className="quality-metric-label">First-Pass Good</span>
            <span className="quality-metric-val">{formatNumber(goodUnits)}</span>
            <span className="quality-metric-pct">
              {hasNumber(productionSummary?.good_rate) ? `${formatPercent(productionSummary.good_rate)} API-reported yield` : 'Yield unavailable'}
            </span>
          </div>
          <div className="quality-metric-item danger">
            <span className="quality-metric-label">Rejected Output</span>
            <span className="quality-metric-val">{formatNumber(rejectUnits)}</span>
            <span className="quality-metric-pct">
              {hasNumber(productionSummary?.reject_rate) ? `${formatPercent(productionSummary.reject_rate)} API-reported reject rate` : 'Reject rate unavailable'}
            </span>
          </div>
          <div className="quality-metric-item warning">
            <span className="quality-metric-label">Rework Volume</span>
            <span className="quality-metric-val">{formatNumber(reworkUnits)}</span>
            <span className="quality-metric-pct">
              {hasNumber(productionSummary?.rework_rate) ? `${formatPercent(productionSummary.rework_rate)} separate rework rate` : 'Rework rate unavailable'}
            </span>
          </div>
          <div className="quality-metric-item info">
            <span className="quality-metric-label">Reported Downtime</span>
            <span className="quality-metric-val">{formatNumber(downtimeMin)} min</span>
            <span className="quality-metric-pct">
              {!summaryAvailable
                ? 'Production summary request failed'
                : hasNumber(productionSummary?.event_count)
                  ? `${formatNumber(productionSummary.event_count)} returned production event(s)`
                  : 'Event count unavailable'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

