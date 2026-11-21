import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';
import KpiCard, { KpiGrid } from '../../components/common/KpiCard';

export default function DailyProductionSection({ productionSummary }) {
  const actualQty = productionSummary ? productionSummary.actual_qty : null;
  const goodQty = productionSummary ? productionSummary.good_qty : null;
  const rejectQty = productionSummary ? productionSummary.reject_qty : null;
  const reworkQty = productionSummary ? productionSummary.rework_qty : null;
  const downtimeMin = productionSummary ? productionSummary.downtime_min : null;
  const rejectRate = productionSummary ? productionSummary.reject_rate : null;
  const goodRate = productionSummary ? productionSummary.good_rate : null;
  const reworkRate = productionSummary ? productionSummary.rework_rate : null;
  const eventCount = productionSummary ? productionSummary.event_count : null;

  const downtimeHours = downtimeMin != null && Number.isFinite(Number(downtimeMin))
    ? (Number(downtimeMin) / 60).toFixed(1)
    : null;

  const cards = [
    {
      id: 'prod-actual',
      title: 'Actual Production Output',
      value: formatNumber(actualQty),
      unit: 'units',
      sublabel: eventCount != null
        ? `${formatNumber(eventCount)} line production batches logged`
        : 'Production event count unavailable',
      kind: actualQty != null ? 'Calculated' : 'Unavailable',
      accent: 'purple',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2"/>
          <path d="M3 9h18"/>
          <path d="M9 21V9"/>
        </svg>
      ),
    },
    {
      id: 'prod-good',
      title: 'Good Production Output',
      value: formatNumber(goodQty),
      unit: 'units',
      sublabel: `Quality First-Pass Yield: ${goodRate != null ? formatPercent(goodRate) : '—'}`,
      kind: goodQty != null ? 'Calculated' : 'Unavailable',
      accent: 'teal',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
          <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
      ),
    },
    {
      id: 'prod-reject',
      title: 'Scrap Rejections',
      value: formatNumber(rejectQty),
      unit: 'units',
      sublabel: `Scrap Rate: ${rejectRate != null ? formatPercent(rejectRate) : '—'} of actual output`,
      kind: rejectQty != null ? 'Calculated' : 'Unavailable',
      accent: 'danger',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
      ),
    },
    {
      id: 'prod-rework',
      title: 'Rework Units',
      value: formatNumber(reworkQty),
      unit: 'units',
      sublabel: `Rework Rate: ${reworkRate != null ? formatPercent(reworkRate) : '—'} • Segregated from scrap`,
      kind: reworkQty != null ? 'Calculated' : 'Unavailable',
      accent: 'orange',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
          <path d="M16 21h5v-5"/>
        </svg>
      ),
    },
    {
      id: 'prod-downtime',
      title: 'Total Line Downtime',
      value: formatNumber(downtimeMin),
      unit: 'minutes',
      sublabel: downtimeHours !== null
        ? `${downtimeHours} cumulative stoppage hours across lines`
        : 'Downtime total unavailable',
      kind: downtimeMin != null ? 'Calculated' : 'Unavailable',
      accent: 'navy',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
      ),
    },
  ];

  return (
    <div className="dashboard-section daily-production-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Production Performance</h3>
          <p className="section-desc">
            Aggregated production events, calculated quality rates, rework volume, and reported line downtime.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">
            {actualQty != null ? `${formatNumber(actualQty)} Units Manufactured` : 'Production output unavailable'}
          </span>
        </div>
      </div>

      <KpiGrid className="daily-production-grid">
        {cards.map((card) => (
          <KpiCard
            key={card.id}
            id={card.id}
            title={card.title}
            value={card.value}
            unit={card.unit}
            accent="purple"
            icon={card.icon}
            minimal={true}
          />
        ))}
      </KpiGrid>

      {/* Engineering Integrity Notice — OEE and Adherence Disclaimer */}
      <div className="daily-disclaimer-box oee-disclaimer">
        <div className="disclaimer-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="16" x2="12" y2="12"/>
            <line x1="12" y1="8" x2="12.01" y2="8"/>
          </svg>
        </div>
        <div className="disclaimer-content">
          <h4 className="disclaimer-title">Operational Data Governance Notice</h4>
          <p className="disclaimer-text">
            Standard Overall Equipment Effectiveness (OEE per ISO 22400) and target adherence are intentionally disclaimed as unavailable. 
            Source manufacturing datasets do not establish explicit Planned Production Time (scheduled shifts vs unscheduled maintenance), 
            and hourly quota values represent gross machine capacities rather than net operational targets. 
            In accordance with platform data integrity guidelines, rework units are segregated from scrap rejects to prevent yield distortion.
          </p>
        </div>
      </div>
    </div>
  );
}
