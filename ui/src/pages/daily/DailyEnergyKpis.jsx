import React from 'react';
import { formatCurrency, formatDateTime, formatNumber } from '../../utils/formatters';

export default function DailyEnergyKpis({ energySummary, powerFactorData }) {
  const totalKwh = energySummary ? Number(energySummary.total_consumption_kwh) : null;
  const totalCost = energySummary ? Number(energySummary.total_cost_inr) : null;
  const totalCo2e = energySummary ? Number(energySummary.total_co2e_kg) : null;
  const avgPf = energySummary?.avg_power_factor ? Number(energySummary.avg_power_factor) : null;
  const distinctHours = energySummary?.distinct_hours || 0;
  const totalReadings = energySummary?.total_readings || 0;
  const peak = energySummary?.peak_reading;

  const lowPfEvents = powerFactorData?.low_pf_events_count ?? 0;
  const minPf = powerFactorData?.min_power_factor ? Number(powerFactorData.min_power_factor).toFixed(4) : null;
  const maxPf = powerFactorData?.max_power_factor ? Number(powerFactorData.max_power_factor).toFixed(4) : null;

  const kpis = [
    {
      id: 'daily-kpi-consumption',
      title: 'Total Energy Consumption',
      value: formatNumber(totalKwh, 2),
      unit: 'kWh',
      sublabel: `${distinctHours} operating hours • ${totalReadings} telemetry readings`,
      accent: 'purple',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      ),
    },
    {
      id: 'daily-kpi-cost',
      title: 'Daily Energy Spend',
      value: formatCurrency(totalCost),
      unit: 'INR',
      sublabel: 'Contract tariff ₹8.25 / kWh applied deterministically',
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
      id: 'daily-kpi-co2e',
      title: 'Carbon Emissions',
      value: formatNumber(totalCo2e, 2),
      unit: 'kg CO₂e',
      sublabel: `${(Number(totalCo2e || 0) / 1000).toFixed(2)} MT CO₂e • Dataset emissions factor ~0.716 kg CO₂e/kWh`,
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
      id: 'daily-kpi-pf',
      title: 'Average Power Factor',
      value: avgPf ? avgPf.toFixed(4) : '—',
      unit: 'PF',
      sublabel: minPf && maxPf ? `Min: ${minPf} • Max: ${maxPf} (Configured threshold ≥ 0.90)` : 'Configured threshold ≥ 0.90',
      accent: lowPfEvents > 0 ? 'danger' : 'orange',
      badge: lowPfEvents === 0 ? 'Within configured threshold' : `${lowPfEvents} Under-threshold Events`,
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      ),
    },
  ];

  return (
    <div className="daily-energy-kpis-container">
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
              <div className="kpi-footer-row">
                {card.sublabel && <span className="kpi-sublabel">{card.sublabel}</span>}
                {card.badge && (
                  <span className={`kpi-mini-badge ${lowPfEvents === 0 ? 'status-ok' : 'status-alert'}`}>
                    {card.badge}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {peak && (
        <div className="daily-peak-strip">
          <div className="peak-strip-left">
            <span className="peak-tag">Peak Hourly Energy Consumption</span>
            <span className="peak-info">
              <strong>{formatNumber(peak.consumption_kwh, 2)} kWh</strong> recorded by meter <strong>{peak.meter_id}</strong> ({peak.plant_id}) at <strong>{formatDateTime(peak.timestamp)}</strong>
            </span>
          </div>
          <div className="peak-strip-right">
            <span className="peak-avg-note">
              Daily Average Hourly Consumption: <strong>{formatNumber(energySummary?.avg_hourly_consumption_kwh, 2)} kWh/h</strong>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

