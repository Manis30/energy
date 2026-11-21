import React, { useEffect, useRef, useState } from 'react';
import { energyApi, energyIntensityApi, productionApi } from '../../services';
import { formatDate, formatNumber } from '../../utils/formatters';
import './EnergyPerformanceComparison.css';

const isNonNegativeNumber = (value) => value !== null
  && value !== undefined
  && !(typeof value === 'string' && value.trim() === '')
  && Number.isFinite(Number(value))
  && Number(value) >= 0;

const isFiniteNumber = (value) => value !== null
  && value !== undefined
  && !(typeof value === 'string' && value.trim() === '')
  && Number.isFinite(Number(value));

const meterKey = (meter) => `${meter?.meter_id || ''}::${meter?.area || ''}`;

const valueOrUnavailable = (value, decimals = 2, unit = '') => (
  isNonNegativeNumber(value)
    ? `${formatNumber(value, decimals)}${unit ? ` ${unit}` : ''}`
    : 'Unavailable'
);

function getProcessMetrics(area, meterId, processEnergy, processAvailable) {
  const isSmt = area === 'SMT' || meterId === 'MTR-SMT';
  const isFal = area === 'FAL' || meterId === 'MTR-FAL';
  const isUtility = ['COMPRESSOR', 'CHILLER', 'HVAC'].includes(area)
    || ['MTR-COMPRESSOR', 'MTR-CHILLER', 'MTR-HVAC'].includes(meterId);

  if (isUtility) {
    return { production: 'Not allocated', intensity: 'Not allocated' };
  }
  if (!isSmt && !isFal) {
    return { production: 'No matched production scope', intensity: 'Unavailable' };
  }
  if (!processAvailable) {
    return { production: 'Unavailable', intensity: 'Unavailable' };
  }

  const summary = isSmt ? processEnergy?.smt_summary : processEnergy?.fal_summary;
  const actualQty = summary?.actual_units ?? summary?.total_actual_qty;
  const goodQty = summary?.good_units ?? summary?.total_good_qty;
  const unitLabel = isSmt ? 'boards' : 'assembly units';
  const secActual = summary?.kwh_per_actual_unit ?? (isSmt ? summary?.overall_process_sec_kwh_per_board : summary?.overall_process_sec_kwh_per_phone);
  const secGood = summary?.kwh_per_good_unit ?? (isSmt ? summary?.overall_process_sec_good_kwh_per_board : summary?.overall_process_sec_good_kwh_per_assembly_unit);

  const prodText = isNonNegativeNumber(goodQty)
    ? `${formatNumber(goodQty, 0)} good ${unitLabel}${isNonNegativeNumber(actualQty) ? ` (${formatNumber(actualQty, 0)} actual)` : ''}`
    : isNonNegativeNumber(actualQty)
    ? `${formatNumber(actualQty, 0)} ${unitLabel}`
    : 'Unavailable';

  const intensityText = isNonNegativeNumber(secGood)
    ? `${formatNumber(secGood, 4)} kWh/good ${unitLabel}${isNonNegativeNumber(secActual) ? ` · ${formatNumber(secActual, 4)} kWh/actual` : ''}`
    : isNonNegativeNumber(secActual)
    ? `${formatNumber(secActual, 4)} kWh/actual ${unitLabel}`
    : 'Unavailable';

  return {
    production: prodText,
    intensity: intensityText,
  };
}

function assignRanks(items, getValue, canRank) {
  if (!canRank || items.length < 2 || !items.every((item) => isNonNegativeNumber(getValue(item)))) {
    return new Map();
  }

  const sortedItems = [...items].sort(
    (left, right) => Number(getValue(right)) - Number(getValue(left))
  );
  const ranks = new Map();
  let rank = 0;
  let previousValue = null;
  sortedItems.forEach((item) => {
    const value = Number(getValue(item));
    if (previousValue === null || value !== previousValue) {
      rank += 1;
      previousValue = value;
    }
    ranks.set(item, rank);
  });
  return ranks;
}

function ComparisonTableState({ available, count, label, loading }) {
  if (loading) {
    return <p className="energy-comparison-state" role="status" aria-live="polite">Loading {label} comparison data…</p>;
  }
  if (!available) {
    return <p className="energy-comparison-state">Unavailable: no usable {label} data was returned.</p>;
  }
  if (count === 0) {
    return <p className="energy-comparison-state">No {label} records were returned.</p>;
  }
  return null;
}

export default function EnergyPerformanceComparison({
  selectedPlant,
  dateRange,
  refreshToken,
}) {
  const [plantRows, setPlantRows] = useState([]);
  const [plantStatus, setPlantStatus] = useState('loading');
  const [plantError, setPlantError] = useState('');
  const [plantDiscoveryPartial, setPlantDiscoveryPartial] = useState(false);
  const [scopeProcessEnergy, setScopeProcessEnergy] = useState(null);
  const [scopeProcessAvailable, setScopeProcessAvailable] = useState(false);
  const [scopeAreas, setScopeAreas] = useState([]);
  const [scopeMeters, setScopeMeters] = useState([]);
  const [scopeDataLoading, setScopeDataLoading] = useState(false);
  const [scopeAreaAvailable, setScopeAreaAvailable] = useState(false);
  const [scopeMeterAvailable, setScopeMeterAvailable] = useState(false);
  const [selectedMeterKey, setSelectedMeterKey] = useState(null);
  const requestId = useRef(0);

  const startDate = dateRange?.start_date;
  const endDate = dateRange?.end_date;
  const hasReportingPeriod = Boolean(startDate && endDate);

  useEffect(() => {
    const currentRequestId = ++requestId.current;
    setPlantRows([]);
    setPlantError('');
    setPlantDiscoveryPartial(false);
    setScopeProcessEnergy(null);
    setScopeProcessAvailable(false);
    setScopeAreas([]);
    setScopeMeters([]);
    setScopeDataLoading(true);
    setScopeAreaAvailable(false);
    setScopeMeterAvailable(false);
    setSelectedMeterKey(null);

    const periodParams = hasReportingPeriod
      ? { start_date: startDate, end_date: endDate }
      : {};
    const scopeParams = {
      ...periodParams,
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
    };

    const loadScopeData = async () => {
      const [scopeProcessResult, areaResult, meterResult] = await Promise.allSettled([
        energyIntensityApi.getProcessEnergy(scopeParams),
        energyApi.getByArea(scopeParams),
        energyApi.getByMeter(scopeParams),
      ]);
      if (currentRequestId !== requestId.current) return;
      if (scopeProcessResult.status === 'fulfilled') {
        setScopeProcessEnergy(scopeProcessResult.value);
        setScopeProcessAvailable(true);
      }
      if (areaResult.status === 'fulfilled' && Array.isArray(areaResult.value)) {
        setScopeAreas(areaResult.value);
        setScopeAreaAvailable(true);
      }
      if (meterResult.status === 'fulfilled' && Array.isArray(meterResult.value)) {
        setScopeMeters(meterResult.value);
        setScopeMeterAvailable(true);
      }
      setScopeDataLoading(false);
    };

    if (!hasReportingPeriod) {
      setPlantStatus('no-period');
      loadScopeData().catch((error) => {
        if (currentRequestId !== requestId.current) return;
        setScopeDataLoading(false);
        setPlantError(error?.message || 'Unable to load area and meter data.');
      });
      return () => {
        requestId.current += 1;
      };
    }

    setPlantStatus('loading');

    const loadComparisons = async () => {
      const [lineResult] = await Promise.allSettled([
        productionApi.getByLine(periodParams),
      ]);

      if (currentRequestId !== requestId.current) return;
      await loadScopeData();
      if (currentRequestId !== requestId.current) return;

      let plantIds = [];
      let discoveryError = '';
      if (lineResult.status === 'fulfilled' && Array.isArray(lineResult.value)) {
        plantIds = [...new Set(
          lineResult.value
            .map((line) => line?.plant_id)
            .filter((plantId) => typeof plantId === 'string' && plantId.trim() !== '')
        )];
      } else {
        discoveryError = lineResult.status === 'rejected'
          ? lineResult.reason?.message || 'Production-by-line data could not be retrieved.'
          : 'Production-by-line response did not contain a list of records.';
      }

      if (selectedPlant && !plantIds.includes(selectedPlant)) {
        plantIds.push(selectedPlant);
      }

      if (plantIds.length === 0) {
        setPlantStatus(discoveryError ? 'error' : 'empty');
        setPlantError(discoveryError || '');
        return;
      }

      const rows = await Promise.all(plantIds.map(async (plantId) => {
        const params = { ...periodParams, plant_id: plantId };
        const [energyResult, processResult, factoryResult] = await Promise.allSettled([
          energyApi.getSummary(params),
          energyIntensityApi.getProcessEnergy(params),
          energyIntensityApi.getFactoryEnergy(params),
        ]);

        return {
          plantId,
          energySummary: energyResult.status === 'fulfilled' ? energyResult.value : null,
          energyAvailable: energyResult.status === 'fulfilled',
          processEnergy: processResult.status === 'fulfilled' ? processResult.value : null,
          processAvailable: processResult.status === 'fulfilled',
          factoryEnergy: factoryResult.status === 'fulfilled' ? factoryResult.value : null,
          factoryAvailable: factoryResult.status === 'fulfilled',
        };
      }));

      if (currentRequestId !== requestId.current) return;
      setPlantRows(rows);
      setPlantDiscoveryPartial(Boolean(discoveryError));
      setPlantError(discoveryError);
      setPlantStatus('ready');
    };

    loadComparisons().catch((error) => {
      if (currentRequestId !== requestId.current) return;
      setScopeDataLoading(false);
      setPlantStatus('error');
      setPlantError(error?.message || 'Unable to load energy performance comparisons.');
    });

    return () => {
      requestId.current += 1;
    };
  }, [startDate, endDate, hasReportingPeriod, selectedPlant, refreshToken]);

  const areaValuesComplete = hasReportingPeriod
    && scopeAreaAvailable
    && scopeAreas.length > 1
    && scopeAreas.every((area) => isNonNegativeNumber(area?.consumption_kwh));
  const meterValuesComplete = hasReportingPeriod
    && scopeMeterAvailable
    && scopeMeters.length > 1
    && scopeMeters.every((meter) => isNonNegativeNumber(meter?.consumption_kwh));
  const plantValuesComplete = plantRows.length > 1
    && plantRows.every((row) => row.energyAvailable
      && isNonNegativeNumber(row.energySummary?.total_consumption_kwh));

  const areaRanks = assignRanks(scopeAreas, (area) => area?.consumption_kwh, areaValuesComplete);
  const meterRanks = assignRanks(scopeMeters, (meter) => meter?.consumption_kwh, meterValuesComplete);
  const plantRanks = assignRanks(
    plantRows,
    (row) => row.energySummary?.total_consumption_kwh,
    plantValuesComplete
  );

  const sortedAreas = [...scopeAreas].sort((left, right) => {
    if (!areaValuesComplete) return 0;
    return Number(right.consumption_kwh) - Number(left.consumption_kwh);
  });
  const sortedMeters = [...scopeMeters].sort((left, right) => {
    if (!meterValuesComplete) return 0;
    return Number(right.consumption_kwh) - Number(left.consumption_kwh);
  });
  const sortedPlantRows = [...plantRows].sort((left, right) => {
    if (!plantValuesComplete) return left.plantId.localeCompare(right.plantId);
    return Number(right.energySummary.total_consumption_kwh)
      - Number(left.energySummary.total_consumption_kwh);
  });

  const periodLabel = hasReportingPeriod
    ? `${formatDate(startDate)} – ${formatDate(endDate)}`
    : 'Unavailable';
  const scopeLabel = selectedPlant || 'All plants';
  const selectedMeter = scopeMeters.find((meter) => meterKey(meter) === selectedMeterKey) || null;

  return (
    <section className="dashboard-section energy-performance-comparison">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Performance Comparison</h3>
          <p className="section-desc">
            Compare returned energy totals and existing, scope-specific intensity values without treating consumption as efficiency.
          </p>
        </div>
      </div>

      <div className="energy-comparison-scope" role="status">
        <span><strong>Requested period:</strong> {periodLabel}</span>
        <span><strong>Area and meter scope:</strong> {scopeLabel}</span>
        <span><strong>Plant list:</strong> production-line identifiers plus the selected plant if absent</span>
      </div>

      <details className="energy-comparison-explanation">
        <summary>Comparison basis and limitations</summary>
        <ul>
          <li>Plant energy values use the same requested date range. Plant ranks are among plant IDs returned by production-line data for that period; they are by total kWh only, not efficiency.</li>
          <li>The APIs do not expose completeness indicators for each plant, area, or meter. Rankings are withheld if a compared group has unavailable energy totals.</li>
          <li>Factory, SMT, and FAL intensity values are existing API calculations and are shown separately. No new intensity is calculated or ranked; product mix and production-scope equivalence are not established here.</li>
          <li>Facility utility consumption is not assigned to production areas, lines, or products.</li>
          <li>This page has no date-range selector. The period is derived from returned daily-energy dates. Area and meter endpoints receive the same period and selected plant; if dates are unavailable, measurements are shown without ranks.</li>
        </ul>
      </details>

      <div className="energy-comparison-panel">
        <div className="energy-comparison-panel-heading">
          <div>
            <h4>Plant comparison</h4>
            <p>Total energy is a consumption measure; existing output and intensity values are contextual, not a plant efficiency ranking.</p>
          </div>
          {plantStatus === 'loading' && <span className="energy-comparison-badge">Loading</span>}
        </div>

        {plantStatus === 'loading' ? (
          <p className="energy-comparison-state" role="status" aria-live="polite">Loading plant comparison data…</p>
        ) : plantStatus === 'no-period' ? (
          <p className="energy-comparison-state">Plant comparisons are unavailable because returned daily-energy dates do not define a reporting period.</p>
        ) : plantStatus === 'error' ? (
          <p className="energy-comparison-state" role="alert">{plantError}</p>
        ) : plantStatus === 'empty' ? (
          <p className="energy-comparison-state">No plant identifiers were returned from production-line data for this period.</p>
        ) : (
          <>
            {plantDiscoveryPartial && (
              <p className="energy-comparison-state" role="status">
                Plant discovery was incomplete: {plantError} Only the current plant is shown.
              </p>
            )}
            {plantRows.some((row) => !row.energyAvailable || !row.processAvailable || !row.factoryAvailable) && (
              <p className="energy-comparison-state" role="status">
                Partial data: one or more plant energy or intensity requests were unavailable.
              </p>
            )}
            {!plantValuesComplete && plantRows.length > 1 && (
              <p className="energy-comparison-state">
                Consumption ranks are withheld because at least one plant total is unavailable.
              </p>
            )}
            <div className="energy-comparison-table-wrap">
              <table className="energy-comparison-table">
                <thead>
                  <tr>
                    <th>Plant</th>
                    <th>Electricity Intensity</th>
                    <th>Cost Intensity</th>
                    <th>Emissions Intensity</th>
                    <th>Good Finished Output</th>
                    <th>Coverage</th>
                    <th>Engineering &amp; Lineage Inspection</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPlantRows.map((row) => (
                    <tr key={row.plantId}>
                      <th scope="row">{row.plantId}</th>
                      <td>
                        <span style={{ fontWeight: 600 }}>
                          {row.factoryAvailable
                            ? valueOrUnavailable(row.factoryEnergy?.electricity_intensity_kwh_per_good_unit, 4, 'kWh/good unit')
                            : 'Unavailable'}
                        </span>
                      </td>
                      <td>
                        {row.factoryAvailable
                          ? valueOrUnavailable(row.factoryEnergy?.cost_intensity_inr_per_good_unit, 2, '₹/good unit')
                          : 'Unavailable'}
                      </td>
                      <td>
                        {row.factoryAvailable
                          ? valueOrUnavailable(row.factoryEnergy?.emissions_intensity_co2e_per_good_unit, 4, 'kg CO₂e/good unit')
                          : 'Unavailable'}
                      </td>
                      <td>
                        {row.factoryAvailable
                          ? valueOrUnavailable(row.factoryEnergy?.final_assembly_good_output, 0, 'units')
                          : 'Unavailable'}
                      </td>
                      <td>
                        {row.factoryAvailable && row.factoryEnergy?.coverage ? (
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '0.15rem 0.45rem',
                              borderRadius: '4px',
                              fontSize: '0.72rem',
                              fontWeight: 600,
                              backgroundColor: row.factoryEnergy.coverage.coverage_status === 'FULL' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                              color: row.factoryEnergy.coverage.coverage_status === 'FULL' ? '#22c55e' : '#eab308',
                              border: `1px solid ${row.factoryEnergy.coverage.coverage_status === 'FULL' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`,
                            }}
                          >
                            {row.factoryEnergy.coverage.coverage_status} ({row.factoryEnergy.coverage.coverage_percentage}%)
                          </span>
                        ) : 'Unavailable'}
                      </td>
                      <td>
                        <details className="energy-comparison-inline-details">
                          <summary>Inspect Numerator / Denominator</summary>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: '0.35rem', fontSize: '0.75rem' }}>
                            <span>
                              <strong>Numerator (Energy):</strong> {row.factoryAvailable ? valueOrUnavailable(row.factoryEnergy?.factory_sec_aligned_energy_kwh, 2, 'kWh') : 'Unavailable'}
                            </span>
                            <span>
                              <strong>Numerator (Cost):</strong> {row.factoryAvailable ? valueOrUnavailable(row.factoryEnergy?.factory_sec_aligned_cost_inr, 2, 'INR') : 'Unavailable'} (Tariff: ₹8.25/kWh, UNKNOWN)
                            </span>
                            <span>
                              <strong>Numerator (CO₂e):</strong> {row.factoryAvailable ? valueOrUnavailable(row.factoryEnergy?.factory_sec_aligned_co2e_kg, 2, 'kg') : 'Unavailable'} (Grid factor: 0.716 kg/kWh, UNKNOWN)
                            </span>
                            <span>
                              <strong>Denominator:</strong> {row.factoryAvailable ? `${valueOrUnavailable(row.factoryEnergy?.final_assembly_good_output, 0, 'good units')} (Actual: ${valueOrUnavailable(row.factoryEnergy?.final_assembly_actual_output, 0, 'units')})` : 'Unavailable'}
                            </span>
                            <span>
                              <strong>Engineering SEC (Actual):</strong> {row.factoryAvailable ? valueOrUnavailable(row.factoryEnergy?.factory_sec_kwh_per_finished_unit, 4, 'kWh/unit') : 'Unavailable'}
                            </span>
                            <span>
                              <strong>Process SMT:</strong> {row.processAvailable ? (
                                `${valueOrUnavailable(row.processEnergy?.smt_summary?.process_kwh ?? row.processEnergy?.smt_summary?.total_process_kwh, 2, 'kWh')} · ${valueOrUnavailable(row.processEnergy?.smt_summary?.good_units ?? row.processEnergy?.smt_summary?.total_good_qty, 0, 'good boards')} (${valueOrUnavailable(row.processEnergy?.smt_summary?.actual_units ?? row.processEnergy?.smt_summary?.total_actual_qty, 0, 'actual boards')}) · ${valueOrUnavailable(row.processEnergy?.smt_summary?.kwh_per_good_unit ?? row.processEnergy?.smt_summary?.overall_process_sec_good_kwh_per_board, 4, 'kWh/good board')} [Actual: ${valueOrUnavailable(row.processEnergy?.smt_summary?.kwh_per_actual_unit ?? row.processEnergy?.smt_summary?.overall_process_sec_kwh_per_board, 4, 'kWh/actual board')}]`
                              ) : 'Unavailable'}
                            </span>
                            <span>
                              <strong>Process FAL:</strong> {row.processAvailable ? (
                                `${valueOrUnavailable(row.processEnergy?.fal_summary?.process_kwh ?? row.processEnergy?.fal_summary?.total_process_kwh, 2, 'kWh')} · ${valueOrUnavailable(row.processEnergy?.fal_summary?.good_units ?? row.processEnergy?.fal_summary?.total_good_qty, 0, 'good assembly units')} (${valueOrUnavailable(row.processEnergy?.fal_summary?.actual_units ?? row.processEnergy?.fal_summary?.total_actual_qty, 0, 'actual assembly units')}) · ${valueOrUnavailable(row.processEnergy?.fal_summary?.kwh_per_good_unit ?? row.processEnergy?.fal_summary?.overall_process_sec_good_kwh_per_assembly_unit, 4, 'kWh/good assembly unit')} [Actual: ${valueOrUnavailable(row.processEnergy?.fal_summary?.kwh_per_actual_unit ?? row.processEnergy?.fal_summary?.overall_process_sec_kwh_per_phone, 4, 'kWh/actual assembly unit')}]`
                              ) : 'Unavailable'}
                            </span>
                          </div>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {plantRows.length > 0 && !plantValuesComplete && plantRows.length === 1 && (
              <p className="energy-comparison-state">A single plant was returned; a cross-plant consumption rank is not applicable.</p>
            )}
          </>
        )}
      </div>

      <details className="energy-comparison-breakdowns">
        <summary>Area and meter consumption comparison</summary>
        <p className="energy-comparison-breakdown-note">
          These values use the existing {scopeLabel} area and meter APIs. Ranks are consumption-only, not efficiency comparisons, and are not assigned when the reporting period is unavailable.
        </p>
        {!scopeProcessAvailable && (
          <p className="energy-comparison-state">Existing process intensity and matched production quantities are unavailable for this scope.</p>
        )}
        <div className="energy-comparison-breakdown-grid">
          <section className="energy-comparison-panel">
            <div className="energy-comparison-panel-heading">
              <div>
                <h4>Energy by area</h4>
                <p>Production evidence is shown only where the existing process-intensity API matches the area.</p>
              </div>
            </div>
            <ComparisonTableState
              available={scopeAreaAvailable}
              count={scopeAreas.length}
              label="area"
              loading={scopeDataLoading}
            />
            {scopeAreaAvailable && scopeAreas.length > 0 && (
              <div className="energy-comparison-table-wrap">
                <table className="energy-comparison-table">
                  <thead>
                    <tr>
                      <th>Area</th>
                      <th>Energy consumption</th>
                      <th>Matched production</th>
                      <th>Existing process intensity</th>
                      <th>Consumption rank</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedAreas.map((area, index) => {
                      const process = getProcessMetrics(area?.area, null, scopeProcessEnergy, scopeProcessAvailable);
                      return (
                        <tr key={area?.area || `area-${index}`}>
                          <th scope="row">{area?.area || 'Area unavailable'}</th>
                          <td>{valueOrUnavailable(area?.consumption_kwh, 2, 'kWh')}</td>
                          <td>{process.production}</td>
                          <td>{process.intensity}</td>
                          <td>{areaRanks.has(area) ? `#${areaRanks.get(area)}` : 'Not ranked'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {scopeAreaAvailable && scopeAreas.length > 1 && !areaValuesComplete && (
              <p className="energy-comparison-state">Area consumption ranks are withheld because one or more returned totals are unavailable.</p>
            )}
          </section>

          <section className="energy-comparison-panel">
            <div className="energy-comparison-panel-heading">
              <div>
                <h4>Energy by meter</h4>
                <p>Facility utility meters are not assigned production quantities or process intensity.</p>
              </div>
            </div>
            <ComparisonTableState
              available={scopeMeterAvailable}
              count={scopeMeters.length}
              label="meter"
              loading={scopeDataLoading}
            />
            {scopeMeterAvailable && scopeMeters.length > 0 && (
              <div className="energy-comparison-table-wrap">
                <table className="energy-comparison-table">
                  <thead>
                    <tr>
                      <th>Meter</th>
                      <th>Area</th>
                      <th>Energy consumption</th>
                      <th>Matched production</th>
                      <th>Existing process intensity</th>
                      <th>Consumption rank</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedMeters.map((meter, index) => {
                      const process = getProcessMetrics(meter?.area, meter?.meter_id, scopeProcessEnergy, scopeProcessAvailable);
                      const isSelected = meterKey(meter) === selectedMeterKey;
                      return (
                        <tr
                          key={meterKey(meter) || `meter-${index}`}
                          className={isSelected ? 'selected' : ''}
                        >
                          <th scope="row">
                            <button
                              type="button"
                              className="energy-comparison-meter-select"
                              aria-pressed={isSelected}
                              aria-label={`${isSelected ? 'Selected' : 'Inspect'} meter ${meter?.meter_id || 'unavailable'}${meter?.area ? ` in ${meter.area}` : ''}`}
                              onClick={() => setSelectedMeterKey(isSelected ? null : meterKey(meter))}
                            >
                              {meter?.meter_id || 'Meter unavailable'}
                            </button>
                          </th>
                          <td>{meter?.area || 'Unavailable'}</td>
                          <td>{valueOrUnavailable(meter?.consumption_kwh, 2, 'kWh')}</td>
                          <td>{process.production}</td>
                          <td>{process.intensity}</td>
                          <td>{meterRanks.has(meter) ? `#${meterRanks.get(meter)}` : 'Not ranked'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {scopeMeterAvailable && scopeMeters.length > 1 && !meterValuesComplete && (
              <p className="energy-comparison-state">Meter consumption ranks are withheld because one or more returned totals are unavailable.</p>
            )}
            {selectedMeter && (
              <section className="energy-meter-investigation" aria-labelledby="energy-meter-investigation-title">
                <div className="energy-meter-investigation-header">
                  <div>
                    <h5 id="energy-meter-investigation-title">Meter investigation: {selectedMeter.meter_id}</h5>
                    <p>{selectedMeter.area || 'Area unavailable'} · {periodLabel} · {scopeLabel}</p>
                  </div>
                  <button
                    type="button"
                    className="energy-meter-investigation-clear"
                    onClick={() => setSelectedMeterKey(null)}
                  >
                    Clear selection
                  </button>
                </div>

                <div className="energy-meter-investigation-metrics">
                  <div>
                    <span>Total interval energy</span>
                    <strong>{valueOrUnavailable(selectedMeter.consumption_kwh, 2, 'kWh')}</strong>
                  </div>
                  <div>
                    <span>Average consumption</span>
                    <strong>Unavailable</strong>
                    <small>Per-meter average is not returned by the existing API.</small>
                  </div>
                  <div>
                    <span>Peak hourly consumption</span>
                    <strong>{valueOrUnavailable(selectedMeter.peak_kwh, 2, 'kWh')}</strong>
                  </div>
                  <div>
                    <span>Energy-weighted average power factor</span>
                    <strong>
                      {isFiniteNumber(selectedMeter.avg_power_factor)
                        ? formatNumber(selectedMeter.avg_power_factor, 4)
                        : 'Unavailable'}
                    </strong>
                  </div>
                  <div>
                    <span>Returned readings</span>
                    <strong>{valueOrUnavailable(selectedMeter.reading_count, 0, 'readings')}</strong>
                  </div>
                </div>

                <div className="energy-meter-investigation-trend" role="status">
                  <h6>Meter consumption history</h6>
                  <p>
                    Unavailable: the existing daily trend endpoint aggregates the selected scope across meters, while the meter endpoint returns period aggregates only. No meter-specific time series is exposed, so no trend is inferred.
                  </p>
                </div>
                <p className="energy-meter-investigation-note">
                  Peak hourly consumption is interval energy in kWh, not electrical demand in kW. These measurements do not diagnose equipment faults, avoidable waste, or efficiency.
                </p>
              </section>
            )}
          </section>
        </div>
      </details>
    </section>
  );
}
