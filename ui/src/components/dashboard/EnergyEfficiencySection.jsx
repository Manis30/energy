import React from 'react';
import { formatNumber } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

function displayNumber(value, decimals = 2) {
  return hasNumber(value) ? formatNumber(value, decimals) : 'Unavailable';
}

export default function EnergyEfficiencySection({
  processEnergy,
  factoryEnergy,
  processAvailable = true,
  factoryAvailable = true,
}) {
  // SMT Area
  const smtSec = processEnergy?.smt_summary?.overall_process_sec_kwh_per_board ?? null;
  const smtKwh = processEnergy?.smt_summary?.total_process_kwh ?? null;
  const smtUnits = processEnergy?.smt_summary?.total_actual_qty ?? null;

  // FAL Area
  const falSec = processEnergy?.fal_summary?.overall_process_sec_kwh_per_phone ?? null;
  const falKwh = processEnergy?.fal_summary?.total_process_kwh ?? null;
  const falUnits = processEnergy?.fal_summary?.total_actual_qty ?? null;

  // Factory Overall SEC
  const factorySec = factoryEnergy?.factory_sec_kwh_per_finished_unit ?? null;
  const totalPlantKwh = factoryEnergy?.total_plant_energy_kwh ?? null;
  const finishedPhones = factoryEnergy?.final_assembly_actual_output ?? null;
  const utilitySharePct = factoryEnergy?.facility_utilities?.utility_share_percentage ?? null;
  const totalUtilityKwh = factoryEnergy?.facility_utilities?.total_utility_consumption_kwh ?? null;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Specific Energy Consumption (SEC) & Intensity</h3>
          <p className="section-desc">
            Calculated energy-per-output ratios from returned process and plant-wide data; these are not approved targets or proof of savings or efficiency improvement.
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

      <div className="sec-cards-grid">
        {/* SMT Process SEC */}
        <div className="sec-card process-smt">
          <div className="sec-card-badge smt">Process Level • Submeter MTR-SMT</div>
          <div className="sec-card-header">
            <h4 className="sec-stage-title">SMT Lines SEC</h4>
            <span className="sec-target-product">Surface-Mount Printed Circuit Boards</span>
          </div>

          <div className="sec-primary-metric">
            <span className="sec-value">{processAvailable ? displayNumber(smtSec, 4) : 'Unavailable'}</span>
            <span className="sec-unit">kWh / board</span>
          </div>

          <div className="sec-details-table">
            <div className="sec-detail-row">
              <span className="sec-detail-label">Direct Process Energy:</span>
              <span className="sec-detail-val">{processAvailable ? `${displayNumber(smtKwh, 2)} kWh` : 'Unavailable'}</span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Total Boards Produced:</span>
              <span className="sec-detail-val">{processAvailable ? `${displayNumber(smtUnits, 0)} units` : 'Unavailable'}</span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Lines Included:</span>
              <span className="sec-detail-val">MTR-SMT aggregate</span>
            </div>
          </div>

          <div className="sec-card-footer">
            <span className="sec-scope-indicator">Dedicated process submeter scope</span>
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
            <span className="sec-value">{processAvailable ? displayNumber(falSec, 4) : 'Unavailable'}</span>
            <span className="sec-unit">kWh / phone</span>
          </div>

          <div className="sec-details-table">
            <div className="sec-detail-row">
              <span className="sec-detail-label">Direct Process Energy:</span>
              <span className="sec-detail-val">{processAvailable ? `${displayNumber(falKwh, 2)} kWh` : 'Unavailable'}</span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Finished Phones Produced:</span>
              <span className="sec-detail-val">{processAvailable ? `${displayNumber(falUnits, 0)} units` : 'Unavailable'}</span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Lines Included:</span>
              <span className="sec-detail-val">MTR-FAL aggregate</span>
            </div>
          </div>

          <div className="sec-card-footer">
            <span className="sec-scope-indicator">Dedicated process submeter scope</span>
          </div>
        </div>

        {/* Factory SEC */}
        <div className="sec-card factory-sec">
          <div className="sec-card-badge factory">Factory level • plant-wide energy</div>
          <div className="sec-card-header">
            <h4 className="sec-stage-title">Total Factory SEC</h4>
            <span className="sec-target-product">Plant Energy Per Finished Good Unit</span>
          </div>

          <div className="sec-primary-metric highlight">
            <span className="sec-value">{factoryAvailable ? displayNumber(factorySec, 4) : 'Unavailable'}</span>
            <span className="sec-unit">kWh / finished phone</span>
          </div>

          <div className="sec-details-table">
            <div className="sec-detail-row">
              <span className="sec-detail-label">Total Plant Energy:</span>
              <span className="sec-detail-val">{factoryAvailable ? `${displayNumber(totalPlantKwh, 2)} kWh` : 'Unavailable'}</span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Finished Output Gate:</span>
              <span className="sec-detail-val">{factoryAvailable ? `${displayNumber(finishedPhones, 0)} phones` : 'Unavailable'}</span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Facility Utilities Share:</span>
              <span className="sec-detail-val">
                {factoryAvailable
                  ? `${displayNumber(utilitySharePct, 1)}% (${displayNumber(totalUtilityKwh, 0)} kWh)`
                  : 'Unavailable'}
              </span>
            </div>
          </div>

          <div className="sec-card-footer factory">
            <span className="sec-scope-indicator">Includes HVAC, Compressor, Chiller</span>
          </div>
        </div>
      </div>
    </div>
  );
}

