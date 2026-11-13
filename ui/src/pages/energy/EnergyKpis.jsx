import React from 'react';
import { formatCurrency, formatDate, formatNumber } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

export default function EnergyKpis({
  energySummary,
  dailyTrend = [],
  dailyTrendAvailable = false,
  dateRange,
  summaryAvailable = true,
}) {
  const totalKwh = hasNumber(energySummary?.total_consumption_kwh)
    ? Number(energySummary.total_consumption_kwh)
    : null;
  const totalCost = hasNumber(energySummary?.total_cost_inr)
    ? Number(energySummary.total_cost_inr)
    : null;
  const totalCo2e = hasNumber(energySummary?.total_co2e_kg)
    ? Number(energySummary.total_co2e_kg)
    : null;
  const totalReadings = hasNumber(energySummary?.total_readings)
    ? Number(energySummary.total_readings)
    : null;
  const readingCountDescription = totalReadings === null
    ? 'Reading count unavailable'
    : `${formatNumber(totalReadings)} returned meter readings`;
  const avgPf = hasNumber(energySummary?.avg_power_factor)
    ? Number(energySummary.avg_power_factor)
    : null;

  const validDailyRecords = (dailyTrend || []).filter((item) => hasNumber(item?.consumption_kwh));
  const dailyTrendCount = validDailyRecords.length;
  const dailyAvgKwh = dailyTrendAvailable && dailyTrendCount > 0
    ? validDailyRecords.reduce((sum, item) => sum + Number(item.consumption_kwh), 0) / dailyTrendCount
    : null;
  const dailyAverageDescription = !dailyTrendAvailable
    ? 'Unavailable: historical trend data could not be retrieved'
    : dailyTrendCount === 0
      ? 'Unavailable: no daily energy totals were returned'
      : `Historical reference for ${dateRange
        ? `${formatDate(dateRange.start_date)} – ${formatDate(dateRange.end_date)}`
        : 'the returned trend period'}; arithmetic average of ${dailyTrendCount} returned daily totals. Not an expected-energy baseline or normalized for production or operating conditions.`;

  const kpis = [
    {
      id: 'kpi-consumption',
      title: 'Total Energy Consumption',
      value: summaryAvailable && totalKwh !== null ? formatNumber(totalKwh, 2) : 'Unavailable',
      unit: 'kWh',
      sublabel: !summaryAvailable
        ? 'Energy summary request failed'
        : totalKwh === null
          ? 'Energy total unavailable'
          : hasNumber(energySummary?.distinct_hours)
          ? `${readingCountDescription} across ${formatNumber(energySummary.distinct_hours)} distinct hourly timestamps; readings are interval consumption, not cumulative`
          : `${readingCountDescription}; distinct timestamp count unavailable`,
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-cost',
      title: 'Dataset-Calculated Energy Cost',
      value: summaryAvailable && totalCost !== null ? formatCurrency(totalCost) : 'Unavailable',
      unit: 'INR',
      sublabel: !summaryAvailable
        ? 'Energy summary request failed'
        : totalCost === null
          ? 'Cost total unavailable'
        : 'Calculated from the dataset; not verified against a current utility bill or contract',
      accent: 'blue',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 3h12"/>
          <path d="M6 8h12"/>
          <path d="m6 13 8.5 8"/>
          <path d="M6 13h3a4 4 0 0 0 0-8"/>
        </svg>
      ),
    },
    {
      id: 'kpi-co2e',
      title: 'Estimated Carbon Emissions',
      value: summaryAvailable && totalCo2e !== null ? formatNumber(totalCo2e, 2) : 'Unavailable',
      unit: 'kg CO₂e',
      sublabel: !summaryAvailable
        ? 'Energy summary request failed'
        : totalCo2e === null
          ? 'CO₂e estimate unavailable'
        : 'Calculated using a dataset emission factor; not a direct or verified emissions measurement',
      accent: 'cyan',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 12h2a8 8 0 0 1 8 8v2"/>
          <path d="m4.93 4.93 1.41 1.41A8 8 0 0 1 18 12h2"/>
          <path d="M12 2v2a8 8 0 0 1 8 8"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      ),
    },
    {
      id: 'kpi-readings',
      title: 'Returned Meter Readings',
      value: summaryAvailable && totalReadings !== null ? formatNumber(totalReadings) : 'Unavailable',
      unit: 'readings',
      sublabel: summaryAvailable ? 'Count returned by the energy summary API' : 'Energy summary request failed',
      accent: 'navy',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/>
          <path d="M6 6h10"/>
          <path d="M6 10h10"/>
          <path d="M6 14h6"/>
        </svg>
      ),
    },
    {
      id: 'kpi-pf',
      title: 'Average Power Factor',
      value: summaryAvailable && avgPf !== null ? avgPf.toFixed(4) : 'Unavailable',
      unit: 'PF',
      sublabel: !summaryAvailable
        ? 'Energy summary request failed'
        : avgPf === null
          ? 'Power factor average unavailable'
          : 'See power-factor monitoring section for returned threshold details',
      accent: 'orange',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-daily-avg',
      title: 'Average Returned Daily Consumption',
      value: dailyAvgKwh !== null ? formatNumber(dailyAvgKwh, 2) : 'Unavailable',
      unit: 'kWh / day',
      sublabel: dailyAverageDescription,
      accent: 'teal',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
          <line x1="16" y1="2" x2="16" y2="6"/>
          <line x1="8" y1="2" x2="8" y2="6"/>
          <line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
      ),
    },
  ];

  return (
    <div className="kpi-grid">
      {kpis.map((card) => (
        <div key={card.id} className={`kpi-card accent-${card.accent}`}>
          <div className="kpi-card-inner">
            <div className="kpi-header">
              <span className="kpi-title">{card.title}</span>
              <div className="kpi-icon-wrap">{card.icon}</div>
            </div>
            <div className="kpi-body">
              <span className="kpi-value">{card.value}</span>
              {card.unit && <span className="kpi-unit">{card.unit}</span>}
            </div>
            {card.sublabel && <div className="kpi-sublabel">{card.sublabel}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

