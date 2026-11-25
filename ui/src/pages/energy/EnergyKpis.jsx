import React, { useMemo } from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';
import KpiCard from '../../components/common/KpiCard';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

function formatTrendPeriod(startDate, endDate) {
  if (!startDate || !endDate) return '';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const sParts = startDate.split('-').map(Number);
  const eParts = endDate.split('-').map(Number);
  if (sParts.length !== 3 || eParts.length !== 3) return '';
  const [sY, sM, sD] = sParts;
  const [eY, eM, eD] = eParts;
  if (sY === eY && sM === eM) {
    const monthName = months[sM - 1] || sM;
    if (sD === eD) {
      return `${monthName} ${sD}, ${sY}`;
    }
    return `${monthName} ${sD} to ${monthName} ${eD}`;
  }
  const sMonth = months[sM - 1] || sM;
  const eMonth = months[eM - 1] || eM;
  return `${sMonth} ${sD} - ${eMonth} ${eD}`;
}

export default function EnergyKpis({
  energySummary,
  powerFactorData,
  dailyTrend = [],
  resolvedDateRange,
  summaryAvailable = true,
  pfAvailable = true,
  dailyTrendAvailable = true,
  selectedShift = 'ALL',
}) {
  const isShiftFiltered = Boolean(selectedShift && selectedShift !== 'ALL');
  const shiftBadge = isShiftFiltered ? { text: `Shift ${selectedShift}`, variant: 'info' } : null;

  // Primary metric extraction
  const totalKwh = summaryAvailable && hasNumber(energySummary?.total_consumption_kwh)
    ? Number(energySummary.total_consumption_kwh)
    : null;

  const totalCost = summaryAvailable && hasNumber(energySummary?.total_cost_inr)
    ? Number(energySummary.total_cost_inr)
    : null;

  const totalCo2e = summaryAvailable && hasNumber(energySummary?.total_co2e_kg)
    ? Number(energySummary.total_co2e_kg)
    : null;

  const totalReadings = summaryAvailable && hasNumber(energySummary?.total_readings)
    ? Number(energySummary.total_readings)
    : null;

  const distinctHours = summaryAvailable && hasNumber(energySummary?.distinct_hours)
    ? Number(energySummary.distinct_hours)
    : null;

  // Power factor values (prefer powerFactorData, fallback to energySummary)
  const avgPf = pfAvailable && hasNumber(powerFactorData?.avg_power_factor)
    ? Number(powerFactorData.avg_power_factor)
    : summaryAvailable && hasNumber(energySummary?.avg_power_factor)
      ? Number(energySummary.avg_power_factor)
      : null;

  const minPf = pfAvailable && hasNumber(powerFactorData?.min_power_factor)
    ? Number(powerFactorData.min_power_factor)
    : null;

  const threshold = pfAvailable && hasNumber(powerFactorData?.threshold)
    ? Number(powerFactorData.threshold)
    : 0.90;

  const lowPfEvents = pfAvailable && hasNumber(powerFactorData?.low_pf_events_count)
    ? Number(powerFactorData.low_pf_events_count)
    : null;

  // Daily trend calculations for sparklines and secondary strip
  const validDailyRecords = (dailyTrend || []).filter((item) => hasNumber(item?.consumption_kwh));
  const dailyRecordCount = validDailyRecords.length;
  const dailyAvgKwh = dailyTrendAvailable && dailyRecordCount > 0
    ? validDailyRecords.reduce((sum, item) => sum + Number(item.consumption_kwh), 0) / dailyRecordCount
    : null;

  // Peak reading info
  const peakReading = energySummary?.peak_reading;
  const peakKwh = hasNumber(peakReading?.consumption_kwh)
    ? Number(peakReading.consumption_kwh)
    : null;

  // Compute trend date range period e.g. "Aug 1 to Oct 31"
  const trendPeriod = useMemo(() => {
    if (!resolvedDateRange) return '';
    return formatTrendPeriod(resolvedDateRange.startDate, resolvedDateRange.endDate);
  }, [resolvedDateRange]);

  const hasMultipleDays = dailyTrendAvailable && Array.isArray(dailyTrend) && dailyTrend.length > 1;

  // Actual cumulative series from historical telemetry
  const energyCumulativeSeries = useMemo(() => {
    if (!hasMultipleDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item.consumption_kwh)) {
        running += Number(item.consumption_kwh);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleDays]);

  const costCumulativeSeries = useMemo(() => {
    if (!hasMultipleDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item.cost_inr)) {
        running += Number(item.cost_inr);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleDays]);

  const co2eCumulativeSeries = useMemo(() => {
    if (!hasMultipleDays) return null;
    let running = 0;
    const series = [];
    dailyTrend.forEach((item) => {
      const co2Val = hasNumber(item.co2e_kg)
        ? Number(item.co2e_kg)
        : hasNumber(item.consumption_kwh)
          ? Number(item.consumption_kwh) * 0.82
          : null;
      if (co2Val !== null) {
        running += co2Val;
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleDays]);

  const pfDailySeries = useMemo(() => {
    if (!hasMultipleDays) return null;
    const series = [];
    dailyTrend.forEach((item) => {
      if (hasNumber(item.avg_power_factor)) {
        series.push(Number(item.avg_power_factor));
      }
    });
    return series.length > 1 ? series : null;
  }, [dailyTrend, hasMultipleDays]);

  // Primary 4 Cards definition matching executive reference
  const primaryCards = [
    {
      id: 'kpi-consumption',
      title: 'Total Energy Consumption',
      value: totalKwh !== null ? formatNumber(totalKwh, 2) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: energyCumulativeSeries,
      minimal: true,
      badge: shiftBadge,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      ),
    },
    {
      id: 'kpi-cost',
      title: 'Energy Cost',
      value: totalCost !== null ? formatCurrency(totalCost) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: costCumulativeSeries,
      minimal: true,
      badge: shiftBadge,
      icon: <span className="kpi-icon-text">₹</span>,
    },
    {
      id: 'kpi-co2e',
      title: 'Estimated Carbon Emissions',
      value: totalCo2e !== null ? formatNumber(totalCo2e, 2) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: co2eCumulativeSeries,
      minimal: true,
      badge: shiftBadge,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      ),
    },
    {
      id: 'kpi-pf',
      title: 'Average Power Factor',
      value: avgPf !== null ? avgPf.toFixed(4) : 'Unavailable',
      unit: '',
      accent: 'purple',
      sparklineData: pfDailySeries,
      minimal: true,
      badge: shiftBadge,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      ),
    },
  ];

  return (
    <div className="kpi-overview-container" style={{ gap: '0.75rem', marginBottom: '0.5rem' }}>
      {/* 1. Exactly 4 Primary KPI Cards */}
      <div className="kpi-grid">
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
            badge={card.badge}
          />
        ))}
      </div>

      {/* 2. Secondary Operational Metrics Strip */}
      <div className="kpi-secondary-grid">
        {/* Metric 1: Returned Meter Readings */}
        <div className="kpi-secondary-item">
          <div className="kpi-secondary-icon navy">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
              <path d="M6 6h10" />
              <path d="M6 10h10" />
              <path d="M6 14h6" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Returned Readings</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {totalReadings !== null ? formatNumber(totalReadings) : '—'}
              </span>
              <span className="kpi-secondary-detail">
                {distinctHours !== null ? `· ${formatNumber(distinctHours)} active hours${isShiftFiltered ? ` (Shift ${selectedShift})` : ''}` : 'readings'}
              </span>
            </div>
          </div>
        </div>

        {/* Metric 2: Daily Average Consumption */}
        <div className="kpi-secondary-item">
          <div className="kpi-secondary-icon purple">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Daily Average Load</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {dailyAvgKwh !== null ? `${formatNumber(dailyAvgKwh, 1)}` : '—'}
              </span>
              <span className="kpi-secondary-detail">
                {dailyRecordCount > 0 ? `kWh/d (${dailyRecordCount}d${isShiftFiltered ? ` • Shift ${selectedShift}` : ''})` : 'kWh/day'}
              </span>
            </div>
          </div>
        </div>

        {/* Metric 3: Minimum Observed PF */}
        <div className="kpi-secondary-item">
          <div className="kpi-secondary-icon orange">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 17 13.5 8.5 8.5 13.5 2 7" />
              <polyline points="16 17 22 17 22 11" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Minimum Power Factor</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {minPf !== null ? minPf.toFixed(4) : '—'}
              </span>
              <span className="kpi-secondary-detail">
                {minPf !== null && threshold
                  ? minPf >= threshold
                    ? `Compliant (≥ ${threshold.toFixed(2)})`
                    : `Deficit: ${(threshold - minPf).toFixed(4)}`
                  : `Threshold: ${threshold.toFixed(2)}`}
              </span>
            </div>
          </div>
        </div>

        {/* Metric 4: Peak Hourly Consumption */}
        <div
          className="kpi-secondary-item"
          title={peakReading?.scope_description || 'Maximum individual meter-hour reading in kWh. Supplied demand_kw is derived (0.92 × kWh); measured peak kW is unavailable.'}
        >
          <div className="kpi-secondary-icon blue">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
              <polyline points="17 6 23 6 23 12" />
            </svg>
          </div>
          <div className="kpi-secondary-info">
            <span className="kpi-secondary-label">Peak Hourly Consumption{isShiftFiltered ? ` (Shift ${selectedShift})` : ''}</span>
            <div className="kpi-secondary-val-row">
              <span className="kpi-secondary-val">
                {peakKwh !== null
                  ? `${formatNumber(peakKwh, 1)}`
                  : hasNumber(energySummary?.avg_hourly_consumption_kwh)
                    ? `${formatNumber(energySummary.avg_hourly_consumption_kwh, 1)}`
                    : '—'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
