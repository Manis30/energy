import React from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

export default function EnergyKpis({ energySummary, dailyTrendCount = 92 }) {
  const totalKwh = energySummary ? Number(energySummary.total_consumption_kwh) : null;
  const totalCost = energySummary ? Number(energySummary.total_cost_inr) : null;
  const totalCo2e = energySummary ? Number(energySummary.total_co2e_kg) : null;
  const totalReadings = energySummary ? energySummary.total_readings : null;
  const avgPf = energySummary?.avg_power_factor ? Number(energySummary.avg_power_factor) : null;

  // Calculate daily average consumption
  const dailyAvgKwh = totalKwh && dailyTrendCount > 0 ? totalKwh / dailyTrendCount : null;

  const kpis = [
    {
      id: 'kpi-consumption',
      title: 'Total Energy Consumption',
      value: formatNumber(totalKwh, 2),
      unit: 'kWh',
      sublabel: energySummary ? `${formatNumber(energySummary.distinct_hours)} operating hours logged` : null,
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-cost',
      title: 'Total Energy Cost',
      value: formatCurrency(totalCost),
      unit: 'INR',
      sublabel: 'Fixed tariff of ₹8.25 / kWh from contract',
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
      title: 'Total Carbon Emissions',
      value: formatNumber(totalCo2e, 2),
      unit: 'kg CO₂e',
      sublabel: 'Grid factor: 0.716 kg CO₂e / kWh',
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
      title: 'Total Meter Readings',
      value: formatNumber(totalReadings),
      unit: 'readings',
      sublabel: '5 submeters monitored continuously',
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
      value: avgPf ? avgPf.toFixed(4) : '—',
      unit: 'PF',
      sublabel: 'Regulatory limit ≥ 0.90 (100% compliant)',
      accent: 'orange',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-daily-avg',
      title: 'Daily Average Consumption',
      value: formatNumber(dailyAvgKwh, 2),
      unit: 'kWh / day',
      sublabel: `Averaged across ${dailyTrendCount} monitored days`,
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

