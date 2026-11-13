import React from 'react';
import { formatNumber } from '../../utils/formatters';

export default function AnomalyKpis({ data }) {
  const totalAnomalies = data ? data.total_anomalies_detected : null;
  const statAnomalies = data?.statistical_zscore?.anomalies || [];
  const rollAnomalies = data?.rolling_baseline?.anomalies || [];
  const standbyData = data?.zero_production_standby;
  const lpfData = data?.low_power_factor;

  // Calculate actual severity breakdown from returned detector records
  let criticalCount = 0;
  let highCount = 0;
  let mediumCount = 0;

  [...statAnomalies, ...rollAnomalies].forEach((a) => {
    if (a.severity === 'CRITICAL') criticalCount++;
    else if (a.severity === 'HIGH') highCount++;
    else if (a.severity === 'MEDIUM') mediumCount++;
  });

  const lowPfCount = lpfData ? lpfData.total_anomalies_detected : 0;
  const standbyKwh = standbyData ? Number(standbyData.total_standby_energy_kwh) : null;
  const standbyHours = standbyData ? (standbyData.total_stoppage_minutes / 60).toFixed(0) : null;

  const kpis = [
    {
      id: 'kpi-total-anom',
      title: 'Total Flagged Exceptions',
      value: formatNumber(totalAnomalies),
      unit: 'events',
      sublabel: 'Across 4 deterministic detection modules',
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 20V10"/>
          <path d="M12 20V4"/>
          <path d="M6 20v-6"/>
        </svg>
      ),
    },
    {
      id: 'kpi-critical',
      title: 'Critical Deviations',
      value: formatNumber(criticalCount),
      unit: 'records',
      sublabel: '|Z| ≥ 4.0σ extreme consumption shifts',
      accent: 'danger',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      ),
    },
    {
      id: 'kpi-high',
      title: 'High-Severity Deviations',
      value: formatNumber(highCount),
      unit: 'records',
      sublabel: '3.0σ ≤ |Z| < 4.0σ statistical outliers',
      accent: 'orange',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      ),
    },
    {
      id: 'kpi-medium',
      title: 'Medium-Severity Deviations',
      value: formatNumber(mediumCount),
      unit: 'records',
      sublabel: 'Threshold 3.0σ filter applied',
      accent: 'blue',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
      ),
    },
    {
      id: 'kpi-lpf',
      title: 'Power Factor Exceptions',
      value: formatNumber(lowPfCount),
      unit: 'readings',
      sublabel: lowPfCount === 0 ? 'Zero readings below 0.90 cutoff' : `${formatNumber(lowPfCount)} readings below 0.90 cutoff`,
      accent: lowPfCount === 0 ? 'teal' : 'danger',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
          <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
      ),
    },
    {
      id: 'kpi-standby',
      title: 'Zero-Production Standby Energy',
      value: formatNumber(standbyKwh, 2),
      unit: 'kWh',
      sublabel: standbyHours ? `Observed across ${standbyHours} stoppage hours` : null,
      accent: 'navy',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
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

