import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';
import KpiCard, { KpiGrid } from '../../components/common/KpiCard';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

export default function ProductionKpis({ summary, summaryAvailable = true, dailyTrend = [] }) {
  const actualQty = summary?.actual_qty ?? null;
  const goodQty = summary?.good_qty ?? null;
  const rejectQty = summary?.reject_qty ?? null;
  const goodRate = summary?.good_rate ?? null;
  const rejectRate = summary?.reject_rate ?? null;
  const reworkQty = summary?.rework_qty ?? null;
  const reworkRate = summary?.rework_rate ?? null;
  const downtimeMin = summary?.downtime_min ?? null;
  const targetQty = summary?.target_qty ?? null;
  const achievementRate = summary?.achievement_rate ?? null;
  const eventCount = summary?.event_count ?? null;
  const balanceValid = summary?.quantity_balance_valid;

  const downtimeHours = downtimeMin !== null && Number.isFinite(Number(downtimeMin))
    ? (Number(downtimeMin) / 60).toFixed(1)
    : null;

  // Real historical trend series if available
  const hasMultipleTrendDays = Array.isArray(dailyTrend) && dailyTrend.length > 1;

  const actualSeries = React.useMemo(() => {
    if (!hasMultipleTrendDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item?.actual_qty)) {
        running += Number(item.actual_qty);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleTrendDays]);

  const goodSeries = React.useMemo(() => {
    if (!hasMultipleTrendDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item?.good_qty)) {
        running += Number(item.good_qty);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleTrendDays]);

  const rejectSeries = React.useMemo(() => {
    if (!hasMultipleTrendDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item?.reject_qty)) {
        running += Number(item.reject_qty);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleTrendDays]);

  const downtimeSeries = React.useMemo(() => {
    if (!hasMultipleTrendDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item?.downtime_min)) {
        running += Number(item.downtime_min);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleTrendDays]);

  // Primary 4 Cards per Desktop Row matching executive reference
  const primaryCards = [
    {
      id: 'kpi-actual',
      title: 'Actual Production',
      value: actualQty !== null ? formatNumber(actualQty) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: actualSeries,
      minimal: true,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
          <line x1="12" y1="22.08" x2="12" y2="12" />
        </svg>
      ),
    },
    {
      id: 'kpi-good',
      title: 'Good Production',
      value: goodQty !== null ? formatNumber(goodQty) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: goodSeries,
      minimal: true,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      ),
    },
    {
      id: 'kpi-reject',
      title: 'Rejected Production',
      value: rejectQty !== null ? formatNumber(rejectQty) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: rejectSeries,
      minimal: true,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      ),
    },
    {
      id: 'kpi-downtime',
      title: 'Production Downtime',
      value: downtimeHours !== null ? `${formatNumber(downtimeHours, 1)}` : 'Unavailable',
      unit: downtimeHours !== null ? 'hrs' : '',
      accent: 'purple',
      sparklineData: downtimeSeries,
      minimal: true,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
      ),
    },
  ];

  return (
    <div className="kpi-overview-container" style={{ marginBottom: '1.5rem' }}>
      {/* 1. Exactly 4 Primary KPI Cards on Desktop */}
      <KpiGrid className="kpi-grid">
        {primaryCards.map((card) => (
          <KpiCard
            key={card.id}
            id={card.id}
            title={card.title}
            value={card.value}
            unit={card.unit}
            accent={card.accent}
            icon={card.icon}
            sparklineData={card.sparklineData}
            minimal={card.minimal}
          />
        ))}
      </KpiGrid>

      {/* 2. Secondary Operational Metrics Strip */}
      <div className="kpi-secondary-grid">
        {/* Secondary 1: Rework Quantity (Separate metric) */}
        <div className="kpi-secondary-item">
          <div className="kpi-secondary-icon blue">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 16H3v5" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Rework Quantity</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {reworkQty !== null ? formatNumber(reworkQty) : '—'}
              </span>
              <span className="kpi-secondary-detail">
                {reworkRate !== null ? `units (${formatPercent(reworkRate)}) · Separate` : 'units'}
              </span>
            </div>
          </div>
        </div>

        {/* Secondary 2: Target Achievement */}
        <div className="kpi-secondary-item">
          <div className="kpi-secondary-icon purple">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 14 14" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Target Achievement</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {achievementRate !== null ? formatPercent(achievementRate) : '—'}
              </span>
              <span className="kpi-secondary-detail">
                {targetQty !== null ? `of ${formatNumber(targetQty)} planned` : 'achievement'}
              </span>
            </div>
          </div>
        </div>

        {/* Secondary 3: Quantity Balance Verification */}
        <div className="kpi-secondary-item">
          <div className={`kpi-secondary-icon ${balanceValid === true ? 'green' : balanceValid === false ? 'orange' : 'navy'}`}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {balanceValid === true ? (
                <polyline points="20 6 9 17 4 12" />
              ) : (
                <>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </>
              )}
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Quantity Balance</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {balanceValid === true ? 'Verified' : balanceValid === false ? 'Mismatch' : '—'}
              </span>
              <span className="kpi-secondary-detail">
                Actual = Good + Reject
              </span>
            </div>
          </div>
        </div>

        {/* Secondary 4: Hourly Logged Events */}
        <div className="kpi-secondary-item">
          <div className="kpi-secondary-icon navy">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
              <path d="M6 6h10" />
              <path d="M6 10h10" />
              <path d="M6 14h6" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Operating Logs</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {eventCount !== null ? formatNumber(eventCount) : '—'}
              </span>
              <span className="kpi-secondary-detail">
                hourly production records
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
