import React from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

export default function KpiOverview({
  energySummary,
  productionSummary,
  energyAvailable = true,
  productionAvailable = true,
}) {
  const energyKwh = energyAvailable && hasNumber(energySummary?.total_consumption_kwh)
    ? formatNumber(energySummary.total_consumption_kwh, 2)
    : 'Unavailable';
  const energyCost = energyAvailable && hasNumber(energySummary?.total_cost_inr)
    ? formatCurrency(energySummary.total_cost_inr)
    : 'Unavailable';
  const co2e = energyAvailable && hasNumber(energySummary?.total_co2e_kg)
    ? formatNumber(energySummary.total_co2e_kg, 2)
    : 'Unavailable';
  const actualUnits = productionAvailable && hasNumber(productionSummary?.actual_qty)
    ? formatNumber(productionSummary.actual_qty)
    : 'Unavailable';
  const goodUnits = productionAvailable && hasNumber(productionSummary?.good_qty)
    ? formatNumber(productionSummary.good_qty)
    : 'Unavailable';
  const rejectRate = productionAvailable && hasNumber(productionSummary?.reject_rate)
    ? formatPercent(productionSummary.reject_rate)
    : 'Unavailable';
  const rejectUnits = productionAvailable && hasNumber(productionSummary?.reject_qty)
    ? formatNumber(productionSummary.reject_qty)
    : 'Unavailable';

  const cards = [
    {
      id: 'kpi-energy',
      title: 'Total Energy Consumption',
      value: energyKwh,
      unit: 'kWh',
      sublabel: !energyAvailable
        ? 'Energy summary request failed'
        : hasNumber(energySummary?.total_readings)
          ? `${formatNumber(energySummary.total_readings)} returned energy-meter readings`
          : 'Energy reading count unavailable',
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-cost',
      title: 'Calculated Energy Cost',
      value: energyCost,
      unit: 'INR',
      sublabel: energyCost === 'Unavailable'
        ? 'Cost total unavailable'
        : 'Dataset-calculated; not a verified utility bill',
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
      sublabel: co2e === 'Unavailable'
        ? 'Emissions estimate unavailable'
        : 'Calculated CO₂e estimate; not a direct emissions measurement',
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
      title: 'Recorded Production Quantity',
      value: actualUnits,
      unit: 'units',
      sublabel: !productionAvailable
        ? 'Production summary request failed'
        : actualUnits === 'Unavailable'
          ? 'Actual quantity unavailable'
          : 'Summed across returned lines; SMT boards and final-assembly phones are different scopes',
      accent: 'navy',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      ),
    },
    {
      id: 'kpi-good',
      title: 'Recorded Good Quantity',
      value: goodUnits,
      unit: 'units',
      sublabel: !productionAvailable
        ? 'Production summary request failed'
        : !hasNumber(productionSummary?.good_rate)
          ? 'First-pass yield unavailable'
          : `${formatPercent(productionSummary.good_rate)} API-reported aggregate yield; production scopes differ`,
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
      title: 'Aggregate Rejected Output Rate',
      value: rejectRate,
      unit: 'of actual output',
      sublabel: rejectUnits === 'Unavailable'
        ? 'Rejected quantity unavailable'
        : `${rejectUnits} rejected units across returned production scopes`,
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

