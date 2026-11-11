import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

export default function ProductionKpis({ summary }) {
  const actualQty = summary ? summary.actual_qty : null;
  const goodQty = summary ? summary.good_qty : null;
  const rejectQty = summary ? summary.reject_qty : null;
  const rejectRate = summary ? summary.reject_rate : null;
  const reworkQty = summary ? summary.rework_qty : null;
  const downtimeMin = summary ? summary.downtime_min : null;
  const downtimeHours = downtimeMin !== null ? (downtimeMin / 60).toFixed(1) : null;

  const kpis = [
    {
      id: 'kpi-actual',
      title: 'Actual Production Output',
      value: formatNumber(actualQty),
      unit: 'units',
      sublabel: summary ? `Across ${formatNumber(summary.event_count)} hourly line logs` : null,
      accent: 'navy',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
      ),
    },
    {
      id: 'kpi-good',
      title: 'First-Pass Good Output',
      value: formatNumber(goodQty),
      unit: 'units',
      sublabel: summary ? `${formatPercent(summary.good_rate)} first-pass quality yield` : null,
      accent: 'teal',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
          <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
      ),
    },
    {
      id: 'kpi-reject',
      title: 'Defective / Scrap Output',
      value: formatNumber(rejectQty),
      unit: 'units',
      sublabel: 'Parts failing in-line quality gates',
      accent: 'orange',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
      ),
    },
    {
      id: 'kpi-reject-rate',
      title: 'Defect / Scrap Rate',
      value: formatPercent(rejectRate),
      unit: 'of output',
      sublabel: 'Calculated as reject / actual units',
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="19" y1="5" x2="5" y2="19"/>
          <circle cx="6.5" cy="6.5" r="2.5"/>
          <circle cx="17.5" cy="17.5" r="2.5"/>
        </svg>
      ),
    },
    {
      id: 'kpi-rework',
      title: 'Rework Quantity',
      value: formatNumber(reworkQty),
      unit: 'units',
      sublabel: 'Excluded from finished good counts',
      accent: 'blue',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
          <path d="M21 3v5h-5"/>
          <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
          <path d="M8 16H3v5"/>
        </svg>
      ),
    },
    {
      id: 'kpi-downtime',
      title: 'Line Stoppage Downtime',
      value: formatNumber(downtimeMin),
      unit: 'minutes',
      sublabel: downtimeHours ? `Equivalent to ${formatNumber(downtimeHours, 1)} operating hours` : null,
      accent: 'cyan',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
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
