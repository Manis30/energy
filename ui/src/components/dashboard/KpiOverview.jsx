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
  selectedPlant = 'ALL',
  selectedShift = 'ALL',
  energyAvailable = true,
  productionAvailable = true,
  factoryEnergyAvailable = true,
  loading = false,
}) {
  const isShiftFiltered = selectedShift && selectedShift !== 'ALL';
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

  // Primary 4 Cards matching reference
  const primaryCards = [
    {
      id: 'kpi-energy',
      title: 'Total Energy Consumption',
      value: energyKwh,
      unit: 'kWh',
      accent: 'purple',
      sparklineData: energySeries,
    },
    {
      id: 'kpi-cost',
      title: 'Energy Cost',
      value: energyCost,
      unit: '₹',
      accent: 'purple',
      sparklineData: costSeries,
    },
    {
      id: 'kpi-co2e',
      title: 'Carbon Emissions',
      value: co2e,
      unit: 'kg CO₂e',
      accent: 'purple',
      sparklineData: co2eSeries,
    },
    {
      id: 'kpi-production',
      title: 'Production Output',
      value: actualUnits,
      unit: 'units',
      accent: 'purple',
      sparklineData: prodSeries,
    },
  ];

  // Headline Management Cards (Per Good Finished Unit)
  const managementCards = [
    {
      id: 'kpi-elec-intensity',
      title: 'Electricity Intensity',
      value: electricityIntensity,
      unit: 'kWh / good unit',
      accent: 'purple',
      secondary: isShiftFiltered ? 'Facility total / unallocated to shift' : null,
      badge: isShiftFiltered ? { text: 'Facility total', variant: 'info' } : null,
    },
    {
      id: 'kpi-cost-intensity',
      title: 'Estimated Cost Intensity',
      value: costIntensity,
      unit: '/ good unit',
      accent: 'purple',
      secondary: isShiftFiltered ? 'Facility total / unallocated to shift' : null,
      badge: isShiftFiltered ? { text: 'Facility total', variant: 'info' } : null,
    },
    {
      id: 'kpi-emissions-intensity',
      title: 'Estimated Emissions Intensity',
      value: emissionsIntensity,
      unit: 'kg CO₂e / good unit',
      accent: 'purple',
      secondary: isShiftFiltered ? 'Facility total / unallocated to shift' : null,
      badge: isShiftFiltered ? { text: 'Facility total', variant: 'info' } : null,
    },
    {
      id: 'kpi-good-output',
      title: 'Good Finished Output',
      value: goodFinishedOutput,
      unit: 'units',
      accent: 'purple',
    },
  ];

  return (
    <div className="kpi-overview-container">
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
            accent={card.accent}
            secondary={card.secondary}
            badge={card.badge}
            loading={loading}
          />
        ))}
      </KpiGrid>

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
            sparklineData={card.sparklineData}
            loading={loading}
          />
        ))}
      </KpiGrid>
    </div>
  );
}
