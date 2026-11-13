import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

export default function DailyIntensitySection({
  processEnergy,
  factoryEnergy,
  productionAvailable = false,
  productionSummary,
}) {
  // SMT Area Data
  const smtSec = processEnergy?.smt_summary?.overall_process_sec_kwh_per_board;
  const smtKwh = processEnergy?.smt_summary?.total_process_kwh;
  const smtUnits = processEnergy?.smt_summary?.total_actual_qty;

  // FAL Area Data
  const falSec = processEnergy?.fal_summary?.overall_process_sec_kwh_per_phone;
  const falKwh = processEnergy?.fal_summary?.total_process_kwh;
  const falUnits = processEnergy?.fal_summary?.total_actual_qty;

  // Factory Level Data
  const factorySec = factoryEnergy?.factory_sec_kwh_per_finished_unit;
  const factorySecGood = factoryEnergy?.factory_sec_good_kwh_per_finished_unit;
  const totalPlantKwh = factoryEnergy?.total_plant_energy_kwh;
  const finishedPhones = factoryEnergy?.final_assembly_actual_output;
  const utilitySharePct = factoryEnergy?.facility_utilities?.utility_share_percentage;
  const totalUtilityKwh = factoryEnergy?.facility_utilities?.total_utility_consumption_kwh;

  const productionQuantityKnown = productionSummary?.actual_qty != null
    && Number.isFinite(Number(productionSummary.actual_qty));
  const hasProduction = productionQuantityKnown && Number(productionSummary.actual_qty) > 0;

  return (
    <div className="dashboard-section daily-intensity-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Specific Energy Consumption (SEC) & Intensity</h3>
          <p className="section-desc">
            Energy efficiency benchmarks distinguishing dedicated manufacturing process SEC from total factory SEC.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag boundary-warning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            Facility Utilities Segregated from Process SEC
          </span>
        </div>
      </div>

      {!productionAvailable ? (
        <div className="intensity-unavailable-banner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            <strong>Production data unavailable</strong>
            <p>SEC cannot be evaluated because the production summary was not returned for this selection.</p>
          </div>
        </div>
      ) : !productionQuantityKnown ? (
        <div className="intensity-unavailable-banner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            <strong>Production quantity unavailable</strong>
            <p>SEC cannot be evaluated because the production quantity was not returned for this selection.</p>
          </div>
        </div>
      ) : !hasProduction ? (
        <div className="intensity-unavailable-banner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            <strong>Intensity Metrics Unavailable for this Selection</strong>
            <p>No finished units or board output were produced on this date. Specific Energy Consumption cannot be calculated with zero production denominator.</p>
          </div>
        </div>
      ) : (
        <div className="sec-cards-grid">
          {/* SMT Process SEC */}
          <div className="sec-card process-smt">
            <div className="sec-card-badge smt">Process Level • Submeter MTR-SMT</div>
            <div className="sec-card-header">
              <h4 className="sec-stage-title">SMT Lines SEC</h4>
              <span className="sec-target-product">Surface-Mount Printed Circuit Boards</span>
            </div>

            <div className="sec-primary-metric">
              <span className="sec-value">
                {smtSec !== null && smtSec !== undefined ? formatNumber(smtSec, 4) : '—'}
              </span>
              <span className="sec-unit">kWh / board <span className={`daily-value-kind ${smtSec == null ? 'unavailable' : ''}`}>{smtSec == null ? 'Unavailable' : 'Calculated'}</span></span>
            </div>

            <div className="sec-details-table">
              <div className="sec-detail-row">
                <span className="sec-detail-label">Direct Process Energy:</span>
                <span className="sec-detail-val">{formatNumber(smtKwh, 2)} kWh</span>
              </div>
              <div className="sec-detail-row">
                <span className="sec-detail-label">Total Boards Produced:</span>
                <span className="sec-detail-val">{formatNumber(smtUnits)} units</span>
              </div>
              <div className="sec-detail-row">
                <span className="sec-detail-label">Scope:</span>
                <span className="sec-detail-val">SMT-L1 & SMT-L2 Process Draw</span>
              </div>
            </div>

            <div className="sec-card-footer">
              <span className="sec-scope-indicator">Machine Process Energy Only</span>
            </div>
          </div>

          {/* Final Assembly Process SEC */}
          <div className="sec-card process-fal">
            <div className="sec-card-badge fal">Process Level • Submeter MTR-FAL</div>
            <div className="sec-card-header">
              <h4 className="sec-stage-title">Final Assembly SEC</h4>
              <span className="sec-target-product">Box-build & Finished Smartphone Units</span>
            </div>

            <div className="sec-primary-metric">
              <span className="sec-value">
                {falSec !== null && falSec !== undefined ? formatNumber(falSec, 4) : '—'}
              </span>
              <span className="sec-unit">kWh / phone <span className={`daily-value-kind ${falSec == null ? 'unavailable' : ''}`}>{falSec == null ? 'Unavailable' : 'Calculated'}</span></span>
            </div>

            <div className="sec-details-table">
              <div className="sec-detail-row">
                <span className="sec-detail-label">Direct Process Energy:</span>
                <span className="sec-detail-val">{formatNumber(falKwh, 2)} kWh</span>
              </div>
              <div className="sec-detail-row">
                <span className="sec-detail-label">Finished Phones Produced:</span>
                <span className="sec-detail-val">{formatNumber(falUnits)} units</span>
              </div>
              <div className="sec-detail-row">
                <span className="sec-detail-label">Scope:</span>
                <span className="sec-detail-val">FAL-L1 & FAL-L2 Process Draw</span>
              </div>
            </div>

            <div className="sec-card-footer">
              <span className="sec-scope-indicator">Machine Process Energy Only</span>
            </div>
          </div>

          {/* Factory Overall SEC */}
          <div className="sec-card factory-sec">
            <div className="sec-card-badge factory">Factory Level • All 5 Plant Meters</div>
            <div className="sec-card-header">
              <h4 className="sec-stage-title">Total Factory SEC</h4>
              <span className="sec-target-product">Plant Energy Per Finished Good Unit</span>
            </div>

            <div className="sec-primary-metric highlight">
              <span className="sec-value">
                {factorySec !== null && factorySec !== undefined ? formatNumber(factorySec, 4) : '—'}
              </span>
              <span className="sec-unit">kWh / finished phone <span className={`daily-value-kind ${factorySec == null ? 'unavailable' : ''}`}>{factorySec == null ? 'Unavailable' : 'Calculated'}</span></span>
            </div>

            <div className="sec-details-table">
              <div className="sec-detail-row">
                <span className="sec-detail-label">Total Plant Energy:</span>
                <span className="sec-detail-val">{formatNumber(totalPlantKwh, 2)} kWh</span>
              </div>
              <div className="sec-detail-row">
                <span className="sec-detail-label">Finished Output Gate:</span>
                <span className="sec-detail-val">{formatNumber(finishedPhones)} phones</span>
              </div>
              <div className="sec-detail-row">
                <span className="sec-detail-label">Facility Utilities Share:</span>
                <span className="sec-detail-val">
                  {formatPercent(utilitySharePct, 1)} ({formatNumber(totalUtilityKwh, 0)} kWh)
                </span>
              </div>
            </div>

            <div className="sec-card-footer factory">
              <span className="sec-scope-indicator">Includes HVAC, Compressor, Chiller</span>
            </div>
          </div>
        </div>
      )}

      <div className="daily-disclaimer-box intensity-disclaimer">
        <div className="disclaimer-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/>
          </svg>
        </div>
        <div className="disclaimer-content">
          <h4 className="disclaimer-title">Energy Boundary & Allocation Rule</h4>
          <p className="disclaimer-text">
            Direct Process SEC reflects dedicated machine submeters (MTR-SMT and MTR-FAL) for line-level equipment energy. 
            Factory utilities (Chiller, Air Compressor, HVAC) maintain overall plant environmental and cleanroom baseline operations. 
            In adherence to industrial energy accounting standards, utility energy is neither arbitrarily distributed across assembly lines nor attributed to individual product SKUs.
          </p>
        </div>
      </div>
    </div>
  );
}
