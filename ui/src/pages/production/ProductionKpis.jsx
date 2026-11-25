import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

/**
 * Section 1: Final Assembly performance
 * Leads with finished goods production across Final Assembly (FAL) lines.
 * Displays 5 compact metrics in one desktop row:
 * 1. Good finished units
 * 2. Good-output yield
 * 3. Rejected units
 * 4. Line downtime (summed line-hours / line-min)
 * 5. Electricity per good finished unit (scope: factory electricity ÷ good FAL units)
 * Displays data coverage badge once beside the section header.
 */
export default function ProductionKpis({
  falData = null,
  factoryEnergy = null,
  summary = null,
  selectedLine = null,
  summaryAvailable = true,
}) {
  const qualityContext = factoryEnergy?.production_quality_context || {};
  const coverage = factoryEnergy?.coverage_summary || {};

  // Resolve Final Assembly metrics
  // Prefer explicitly computed falData from byLine; fallback to factoryEnergy context
  const goodQty = falData?.goodQty ?? qualityContext.good_qty ?? (selectedLine?.startsWith('FAL') ? summary?.good_qty : null);
  const actualQty = falData?.actualQty ?? qualityContext.actual_qty ?? (selectedLine?.startsWith('FAL') ? summary?.actual_qty : null);
  const rejectQty = falData?.rejectQty ?? qualityContext.reject_qty ?? (selectedLine?.startsWith('FAL') ? summary?.reject_qty : null);
  const yieldPct = falData?.yieldPct ?? qualityContext.yield_percentage ?? (selectedLine?.startsWith('FAL') ? summary?.good_rate : null);
  const rejectPct = falData?.rejectPct ?? qualityContext.reject_rate_percentage ?? (selectedLine?.startsWith('FAL') ? summary?.reject_rate : null);
  const downtimeMin = falData?.downtimeMin ?? qualityContext.downtime_minutes ?? (selectedLine?.startsWith('FAL') ? summary?.downtime_min : null);

  const downtimeHours = hasNumber(downtimeMin)
    ? (Number(downtimeMin) / 60).toFixed(1)
    : null;

  const elecIntensity = factoryEnergy?.electricity_intensity_kwh_per_good_unit ?? null;
  const coverageStatus = coverage.coverage_status ?? null;
  const coveragePct = coverage.coverage_percentage ?? null;

  return (
    <div className="dashboard-section fal-performance-panel">
      {/* 1. Header with Title & Single Coverage Badge */}
      <div className="section-header fal-header">
        <div>
          <h3 className="section-title">Final Assembly performance</h3>
          <p className="section-desc">
            Finished goods throughput, quality yield, and factory energy intensity across Final Assembly lines.
          </p>
        </div>
        {coverageStatus && (
          <div className="coverage-badge-container">
            <span
              className={`compact-coverage-badge ${
                coverageStatus === 'FULL' ? 'full' : 'partial'
              }`}
            >
              <span className="coverage-dot"></span>
              {coverageStatus === 'FULL' ? 'Full coverage' : 'Partial coverage'} · {hasNumber(coveragePct) ? `${coveragePct}%` : '100%'}
            </span>
          </div>
        )}
      </div>

      {/* 2. Five Compact Metrics in One Desktop Row */}
      <div className="fal-summary-strip">
        {/* Metric 1: Good Finished Units */}
        <div className="fal-segment">
          <span className="fal-label">Good finished units</span>
          <div className="fal-value-row">
            <span className="fal-val">
              {hasNumber(goodQty) ? formatNumber(goodQty) : '—'}
            </span>
            <span className="fal-unit">units</span>
          </div>
          <span className="fal-subtext">Final Assembly output gate</span>
        </div>

        {/* Metric 2: Good-Output Yield */}
        <div className="fal-segment">
          <span className="fal-label">Good-output yield</span>
          <div className="fal-value-row">
            <span className="fal-val">
              {hasNumber(yieldPct) ? formatPercent(yieldPct) : '—'}
            </span>
            <span className="fal-unit">% of actual</span>
          </div>
          <span className="fal-subtext">Good ÷ actual FAL units</span>
        </div>

        {/* Metric 3: Rejected Units (consistent with FAL scrap count and rate) */}
        <div className="fal-segment">
          <span className="fal-label">Rejected units</span>
          <div className="fal-value-row">
            <span className="fal-val">
              {hasNumber(rejectQty) ? formatNumber(rejectQty) : '—'}
            </span>
            <span className="fal-unit">units</span>
          </div>
          <span className="fal-subtext">
            {hasNumber(rejectPct) ? `${formatPercent(rejectPct)} reject rate` : 'Final Assembly scrap'}
          </span>
        </div>

        {/* Metric 4: Line Downtime */}
        <div className="fal-segment">
          <span className="fal-label">Line downtime</span>
          <div className="fal-value-row">
            <span className="fal-val">
              {hasNumber(downtimeHours) ? formatNumber(downtimeHours, 1) : '—'}
            </span>
            <span className="fal-unit">line-hrs</span>
          </div>
          <span className="fal-subtext">
            {hasNumber(downtimeMin) ? `Summed: ${formatNumber(downtimeMin)} line-min` : 'Summed across FAL lines'}
          </span>
        </div>

        {/* Metric 5: Electricity Intensity */}
        <div className="fal-segment">
          <span className="fal-label">Electricity per good finished unit</span>
          <div className="fal-value-row">
            <span className="fal-val">
              {hasNumber(elecIntensity) ? formatNumber(elecIntensity, 4) : '—'}
            </span>
            <span className="fal-unit">kWh/good unit</span>
          </div>
          <span className="fal-subtext">Factory electricity ÷ good FAL units</span>
        </div>
      </div>
    </div>
  );
}
