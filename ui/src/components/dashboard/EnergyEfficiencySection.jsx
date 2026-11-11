import React from 'react';
import { formatNumber } from '../../utils/formatters';

export default function EnergyEfficiencySection({ processEnergy, factoryEnergy }) {
  // SMT Area
  const smtSec = processEnergy?.smt_summary?.overall_process_sec_kwh_per_board || '0.3547';
  const smtKwh = processEnergy?.smt_summary?.total_process_kwh || '507553.50';
  const smtUnits = processEnergy?.smt_summary?.total_actual_qty || '1431132';

  // FAL Area
  const falSec = processEnergy?.fal_summary?.overall_process_sec_kwh_per_phone || '0.3652';
  const falKwh = processEnergy?.fal_summary?.total_process_kwh || '362678.42';
  const falUnits = processEnergy?.fal_summary?.total_actual_qty || '993052';

  // Factory Overall SEC
  const factorySec = factoryEnergy?.factory_sec_kwh_per_finished_unit || '1.9718';
  const totalPlantKwh = factoryEnergy?.total_plant_energy_kwh || '1958088.31';
  const finishedPhones = factoryEnergy?.final_assembly_actual_output || '993052';
  const utilitySharePct = factoryEnergy?.facility_utilities?.utility_share_percentage || '55.56';
  const totalUtilityKwh = factoryEnergy?.facility_utilities?.total_utility_consumption_kwh || '1087856.39';

  return (
    <div className="dashboard-section">
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

      <div className="sec-cards-grid">
        {/* SMT Process SEC */}
        <div className="sec-card process-smt">
          <div className="sec-card-badge smt">Process Level • Submeter MTR-SMT</div>
          <div className="sec-card-header">
            <h4 className="sec-stage-title">SMT Lines SEC</h4>
            <span className="sec-target-product">Surface-Mount Printed Circuit Boards</span>
          </div>

          <div className="sec-primary-metric">
            <span className="sec-value">{formatNumber(smtSec, 4)}</span>
            <span className="sec-unit">kWh / board</span>
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
              <span className="sec-detail-label">Lines Included:</span>
              <span className="sec-detail-val">SMT-L1 (0.3567) & SMT-L2 (0.3528)</span>
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
            <span className="sec-value">{formatNumber(falSec, 4)}</span>
            <span className="sec-unit">kWh / phone</span>
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
              <span className="sec-detail-label">Lines Included:</span>
              <span className="sec-detail-val">FAL-L1 (0.3673) & FAL-L2 (0.3631)</span>
            </div>
          </div>

          <div className="sec-card-footer">
            <span className="sec-scope-indicator">Machine Process Energy Only</span>
          </div>
        </div>

        {/* Factory SEC */}
        <div className="sec-card factory-sec">
          <div className="sec-card-badge factory">Factory Level • All 5 Plant Meters</div>
          <div className="sec-card-header">
            <h4 className="sec-stage-title">Total Factory SEC</h4>
            <span className="sec-target-product">Plant Energy Per Finished Good Unit</span>
          </div>

          <div className="sec-primary-metric highlight">
            <span className="sec-value">{formatNumber(factorySec, 4)}</span>
            <span className="sec-unit">kWh / finished phone</span>
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
              <span className="sec-detail-val">{formatNumber(utilitySharePct, 1)}% ({formatNumber(totalUtilityKwh, 0)} kWh)</span>
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

