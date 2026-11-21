import React, { useState } from 'react';
import { formatNumber } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

function displayNumber(value, decimals = 2) {
  return hasNumber(value) ? formatNumber(value, decimals) : 'Unavailable';
}

export default function EnergyEfficiencySection({
  processEnergy,
  factoryEnergy,
  processAvailable = true,
  factoryAvailable = true,
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  // SMT Process Energy & SEC
  const smtSec = processEnergy?.smt_summary?.overall_process_sec_kwh_per_board ?? null;
  const smtKwh = processEnergy?.smt_summary?.total_process_kwh ?? null;
  const smtUnits = processEnergy?.smt_summary?.total_actual_qty ?? null;

  // FAL Process Energy & SEC
  const falSec = processEnergy?.fal_summary?.overall_process_sec_kwh_per_phone ?? null;
  const falKwh = processEnergy?.fal_summary?.total_process_kwh ?? null;
  const falUnits = processEnergy?.fal_summary?.total_actual_qty ?? null;

  // Factory Overall SEC & Intensity
  const isFactorySecAvailable = Boolean(
    factoryAvailable &&
    factoryEnergy?.factory_sec_data_available &&
    hasNumber(factoryEnergy?.factory_sec_kwh_per_finished_unit)
  );
  const factorySec = factoryEnergy?.factory_sec_kwh_per_finished_unit ?? null;
  const totalPlantKwh = factoryEnergy?.total_plant_energy_kwh ?? null;
  const finishedPhones = factoryEnergy?.final_assembly_actual_output ?? null;
  const utilitySharePct = factoryEnergy?.facility_utilities?.utility_share_percentage ?? null;
  const totalUtilityKwh = factoryEnergy?.facility_utilities?.total_utility_consumption_kwh ?? null;
  const factoryAlignmentNote = factoryEnergy?.factory_sec_alignment_note || 'Scope alignment not established';

  return (
    <div className="dashboard-section sec-dashboard-section">
      {/* Section Header with Info Tooltip & Segregation Tag */}
      <div className="section-header">
        <div className="section-header-title-row">
          <div className="sec-header-title-group">
            <h3 className="section-title">Specific Energy Consumption (SEC) &amp; Energy Intensity</h3>
            <button
              type="button"
              className="sec-info-btn"
              onClick={() => setShowTooltip(!showTooltip)}
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              aria-label="What is Specific Energy Consumption (SEC)?"
              title="Click to view SEC definition and engineering boundaries"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>What is SEC?</span>
            </button>

            {showTooltip && (
              <div className="sec-info-tooltip" role="tooltip">
                <div className="sec-tooltip-heading">Specific Energy Consumption (SEC) Standard</div>
                <p>
                  <strong>Specific Energy Consumption (SEC)</strong> represents electrical energy consumed per unit of manufactured output within a strictly defined process boundary.
                </p>
                <ul>
                  <li><strong>SMT Process:</strong> Measures kWh per completed printed circuit board (PCB).</li>
                  <li><strong>Final Assembly:</strong> Measures kWh per boxed smartphone unit.</li>
                  <li><strong>Factory SEC:</strong> Measures total plant energy per finished unit when line flows align.</li>
                </ul>
                <div className="sec-tooltip-warning">
                  ⚠️ SMT (kWh/board) and FAL (kWh/phone) reflect distinct manufacturing steps and must never be compared directly. Ratios are observed telemetry, not engineering savings guarantees.
                </div>
              </div>
            )}
          </div>
          <p className="section-desc">
            Direct process-level energy consumption per manufactured unit, with facility utilities segregated from line ratios.
          </p>
        </div>

        <div className="section-tag-group">
          <span className="section-tag boundary-warning" title="HVAC, Compressors and Chillers are isolated from process line SEC">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Facility Utilities Segregated from Process SEC
          </span>
        </div>
      </div>

      {/* 3 Prominent, Visually Consistent SEC Cards */}
      <div className="sec-cards-grid">
        {/* =================================================================== */}
        {/* CARD 1: SMT ENERGY EFFICIENCY                                      */}
        {/* =================================================================== */}
        <div className="sec-card process-smt">
          <div className="sec-card-top">
            <span className="sec-card-badge smt">Process Boundary • MTR-SMT</span>
            <span className="sec-stage-indicator">Stage 1: Surface-Mount</span>
          </div>

          <div className="sec-card-header">
            <h4 className="sec-stage-title">SMT Energy Efficiency</h4>
            <span className="sec-target-product">Printed Circuit Board (PCB) Assembly</span>
          </div>

          {/* Prominent Primary SEC Metric with Units Immediately Beside Value */}
          <div className="sec-primary-metric smt">
            <span className="sec-value">
              {processAvailable ? displayNumber(smtSec, 4) : 'Unavailable'}
            </span>
            <span className="sec-unit">kWh / board</span>
          </div>

          {/* Clean Structured Metric Rows */}
          <div className="sec-details-table">
            <div className="sec-detail-row">
              <span className="sec-detail-label">Process Energy</span>
              <span className="sec-detail-val">
                {processAvailable ? `${displayNumber(smtKwh, 2)} kWh` : 'Unavailable'}
              </span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Boards Produced</span>
              <span className="sec-detail-val">
                {processAvailable ? `${displayNumber(smtUnits, 0)} boards` : 'Unavailable'}
              </span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Lines Measured</span>
              <span className="sec-detail-val">SMT-L1 &amp; SMT-L2 (MTR-SMT)</span>
            </div>
          </div>

          <div className="sec-card-footer">
            <span className="sec-scope-indicator">
              Direct submeter telemetry; excludes facility HVAC &amp; compressors.
            </span>
          </div>
        </div>

        {/* =================================================================== */}
        {/* CARD 2: FINAL ASSEMBLY ENERGY EFFICIENCY                           */}
        {/* =================================================================== */}
        <div className="sec-card process-fal">
          <div className="sec-card-top">
            <span className="sec-card-badge fal">Process Boundary • MTR-FAL</span>
            <span className="sec-stage-indicator">Stage 2: Box-Build &amp; Packaging</span>
          </div>

          <div className="sec-card-header">
            <h4 className="sec-stage-title">Final Assembly Energy Efficiency</h4>
            <span className="sec-target-product">Finished Smartphone Box-Build</span>
          </div>

          {/* Prominent Primary SEC Metric with Units Immediately Beside Value */}
          <div className="sec-primary-metric fal">
            <span className="sec-value">
              {processAvailable ? displayNumber(falSec, 4) : 'Unavailable'}
            </span>
            <span className="sec-unit">kWh / phone</span>
          </div>

          {/* Clean Structured Metric Rows */}
          <div className="sec-details-table">
            <div className="sec-detail-row">
              <span className="sec-detail-label">Process Energy</span>
              <span className="sec-detail-val">
                {processAvailable ? `${displayNumber(falKwh, 2)} kWh` : 'Unavailable'}
              </span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Finished Phones Produced</span>
              <span className="sec-detail-val">
                {processAvailable ? `${displayNumber(falUnits, 0)} phones` : 'Unavailable'}
              </span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Lines Measured</span>
              <span className="sec-detail-val">FAL-L1 &amp; FAL-L2 (MTR-FAL)</span>
            </div>
          </div>

          <div className="sec-card-footer">
            <span className="sec-scope-indicator">
              Direct submeter telemetry; excludes facility HVAC &amp; compressors.
            </span>
          </div>
        </div>

        {/* =================================================================== */}
        {/* CARD 3: FACTORY ENERGY INTENSITY                                   */}
        {/* =================================================================== */}
        <div className="sec-card factory-sec">
          <div className="sec-card-top">
            <span className="sec-card-badge factory">Plant-Wide Boundary • Consolidated</span>
            <span className="sec-stage-indicator">Total Facility Gate</span>
          </div>

          <div className="sec-card-header">
            <h4 className="sec-stage-title">Factory Energy Intensity</h4>
            <span className="sec-target-product">Plant Energy Per Finished Unit Gate</span>
          </div>

          {/* Prominent Primary SEC Metric with Units Immediately Beside Value */}
          <div className="sec-primary-metric factory">
            <span className="sec-value">
              {isFactorySecAvailable ? displayNumber(factorySec, 4) : 'Unavailable'}
            </span>
            <span className="sec-unit">
              {isFactorySecAvailable ? 'kWh / finished phone' : '(Boundary Unaligned)'}
            </span>
          </div>

          {/* Clean Structured Metric Rows */}
          <div className="sec-details-table">
            <div className="sec-detail-row">
              <span className="sec-detail-label">Total Plant Energy</span>
              <span className="sec-detail-val">
                {factoryAvailable ? `${displayNumber(totalPlantKwh, 2)} kWh` : 'Unavailable'}
              </span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Finished Output Quantity</span>
              <span className="sec-detail-val">
                {factoryAvailable ? `${displayNumber(finishedPhones, 0)} phones` : 'Unavailable'}
              </span>
            </div>
            <div className="sec-detail-row">
              <span className="sec-detail-label">Facility Utilities Contribution</span>
              <span className="sec-detail-val">
                {factoryAvailable && hasNumber(utilitySharePct)
                  ? `${displayNumber(utilitySharePct, 1)}% (${displayNumber(totalUtilityKwh, 0)} kWh)`
                  : 'Unavailable'}
              </span>
            </div>
          </div>

          <div className="sec-card-footer factory">
            <span className="sec-scope-indicator">
              {isFactorySecAvailable
                ? 'Includes plant HVAC, air compressors & chillers.'
                : factoryAlignmentNote}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
