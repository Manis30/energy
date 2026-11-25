import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { formatNumber } from '../../utils/formatters';
import { operatingContextApi } from '../../services/operatingContextApi';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

function formatDayMonth(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length < 3) return dateStr;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const m = parseInt(parts[1], 10) - 1;
  const d = parseInt(parts[2], 10);
  return `${d} ${months[m] || parts[1]}`;
}

function formatFullDate(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length < 3) return dateStr;
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  const m = parseInt(parts[1], 10) - 1;
  const d = parseInt(parts[2], 10);
  const y = parts[0];
  return `${d} ${months[m] || parts[1]} ${y}`;
}

/**
 * Hourly Energy Area Chart for Single Date View
 */
function HourlyEnergyChart({ hourlyData = [] }) {
  return (
    <ResponsiveContainer width="100%" height={215}>
      <AreaChart data={hourlyData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="hourlyEnergyGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--brand-purple, #6f3dba)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--brand-purple, #6f3dba)" stopOpacity={0.01} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, rgba(0,0,0,0.06))" vertical={false} />
        <XAxis
          dataKey="hourLabel"
          stroke="var(--chart-axis, #94a3b8)"
          tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
          tickLine={false}
          interval={3}
        />
        <YAxis
          domain={[0, 'auto']}
          stroke="var(--chart-axis, #94a3b8)"
          tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
          tickLine={false}
          tickFormatter={(val) => (val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val)}
          width={45}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (active && payload && payload.length) {
              const d = payload[0].payload;
              return (
                <div className="custom-chart-tooltip exec-chart-tooltip" role="tooltip">
                  <div className="tooltip-title">{d.date} · {d.hourLabel}</div>
                  <div className="tooltip-row">
                    <span className="tooltip-label">Hourly Use:</span>
                    <span className="tooltip-val" style={{ color: '#6f3dba' }}>{formatNumber(d.consumption_kwh, 2)} kWh</span>
                  </div>
                </div>
              );
            }
            return null;
          }}
        />
        <Area
          type="monotone"
          dataKey="consumption_kwh"
          stroke="var(--brand-purple, #6f3dba)"
          strokeWidth={2.2}
          fillOpacity={1}
          fill="url(#hourlyEnergyGrad)"
          name="Hourly Consumption"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/**
 * Single Day Observation Card for Energy
 */
function SingleDayEnergyCard({ item }) {
  const kwh = item?.consumption_kwh;
  return (
    <div className="single-observation-container">
      <div className="single-obs-badge">Single Observation</div>
      <div className="single-obs-date">{formatFullDate(item?.date)}</div>
      <div className="single-obs-value" style={{ color: '#6f3dba' }}>
        {hasNumber(kwh) ? `${formatNumber(kwh, 2)} kWh` : 'No reading recorded'}
      </div>
      <div className="single-obs-sub">Aggregated electricity consumption for selected date</div>
    </div>
  );
}

/**
 * Single Day Observation Card for Production
 */
function SingleDayProductionCard({ item }) {
  const actual = item?.actual_qty;
  const good = item?.good_qty;
  const yieldVal = item?.yield_pct;

  return (
    <div className="single-observation-container">
      <div className="single-obs-badge">Single Observation</div>
      <div className="single-obs-date">{formatFullDate(item?.date)}</div>
      <div className="single-obs-stats-grid">
        <div className="single-obs-stat">
          <div className="stat-label">Actual Output</div>
          <div className="stat-val" style={{ color: '#3b82f6' }}>
            {hasNumber(actual) ? `${formatNumber(actual)} units` : '—'}
          </div>
        </div>
        <div className="single-obs-stat">
          <div className="stat-label">Good Units</div>
          <div className="stat-val" style={{ color: '#10b981' }}>
            {hasNumber(good) ? `${formatNumber(good)} units` : '—'}
          </div>
        </div>
        <div className="single-obs-stat">
          <div className="stat-label">Yield Rate</div>
          <div className="stat-val font-semibold" style={{ color: '#0f172a' }}>
            {hasNumber(yieldVal) ? `${Number(yieldVal).toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>
      <div className="single-obs-sub">Production performance for selected date</div>
    </div>
  );
}

/**
 * Custom Tooltip for Daily Energy Line Chart
 */
function EnergyDailyTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const kwh = data.consumption_kwh;

    return (
      <div className="custom-chart-tooltip exec-chart-tooltip" role="tooltip">
        <div className="tooltip-title">{formatFullDate(data.date) || data.date}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Electricity Use:</span>
          <span className="tooltip-val font-semibold" style={{ color: '#6f3dba' }}>
            {kwh !== null ? `${formatNumber(kwh, 2)} kWh` : 'No reading recorded'}
          </span>
        </div>
        {data.isPeak && (
          <div className="tooltip-row tooltip-badge-row">
            <span className="tooltip-badge-peak">Peak use in period</span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

/**
 * Custom Tooltip for Production Shared Plots
 */
function ProductionSharedTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const actual = data.actual_qty;
    const good = data.good_qty;
    const yieldVal = data.yield_pct;

    return (
      <div className="custom-chart-tooltip exec-chart-tooltip" role="tooltip">
        <div className="tooltip-title">{formatFullDate(data.date) || data.date}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val" style={{ color: '#3b82f6' }}>
            {hasNumber(actual) ? `${formatNumber(actual)} units` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val" style={{ color: '#10b981' }}>
            {hasNumber(good) ? `${formatNumber(good)} units` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row tooltip-highlight-row">
          <span className="tooltip-label">Yield:</span>
          <span
            className="tooltip-val font-semibold"
            style={{ color: data.isLowestYield ? '#ef4444' : '#10b981' }}
          >
            {hasNumber(yieldVal) ? `${Number(yieldVal).toFixed(1)}%` : 'Unavailable'}
          </span>
        </div>
        {data.isLowestYield && (
          <div className="tooltip-row tooltip-badge-row">
            <span className="tooltip-badge-low">Lowest yield in period</span>
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
  selectedPlant = 'ALL',
  selectedShift = 'ALL',
}) {
  const isDaily = Boolean(resolvedDateRange?.isDaily);
  const rangeLabel = resolvedDateRange?.label || 'selected period';

  // State for hourly observations on single-date view
  const [hourlyProfile, setHourlyProfile] = useState(null);
  const [hourlyLoading, setHourlyLoading] = useState(false);

  useEffect(() => {
    let active = true;
    if (isDaily && resolvedDateRange?.startDate) {
      setHourlyLoading(true);
      const params = {
        start_date: resolvedDateRange.startDate,
        end_date: resolvedDateRange.endDate,
        ...(selectedPlant !== 'ALL' ? { plant_id: selectedPlant } : {}),
      };

      const shiftHourMap = {
        A: [6, 7, 8, 9, 10, 11, 12, 13],
        B: [14, 15, 16, 17, 18, 19, 20, 21],
        C: [22, 23, 0, 1, 2, 3, 4, 5],
      };
      const cleanShift = selectedShift !== 'ALL' ? selectedShift.replace('Shift ', '').trim().toUpperCase() : null;
      const validHours = cleanShift ? shiftHourMap[cleanShift] : null;

      operatingContextApi
        .getObservations(params)
        .then((obs) => {
          if (!active) return;
          if (Array.isArray(obs) && obs.length > 0) {
            const hourSums = Array(24).fill(0);
            let hasAny = false;
            obs.forEach((o) => {
              const h = Number(o.hour);
              const val = Number(o.consumption_kwh) || 0;
              if (h >= 0 && h < 24) {
                if (validHours && !validHours.includes(h)) return;
                hourSums[h] += val;
                if (val > 0) hasAny = true;
              }
            });
            if (hasAny) {
              const hoursToMap = validHours || Array.from({ length: 24 }, (_, i) => i);
              const profile = hoursToMap.map((h) => ({
                hour: h,
                hourLabel: `${String(h).padStart(2, '0')}:00`,
                consumption_kwh: hourSums[h] || 0,
                date: resolvedDateRange.startDate,
              }));
              setHourlyProfile(profile);
            } else {
              setHourlyProfile(null);
            }
          } else {
            setHourlyProfile(null);
          }
        })
        .catch((err) => {
          if (!active) return;
          console.warn('Hourly observations fetch notice:', err);
          setHourlyProfile(null);
        })
        .finally(() => {
          if (active) setHourlyLoading(false);
        });
    } else {
      setHourlyProfile(null);
      setHourlyLoading(false);
    }
    return () => {
      active = false;
    };
  }, [isDaily, resolvedDateRange?.startDate, resolvedDateRange?.endDate, selectedPlant, selectedShift]);

  // Format Energy Trend Data
  const energyData = useMemo(() => {
    const rawList = (energyTrend || []).map((item) => {
      const isRecorded = hasNumber(item.consumption_kwh);
      const kwh = isRecorded ? Number(item.consumption_kwh) : null;
      return {
        ...item,
        date: item.date,
        consumption_kwh: kwh,
      };
    });

    // Find peak day (highest recorded kWh > 0)
    let peakItem = null;
    rawList.forEach((item) => {
      if (item.consumption_kwh !== null && item.consumption_kwh > 0) {
        if (!peakItem || item.consumption_kwh > peakItem.consumption_kwh) {
          peakItem = item;
        }
      }
    });

    // Calculate period average (mean of valid non-null days)
    const validRecorded = rawList.filter((item) => item.consumption_kwh !== null);
    const avg =
      validRecorded.length > 0
        ? Math.round(
            validRecorded.reduce((sum, item) => sum + item.consumption_kwh, 0) /
              validRecorded.length
          )
        : 0;

    return rawList.map((item) => ({
      ...item,
      isPeak: peakItem ? item.date === peakItem.date : false,
      periodAverage: avg > 0 ? avg : null,
    }));
  }, [energyTrend]);

  const hasEnergyValues = useMemo(
    () => energyData.some((item) => item.consumption_kwh !== null),
    [energyData]
  );

  const peakEnergyDay = useMemo(
    () => energyData.find((item) => item.isPeak) || null,
    [energyData]
  );

  const periodAverageKwh = useMemo(() => {
    const valid = energyData.filter((item) => item.consumption_kwh !== null);
    if (valid.length === 0) return 0;
    return Math.round(
      valid.reduce((sum, item) => sum + item.consumption_kwh, 0) / valid.length
    );
  }, [energyData]);

  // Format Production Trend Data
  const prodData = useMemo(() => {
    const rawList = (productionTrend || []).map((item) => {
      const actual = hasNumber(item.actual_qty) ? Number(item.actual_qty) : null;
      const good = hasNumber(item.good_qty) ? Number(item.good_qty) : null;
      let yieldVal = null;

      if (hasNumber(item.yield_pct)) {
        yieldVal = Number(item.yield_pct);
      } else if (hasNumber(item.good_rate)) {
        const gr = Number(item.good_rate);
        yieldVal = gr <= 1 ? gr * 100 : gr;
      } else if (actual !== null && good !== null && actual > 0) {
        yieldVal = (good / actual) * 100;
      }

      if (yieldVal !== null) {
        yieldVal = Number(yieldVal.toFixed(2));
      }

      return {
        ...item,
        actual_qty: actual,
        good_qty: good,
        yield_pct: yieldVal,
        date: item.date,
      };
    });

    // Find day with lowest valid yield where production occurred (actual > 0 and yield_pct != null)
    let lowestDay = null;
    rawList.forEach((item) => {
      if (
        item.actual_qty !== null &&
        item.actual_qty > 0 &&
        item.yield_pct !== null
      ) {
        if (!lowestDay || item.yield_pct < lowestDay.yield_pct) {
          lowestDay = item;
        }
      }
    });

    return rawList.map((item) => ({
      ...item,
      isLowestYield: lowestDay ? item.date === lowestDay.date : false,
    }));
  }, [productionTrend]);

  const hasProdValues = useMemo(
    () =>
      prodData.some(
        (item) => item.actual_qty !== null || item.good_qty !== null
      ),
    [prodData]
  );

  const lowestYieldDay = useMemo(
    () => prodData.find((item) => item.isLowestYield) || null,
    [prodData]
  );

  // Period yield: total good units / total actual units across filtered range
  const periodYieldInfo = useMemo(() => {
    let totalGood = 0;
    let totalActual = 0;
    let count = 0;

    prodData.forEach((item) => {
      if (
        item.actual_qty !== null &&
        item.good_qty !== null &&
        item.actual_qty > 0
      ) {
        totalGood += item.good_qty;
        totalActual += item.actual_qty;
        count += 1;
      }
    });

    if (count === 0 || totalActual === 0) {
      return { yieldPct: null, totalGood: 0, totalActual: 0, available: false };
    }

    const yieldPct = ((totalGood / totalActual) * 100).toFixed(1);
    return { yieldPct, totalGood, totalActual, available: true };
  }, [prodData]);

  // Y-axis Zoom for Production Yield line so drops are prominent
  const yieldAxisDomain = useMemo(() => {
    const validYields = prodData
      .map((d) => d.yield_pct)
      .filter((y) => y !== null && y !== undefined && Number.isFinite(y));

    if (validYields.length === 0) {
      return { yMin: 90, yMax: 100, ticks: [90, 95, 100] };
    }

    const minVal = Math.min(...validYields);
    const maxVal = Math.max(...validYields);
    const yMin = Math.max(0, Math.floor(minVal - 2));
    const yMax = Math.min(100, Math.ceil(maxVal + 1));
    const mid = Math.round((yMin + yMax) / 2);
    const ticks = Array.from(new Set([yMin, mid, yMax])).sort((a, b) => a - b);
    return { yMin, yMax: yMax <= yMin ? yMin + 5 : yMax, ticks };
  }, [prodData]);

  // Dynamic X-axis interval to avoid crowded labels
  const dateInterval = useMemo(() => {
    const len = Math.max(energyData.length, prodData.length);
    if (len > 24) return 4;
    if (len > 14) return 2;
    if (len > 7) return 1;
    return 0;
  }, [energyData.length, prodData.length]);

  // Energy Takeaway: "Peak use on 21 Oct · 21,646 kWh"
  const energyTakeaway = useMemo(() => {
    if (isDaily) {
      if (hourlyProfile && hourlyProfile.length > 0) {
        const peak = hourlyProfile.reduce(
          (max, h) => (h.consumption_kwh > (max?.consumption_kwh || 0) ? h : max),
          hourlyProfile[0]
        );
        if (peak && peak.consumption_kwh > 0) {
          const nextH = (peak.hour + 1) % 24;
          const nextHStr = `${String(nextH).padStart(2, '0')}:00`;
          return (
            <span>
              Peak hour: {peak.hourLabel}–{nextHStr} ·{' '}
              <strong className="highlight">{formatNumber(peak.consumption_kwh, 1)} kWh</strong>
            </span>
          );
        }
      }
      if (energyData[0] && energyData[0].consumption_kwh !== null) {
        return (
          <span>
            Daily total: {formatDayMonth(energyData[0].date)} ·{' '}
            <strong className="highlight">{formatNumber(energyData[0].consumption_kwh, 0)} kWh</strong>
          </span>
        );
      }
      return <span>Daily consumption profile</span>;
    }

    if (peakEnergyDay && peakEnergyDay.consumption_kwh > 0) {
      return (
        <span>
          Peak use on {formatDayMonth(peakEnergyDay.date)} ·{' '}
          <strong className="highlight">{formatNumber(peakEnergyDay.consumption_kwh, 0)} kWh</strong>
        </span>
      );
    }

    return <span>Monthly consumption profile</span>;
  }, [isDaily, hourlyProfile, energyData, peakEnergyDay]);

  // Production Takeaway: "Period yield 98.1% · Lowest yield on [date]"
  const productionTakeaway = useMemo(() => {
    if (!periodYieldInfo.available) {
      return <span>Period yield: <span className="text-muted">Unavailable</span></span>;
    }

    if (lowestYieldDay) {
      return (
        <span>
          Period yield <strong className="highlight">{periodYieldInfo.yieldPct}%</strong> ·{' '}
          Lowest yield on {formatDayMonth(lowestYieldDay.date)}
        </span>
      );
    }

    return (
      <span>
        Period yield <strong className="highlight">{periodYieldInfo.yieldPct}%</strong> ({formatNumber(periodYieldInfo.totalGood)} / {formatNumber(periodYieldInfo.totalActual)} units)
      </span>
    );
  }, [periodYieldInfo, lowestYieldDay]);

  // Single Day Detection
  const isSingleEnergyDay = isDaily || energyData.length === 1;
  const isSingleProdDay = isDaily || prodData.length === 1;

  return (
    <div className="dashboard-charts-grid">
      {/* 1. Daily Energy Consumption */}
      <div className="chart-card executive-chart-card">
        {/* Row 1: Title and Analytics Link */}
        <div className="chart-card-header executive-chart-header">
          <div className="chart-title-wrap">
            <h3 className="chart-card-title" style={{ fontSize: '15px', fontWeight: 600 }}>Daily Energy Consumption</h3>
          </div>
          <div className="chart-header-right">
            <Link
              to="/energy-analytics"
              className="chart-header-action"
              title="Open Energy Analytics"
            >
              <span>Energy Analytics</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </Link>
          </div>
        </div>

        {/* Row 2: One-line Takeaway Banner */}
        <div className="chart-takeaway-banner" role="status">
          <div className="takeaway-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
          </div>
          <div className="takeaway-content">{energyTakeaway}</div>
        </div>

        {/* Row 3: Plot Area */}
        <div
          className="chart-wrapper executive-chart-wrapper"
          role="group"
          aria-label="Daily energy consumption line chart in kWh"
        >
          {loading || (isDaily && hourlyLoading) ? (
            <div className="chart-skeleton-box" aria-hidden="true">
              <div className="skeleton-chart-bars" />
            </div>
          ) : !energyAvailable || energyData.length === 0 || !hasEnergyValues ? (
            <div className="chart-empty-state">
              {!energyAvailable
                ? 'Energy telemetry feed is currently offline.'
                : `No energy records returned for ${rangeLabel}.`}
            </div>
          ) : isSingleEnergyDay ? (
            hourlyProfile && hourlyProfile.length > 0 ? (
              <HourlyEnergyChart hourlyData={hourlyProfile} />
            ) : (
              <SingleDayEnergyCard item={energyData[0]} />
            )
          ) : (
            <ResponsiveContainer width="100%" height={215}>
              <AreaChart
                data={energyData}
                margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="dailyEnergyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6f3dba" stopOpacity={0.16} />
                    <stop offset="95%" stopColor="#6f3dba" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--chart-grid, rgba(0,0,0,0.06))"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  stroke="var(--chart-axis, #94a3b8)"
                  tickLine={false}
                  tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
                  tickFormatter={formatDayMonth}
                  interval={dateInterval}
                />
                <YAxis
                  domain={[0, (dataMax) => Math.ceil((dataMax * 1.12) / 1000) * 1000]}
                  stroke="var(--chart-axis, #94a3b8)"
                  tickLine={false}
                  tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
                  tickFormatter={(val) => (val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val)}
                  width={45}
                />
                <Tooltip content={<EnergyDailyTooltip />} />
                {periodAverageKwh > 0 && (
                  <ReferenceLine
                    y={periodAverageKwh}
                    stroke="#94a3b8"
                    strokeDasharray="4 4"
                    label={{
                      value: 'Period average',
                      position: 'insideTopLeft',
                      fill: '#64748b',
                      fontSize: 11,
                      fontWeight: 500,
                      dy: -10,
                      dx: 8,
                    }}
                  />
                )}
                <Area
                  type="monotone"
                  dataKey="consumption_kwh"
                  stroke="#6f3dba"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#dailyEnergyGrad)"
                  connectNulls={false}
                  name="Daily Electricity Use"
                  dot={(props) => {
                    const { cx, cy, payload } = props;
                    if (payload?.isPeak && cx != null && cy != null) {
                      return (
                        <g key={`peak-dot-${payload.date}`}>
                          <circle cx={cx} cy={cy} r={5} fill="#6f3dba" stroke="#ffffff" strokeWidth={2} />
                          <circle cx={cx} cy={cy} r={8} fill="none" stroke="#6f3dba" strokeOpacity={0.35} strokeWidth={2} />
                        </g>
                      );
                    }
                    return null;
                  }}
                  activeDot={{ r: 6, fill: '#6f3dba', stroke: '#ffffff', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Bottom Legend */}
        <div className="chart-legend-bottom" aria-hidden="true">
          <span className="legend-item">
            <span className="legend-swatch-line purple" />
            <span>Electricity use (kWh)</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch-dashed" />
            <span>Period average</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch-dot purple" />
            <span>Peak day</span>
          </span>
        </div>
      </div>

      {/* 2. Daily Production Output */}
      <div className="chart-card executive-chart-card">
        {/* Row 1: Title and Analytics Link (No colliding legend!) */}
        <div className="chart-card-header executive-chart-header">
          <div className="chart-title-wrap">
            <h3 className="chart-card-title" style={{ fontSize: '15px', fontWeight: 600 }}>Daily Production Output</h3>
          </div>
          <div className="chart-header-right">
            <Link
              to="/production-analytics"
              className="chart-header-action"
              title="Open Production Analytics"
            >
              <span>Production Analytics</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </Link>
          </div>
        </div>

        {/* Row 2: One-line Takeaway Banner */}
        <div className="chart-takeaway-banner" role="status">
          <div className="takeaway-icon prod-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div className="takeaway-content">{productionTakeaway}</div>
        </div>

        {/* Row 3: Plot Area - Two Aligned Plots with Shared Date Axis */}
        <div
          className="chart-wrapper executive-chart-wrapper"
          role="group"
          aria-label="Daily production actual output bars and quality yield line chart"
        >
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
          ) : isSingleProdDay ? (
            <SingleDayProductionCard item={prodData[0]} />
          ) : (
            <div className="production-dual-plots">
              {/* Upper plot: Actual output compact blue bars (height: 130px) */}
              <div className="production-bars-plot" style={{ height: 130 }}>
                <ResponsiveContainer width="100%" height={130}>
                  <BarChart
                    data={prodData}
                    syncId="dailyProductionShared"
                    margin={{ top: 8, right: 16, left: 0, bottom: 2 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="var(--chart-grid, rgba(0,0,0,0.06))"
                      vertical={false}
                    />
                    <XAxis dataKey="date" hide={true} />
                    <YAxis
                      domain={[0, (dataMax) => Math.ceil((dataMax * 1.12) / 1000) * 1000]}
                      stroke="var(--chart-axis, #94a3b8)"
                      tickLine={false}
                      tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
                      tickFormatter={(val) => (val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val)}
                      width={45}
                    />
                    <Tooltip content={<ProductionSharedTooltip />} cursor={{ fill: 'rgba(0, 0, 0, 0.04)' }} />
                    <Bar
                      dataKey="actual_qty"
                      fill="var(--brand-blue, #3b82f6)"
                      name="Actual Output"
                      maxBarSize={prodData.length <= 5 ? 32 : 18}
                      radius={[3, 3, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Lower plot: Quality Yield green line with zoomed percentage axis (height: 85px) */}
              <div className="production-yield-plot" style={{ height: 85 }}>
                <ResponsiveContainer width="100%" height={85}>
                  <LineChart
                    data={prodData}
                    syncId="dailyProductionShared"
                    margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="var(--chart-grid, rgba(0,0,0,0.06))"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="date"
                      stroke="var(--chart-axis, #94a3b8)"
                      tickLine={false}
                      tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
                      tickFormatter={formatDayMonth}
                      interval={dateInterval}
                    />
                    <YAxis
                      domain={[yieldAxisDomain.yMin, yieldAxisDomain.yMax]}
                      ticks={yieldAxisDomain.ticks}
                      stroke="var(--chart-axis, #94a3b8)"
                      tickLine={false}
                      tick={{ fontSize: 12, fill: 'var(--chart-axis, #64748b)', fontFamily: 'var(--font-family)' }}
                      tickFormatter={(v) => `${v}%`}
                      width={45}
                    />
                    <Tooltip content={<ProductionSharedTooltip />} cursor={{ stroke: 'rgba(0, 0, 0, 0.12)', strokeWidth: 1, strokeDasharray: '3 3' }} />
                    <Line
                      type="monotone"
                      dataKey="yield_pct"
                      stroke="var(--brand-teal, #10b981)"
                      strokeWidth={2.2}
                      connectNulls={false}
                      name="Quality Yield"
                      dot={(props) => {
                        const { cx, cy, payload } = props;
                        if (payload?.isLowestYield && cx != null && cy != null) {
                          return (
                            <g key={`lowest-dot-${payload.date}`}>
                              <circle cx={cx} cy={cy} r={5} fill="#ef4444" stroke="#ffffff" strokeWidth={2} />
                              <circle cx={cx} cy={cy} r={8} fill="none" stroke="#ef4444" strokeOpacity={0.4} strokeWidth={2} />
                            </g>
                          );
                        }
                        return null;
                      }}
                      activeDot={{ r: 5, fill: '#10b981', stroke: '#ffffff', strokeWidth: 2 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Legend */}
        <div className="chart-legend-bottom" aria-hidden="true">
          <span className="legend-item">
            <span className="legend-swatch-bar blue" />
            <span>Actual output (units)</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch-line green" />
            <span>Daily yield (%)</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch-dot red" />
            <span>Lowest yield</span>
          </span>
        </div>
      </div>
    </div>
  );
}

export default ExecutiveChartsRow;
