import React from 'react';
import { formatCurrency, formatNumber } from '../../utils/formatters';
import KpiCard, { KpiGrid } from '../common/KpiCard';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

export default function KpiOverview({
  energySummary,
  productionSummary,
  factoryEnergy,
  energyTrend,
  productionTrend,
  resolvedDateRange,
  energyAvailable = true,
  productionAvailable = true,
  factoryEnergyAvailable = true,
  loading = false,
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
    ? formatNumber(productionSummary.actual_qty, 0)
    : 'Unavailable';

  // Phase 2 Headline Management Metrics (per Good Finished Unit)
  const isFactoryAvailable = factoryEnergyAvailable && factoryEnergy !== null;
  const electricityIntensity = isFactoryAvailable && hasNumber(factoryEnergy?.electricity_intensity_kwh_per_good_unit)
    ? formatNumber(factoryEnergy.electricity_intensity_kwh_per_good_unit, 4)
    : 'Unavailable';

  const costIntensity = isFactoryAvailable && hasNumber(factoryEnergy?.cost_intensity_inr_per_good_unit)
    ? formatCurrency(factoryEnergy.cost_intensity_inr_per_good_unit)
    : 'Unavailable';

  const emissionsIntensity = isFactoryAvailable && hasNumber(factoryEnergy?.emissions_intensity_co2e_per_good_unit)
    ? formatNumber(factoryEnergy.emissions_intensity_co2e_per_good_unit, 4)
    : 'Unavailable';

  const goodFinishedOutput = isFactoryAvailable && hasNumber(factoryEnergy?.final_assembly_good_output)
    ? formatNumber(factoryEnergy.final_assembly_good_output, 0)
    : 'Unavailable';

  const actualSec = isFactoryAvailable && hasNumber(factoryEnergy?.factory_sec_kwh_per_finished_unit)
    ? formatNumber(factoryEnergy.factory_sec_kwh_per_finished_unit, 4)
    : 'Unavailable';

  const coverageStatus = factoryEnergy?.coverage?.coverage_status || 'UNKNOWN';
  const coveragePct = hasNumber(factoryEnergy?.coverage?.coverage_percentage)
    ? Number(factoryEnergy.coverage.coverage_percentage).toFixed(1)
    : '0.0';
  const completeHours = factoryEnergy?.coverage?.complete_matched_hours ?? 0;
  const expectedHours = factoryEnergy?.coverage?.expected_plant_hours ?? 0;

  const yieldPct = hasNumber(factoryEnergy?.production_context?.fal_yield_pct)
    ? `${Number(factoryEnergy.production_context.fal_yield_pct).toFixed(2)}%`
    : null;
  const rejectQty = hasNumber(factoryEnergy?.production_context?.fal_reject_qty)
    ? formatNumber(factoryEnergy.production_context.fal_reject_qty, 0)
    : null;
  const downtimeMin = hasNumber(factoryEnergy?.production_context?.fal_downtime_line_minutes)
    ? formatNumber(factoryEnergy.production_context.fal_downtime_line_minutes, 0)
    : null;

  const hasMultipleEnergyDays = Array.isArray(energyTrend) && energyTrend.length > 1;
  const hasMultipleProdDays = Array.isArray(productionTrend) && productionTrend.length > 1;

  const energySeries = React.useMemo(() => {
    if (!hasMultipleEnergyDays) return null;
    let running = 0;
    const series = [];
    energyTrend.forEach((item) => {
      if (hasNumber(item?.consumption_kwh)) {
        running += Number(item.consumption_kwh);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [energyTrend, hasMultipleEnergyDays]);

  const costSeries = React.useMemo(() => {
    if (!hasMultipleEnergyDays) return null;
    let running = 0;
    const series = [];
    energyTrend.forEach((item) => {
      if (hasNumber(item?.cost_inr)) {
        running += Number(item.cost_inr);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [energyTrend, hasMultipleEnergyDays]);

  const co2eSeries = React.useMemo(() => {
    if (!hasMultipleEnergyDays) return null;
    let running = 0;
    const series = [];
    energyTrend.forEach((item) => {
      const co2 = hasNumber(item?.co2e_kg)
        ? Number(item.co2e_kg)
        : hasNumber(item?.consumption_kwh)
          ? Number(item.consumption_kwh) * 0.82
          : null;
      if (co2 !== null) {
        running += co2;
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [energyTrend, hasMultipleEnergyDays]);

  const prodSeries = React.useMemo(() => {
    if (!hasMultipleProdDays) return null;
    let running = 0;
    const series = [];
    productionTrend.forEach((item) => {
      if (hasNumber(item?.actual_qty)) {
        running += Number(item.actual_qty);
        series.push(running);
      }
    });
    return series.length > 1 ? series : null;
  }, [productionTrend, hasMultipleProdDays]);

  // Primary 4 Cards matching reference: media_1794921119081_6e3161cd.png
  const primaryCards = [
    {
      id: 'kpi-energy',
      title: 'Total Energy Consumption',
      value: energyKwh,
      unit: '',
      accent: 'purple',
      sparklineData: energySeries,
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      ),
    },
    {
      id: 'kpi-cost',
      title: 'Energy Cost',
      value: energyCost,
      unit: '',
      accent: 'purple',
      sparklineData: costSeries,
      icon: <span className="kpi-icon-text">₹</span>,
    },
    {
      id: 'kpi-co2e',
      title: 'Carbon Emissions',
      value: co2e,
      unit: '',
      accent: 'purple',
      sparklineData: co2eSeries,
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      ),
    },
    {
      id: 'kpi-production',
      title: 'Production Output',
      value: actualUnits,
      unit: '',
      accent: 'purple',
      sparklineData: prodSeries,
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
        </svg>
      ),
    },
  ];

  // Headline Management Cards (Per Good Finished Unit)
  const managementCards = [
    {
      id: 'kpi-elec-intensity',
      title: 'Electricity Intensity',
      value: electricityIntensity,
      unit: 'kWh / good unit',
      secondary: `Plant Energy / Good Output • Actual SEC: ${actualSec} kWh/unit`,
      accent: 'purple',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      ),
    },
    {
      id: 'kpi-cost-intensity',
      title: 'Estimated Cost Intensity',
      value: costIntensity,
      unit: '/ good unit',
      secondary: 'Dataset-derived tariff (₹8.25/kWh)',
      accent: 'blue',
      icon: <span className="kpi-icon-text">₹</span>,
    },
    {
      id: 'kpi-emissions-intensity',
      title: 'Estimated Emissions Intensity',
      value: emissionsIntensity,
      unit: 'kg CO₂e / good unit',
      secondary: 'Grid factor assumption (0.716 kg/kWh)',
      accent: 'teal',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      ),
    },
    {
      id: 'kpi-good-output',
      title: 'Good Finished Output',
      value: goodFinishedOutput,
      unit: 'units',
      secondary: yieldPct ? `Yield: ${yieldPct}${rejectQty ? ` • Scrap: ${rejectQty}` : ''}` : 'FAL finished goods gate',
      accent: 'green',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
        </svg>
      ),
    },
  ];

  return (
    <div className="kpi-overview-container">
      {/* Management Headline Banner & Coverage */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '-0.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'none', letterSpacing: 'normal', color: 'var(--text-primary, #0f172a)' }}>
            Management energy intelligence
          </span>
          <span style={{ color: 'var(--text-muted, #94a3b8)', fontSize: '12px' }}>•</span>
          <span style={{ fontSize: '12px', fontWeight: 400, color: 'var(--text-secondary, #64748b)' }}>
            Denominator: Good finished units (FAL gate)
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              padding: '0.15rem 0.5rem',
              borderRadius: '9999px',
              fontSize: '12px',
              fontWeight: 500,
              backgroundColor: coverageStatus === 'FULL' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(234, 179, 8, 0.15)',
              color: coverageStatus === 'FULL' ? '#22c55e' : '#eab308',
              border: `1px solid ${coverageStatus === 'FULL' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`,
            }}
          >
            ● Coverage: {coverageStatus} ({coveragePct}% • {completeHours}/{expectedHours} plant-hrs)
          </span>
        </div>
      </div>

      {/* 1. Headline Intensity Cards */}
      <KpiGrid className="kpi-grid intensity-kpi-grid">
        {managementCards.map((card) => (
          <KpiCard
            key={card.id}
            id={card.id}
            className="intensity-kpi-card"
            title={card.title}
            value={card.value}
            unit={card.unit}
            secondary={card.secondary}
            accent={card.accent}
            icon={card.icon}
            loading={loading}
          />
        ))}
      </KpiGrid>

      {/* Sub-header for Full Scope Totals */}
      <div style={{ display: 'flex', alignItems: 'center', marginTop: '0.25rem', marginBottom: '-0.25rem' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'none', letterSpacing: 'normal', color: 'var(--text-tertiary, #64748b)' }}>
          Factory full-scope totals (all telemetry observations)
        </span>
      </div>

      {/* 2. Full Scope Totals Cards */}
      <KpiGrid className="kpi-grid totals-kpi-grid">
        {primaryCards.map((card) => (
          <KpiCard
            key={card.id}
            id={card.id}
            className="totals-kpi-card"
            title={card.title}
            value={card.value}
            unit={card.unit}
            accent={card.accent}
            icon={card.icon}
            sparklineData={card.sparklineData}
            loading={loading}
          />
        ))}
      </KpiGrid>
    </div>
  );
}
