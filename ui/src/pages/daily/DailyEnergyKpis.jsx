import React from 'react';
import { formatCurrency, formatDateTime, formatNumber } from '../../utils/formatters';
import KpiCard, { KpiGrid } from '../../components/common/KpiCard';

export default function DailyEnergyKpis({ energySummary, powerFactorData }) {
  const totalReadings = energySummary?.total_readings ?? null;
  const hasEnergyReadingsCount = totalReadings !== null && Number.isFinite(Number(totalReadings));
  const hasEnergyReadings = hasEnergyReadingsCount && Number(totalReadings) > 0;
  const noEnergyReadings = hasEnergyReadingsCount && Number(totalReadings) === 0;
  const totalKwh = hasEnergyReadings && energySummary?.total_consumption_kwh != null
    ? Number(energySummary.total_consumption_kwh)
    : null;
  const totalCost = hasEnergyReadings && energySummary?.total_cost_inr != null
    ? Number(energySummary.total_cost_inr)
    : null;
  const totalCo2e = hasEnergyReadings && energySummary?.total_co2e_kg != null
    ? Number(energySummary.total_co2e_kg)
    : null;
  const avgPf = hasEnergyReadings && energySummary?.avg_power_factor != null
    ? Number(energySummary.avg_power_factor)
    : null;
  const distinctHours = energySummary?.distinct_hours ?? null;
  const peak = energySummary?.peak_reading;

  const pfReadingsCount = powerFactorData?.total_readings;
  const hasPfReadings = pfReadingsCount != null && Number.isFinite(Number(pfReadingsCount))
    && Number(pfReadingsCount) > 0;
  const lowPfEvents = hasPfReadings && powerFactorData?.low_pf_events_count != null
    ? powerFactorData.low_pf_events_count
    : null;
  const minPf = powerFactorData?.min_power_factor != null ? Number(powerFactorData.min_power_factor).toFixed(4) : null;
  const maxPf = powerFactorData?.max_power_factor != null ? Number(powerFactorData.max_power_factor).toFixed(4) : null;

  const kpis = [
    {
      id: 'daily-kpi-consumption',
      title: 'Total Energy Consumption',
      value: formatNumber(totalKwh, 2),
      unit: 'kWh',
      sublabel: noEnergyReadings
        ? 'No energy meter readings returned'
        : hasEnergyReadingsCount
          ? `${formatNumber(distinctHours)} distinct timestamps • ${formatNumber(totalReadings)} meter readings`
          : 'Energy reading count unavailable',
      kind: totalKwh !== null ? 'Calculated' : 'Unavailable',
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
      sublabel: totalCost !== null
        ? 'Dataset tariff ₹8.25 / kWh applied deterministically'
        : hasEnergyReadings ? 'Cost total unavailable' : 'No cost total available without energy readings',
      kind: totalCost !== null ? 'Calculated' : 'Unavailable',
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
      sublabel: totalCo2e !== null
        ? `${(totalCo2e / 1000).toFixed(2)} MT CO₂e • Dataset emissions factor ~0.716 kg CO₂e/kWh`
        : hasEnergyReadings ? 'Emissions estimate unavailable' : 'No emissions total available without energy readings',
      kind: totalCo2e !== null ? 'Calculated' : 'Unavailable',
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
      value: avgPf !== null ? avgPf.toFixed(4) : '—',
      unit: 'PF',
      sublabel: minPf !== null && maxPf !== null ? `Min: ${minPf} • Max: ${maxPf} (Configured threshold ≥ 0.90)` : 'Configured threshold ≥ 0.90',
      accent: lowPfEvents === null ? 'orange' : lowPfEvents > 0 ? 'danger' : 'orange',
      badge: lowPfEvents === null
        ? 'Unavailable'
        : lowPfEvents === 0
          ? 'No readings below threshold'
          : `${lowPfEvents} Under-threshold Events`,
      kind: avgPf !== null ? 'Calculated' : 'Unavailable',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      ),
    },
  ];

  return (
    <div className="daily-energy-kpis-container">
      <KpiGrid className="kpi-grid">
        {kpis.map((card) => (
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

      {peak && (
        <div className="daily-peak-strip">
          <div className="peak-strip-left">
            <span className="peak-tag">Peak Hourly Energy Consumption <span className="daily-value-kind">Measured reading</span></span>
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

