import React from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

export default function KpiOverview({ energySummary, productionSummary }) {
  const energyKwh = energySummary ? formatNumber(energySummary.total_consumption_kwh, 2) : '—';
  const energyCost = energySummary ? formatCurrency(energySummary.total_cost_inr) : '—';
  const co2e = energySummary ? formatNumber(energySummary.total_co2e_kg, 2) : '—';

  const actualUnits = productionSummary ? formatNumber(productionSummary.actual_qty) : '—';
  const goodUnits = productionSummary ? formatNumber(productionSummary.good_qty) : '—';
  const rejectRate = productionSummary ? formatPercent(productionSummary.reject_rate) : '—';
  const rejectUnits = productionSummary ? formatNumber(productionSummary.reject_qty) : '0';

  const cards = [
    {
      id: 'kpi-energy',
      title: 'Total Energy Consumption',
      value: energyKwh,
      unit: 'kWh',
      sublabel: energySummary ? `${formatNumber(energySummary.total_readings)} meter-hours monitored` : null,
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-cost',
      title: 'Total Energy Spend',
      value: energyCost,
      unit: 'INR',
      sublabel: 'Calculated using time-of-day tariff rates',
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
      value: co2e,
      unit: 'kg CO₂e',
      sublabel: 'Based on 0.716 kg CO₂e/kWh grid factor',
      accent: 'cyan',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/>
          <path d="m9 12 2 2 4-4"/>
        </svg>
      ),
    },
    {
      id: 'kpi-actual',
      title: 'Actual Production Volume',
      value: actualUnits,
      unit: 'Units',
      sublabel: productionSummary ? `Across SMT & Final Assembly lines` : null,
      accent: 'navy',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-good',
      title: 'Good Production Volume',
      value: goodUnits,
      unit: 'Units',
      sublabel: productionSummary ? `${formatPercent(productionSummary.good_rate)} yield rate` : null,
      accent: 'green',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
          <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
      ),
    },
    {
      id: 'kpi-reject',
      title: 'Overall Scrap / Reject Rate',
      value: rejectRate,
      unit: '% of Actual',
      sublabel: `${rejectUnits} defective units isolated`,
      accent: 'orange',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      ),
    },
  ];

  return (
    <div className="kpi-grid">
      {cards.map((card) => (
        <div key={card.id} className={`kpi-card accent-${card.accent}`}>
          <div className="kpi-card-header">
            <span className="kpi-title">{card.title}</span>
            <div className={`kpi-icon-badge ${card.accent}`}>
              {card.icon}
            </div>
          </div>
          <div className="kpi-card-body">
            <div className="kpi-value-row">
              <span className="kpi-value">{card.value}</span>
              <span className="kpi-unit">{card.unit}</span>
            </div>
            {card.sublabel && (
              <div className="kpi-sublabel">{card.sublabel}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

