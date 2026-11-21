import React from 'react';
import { formatNumber, formatCurrency, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

export default function ProductionEnergyTradeoffSection({
  factoryEnergy,
  loading = false,
  selectedLine = null,
  selectedProduct = null,
  selectedShift = null,
  onClearFilters,
}) {
  const hasIncompatibleFilter = Boolean(selectedLine || selectedProduct || selectedShift);

  const qualityContext = factoryEnergy?.production_quality_context || {};
  const coverage = factoryEnergy?.coverage_summary || {};
  const lineage = factoryEnergy?.factor_lineage || {};

  const elecIntensity = factoryEnergy?.electricity_intensity_kwh_per_good_unit;
  const costIntensity = factoryEnergy?.cost_intensity_inr_per_good_unit;
  const emissionsIntensity = factoryEnergy?.emissions_intensity_co2e_per_good_unit;

  const targetQty = qualityContext.target_qty;
  const actualQty = qualityContext.actual_qty;
  const goodQty = qualityContext.good_qty;
  const rejectQty = qualityContext.reject_qty;
  const downtimeMin = qualityContext.downtime_minutes;
  const yieldPct = qualityContext.yield_percentage;
  const rejectPct = qualityContext.reject_rate_percentage;

  return (
    <div className="dashboard-section" style={{ marginTop: '1.5rem', marginBottom: '1.5rem' }}>
      <div className="section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h3 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>Energy Intensity &amp; Production Quality Trade-offs</span>
            <span
              style={{
                fontSize: '0.72rem',
                padding: '0.15rem 0.5rem',
                borderRadius: '4px',
                fontWeight: 600,
                backgroundColor: hasIncompatibleFilter ? 'rgba(239, 68, 68, 0.15)' : 'rgba(168, 85, 247, 0.15)',
                color: hasIncompatibleFilter ? '#ef4444' : '#a855f7',
                border: `1px solid ${hasIncompatibleFilter ? 'rgba(239, 68, 68, 0.3)' : 'rgba(168, 85, 247, 0.3)'}`,
              }}
            >
              {hasIncompatibleFilter ? 'Scope Incompatible' : 'Factory Scope'}
            </span>
          </h3>
          <p className="section-desc">
            Evaluating factory electricity intensity per good finished unit against quality yield, reject scrap, and FAL downtime.
            Lower energy intensity achieved by producing scrap or idling lines is not genuine operational efficiency.
          </p>
        </div>

        {coverage.coverage_status && !hasIncompatibleFilter && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.25rem 0.65rem',
                borderRadius: '12px',
                fontWeight: 600,
                backgroundColor: coverage.coverage_status === 'FULL' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                color: coverage.coverage_status === 'FULL' ? '#22c55e' : '#eab308',
                border: `1px solid ${coverage.coverage_status === 'FULL' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`,
              }}
            >
              Coverage: {coverage.coverage_status} ({coverage.coverage_percentage}% • {coverage.complete_matched_hours}/{coverage.expected_plant_hours} hrs)
            </span>
          </div>
        )}
      </div>

      {hasIncompatibleFilter ? (
        <div
          style={{
            padding: '1.25rem',
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: 'var(--radius-md, 8px)',
            marginTop: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.85rem' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.2" style={{ flexShrink: 0, marginTop: '2px' }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div style={{ flex: 1 }}>
              <h4 style={{ margin: 0, fontSize: '0.92rem', fontWeight: 600, color: '#f87171' }}>
                Factory Energy Intensity Unavailable for Sub-Plant Filter Selection
              </h4>
              <p style={{ margin: '0.4rem 0 0.75rem 0', fontSize: '0.82rem', color: 'var(--text-secondary, #94a3b8)', lineHeight: 1.5 }}>
                {factoryEnergy?.electricity_status_reason ||
                  `Factory energy intensity cannot be filtered by line (${selectedLine || 'all'}), product (${selectedProduct || 'all'}), or shift (${selectedShift || 'all'}) because facility utility loads (HVAC, compressed air, chillers) operate at plant scope and cannot be allocated to individual lines or products without supported submeter mappings.`}
              </p>
              {onClearFilters && (
                <button
                  type="button"
                  onClick={onClearFilters}
                  style={{
                    padding: '0.35rem 0.85rem',
                    backgroundColor: '#ef4444',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '4px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Clear Line / Product / Shift Filters to View Plant Scope
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* 5-Card Balanced KPI Strip */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '1rem',
              marginTop: '1rem',
            }}
          >
            {/* Card 1: Electricity Intensity */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1rem',
                borderLeft: '4px solid #a855f7',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
                Electricity Intensity
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0.3rem 0 0.15rem 0' }}>
                {hasNumber(elecIntensity) ? `${formatNumber(elecIntensity, 4)}` : 'Unavailable'}
                <span style={{ fontSize: '0.78rem', fontWeight: 500, color: '#a855f7', marginLeft: '0.35rem' }}>kWh/good unit</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span>Cost: {hasNumber(costIntensity) ? `${formatCurrency(costIntensity)}/unit` : '—'}</span>
                <span>•</span>
                <span>CO₂e: {hasNumber(emissionsIntensity) ? `${formatNumber(emissionsIntensity, 3)} kg/unit` : '—'}</span>
              </div>
            </div>

            {/* Card 2: Good Finished Units */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1rem',
                borderLeft: '4px solid #22c55e',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
                Good Output (FAL Gate)
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#22c55e', margin: '0.3rem 0 0.15rem 0' }}>
                {hasNumber(goodQty) ? formatNumber(goodQty) : 'Unavailable'}
                <span style={{ fontSize: '0.78rem', fontWeight: 500, color: 'var(--text-muted)', marginLeft: '0.35rem' }}>units</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                Actual: {hasNumber(actualQty) ? formatNumber(actualQty) : '—'} • Target: {hasNumber(targetQty) ? formatNumber(targetQty) : '—'}
              </div>
            </div>

            {/* Card 3: Good-Output Yield */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1rem',
                borderLeft: '4px solid #38bdf8',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
                Good-Output Yield %
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#38bdf8', margin: '0.3rem 0 0.15rem 0' }}>
                {hasNumber(yieldPct) ? formatPercent(yieldPct) : 'Unavailable'}
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                FAL good / actual output (98.16% historical; first-pass requires rework proof)
              </div>
            </div>

            {/* Card 4: Reject Scrap */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1rem',
                borderLeft: '4px solid #f87171',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
                Reject Scrap Units
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#f87171', margin: '0.3rem 0 0.15rem 0' }}>
                {hasNumber(rejectQty) ? formatNumber(rejectQty) : 'Unavailable'}
                <span style={{ fontSize: '0.78rem', fontWeight: 500, color: 'var(--text-muted)', marginLeft: '0.35rem' }}>units</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                FAL scrap: {hasNumber(rejectPct) ? formatPercent(rejectPct) : '—'} reject rate
              </div>
            </div>

            {/* Card 5: FAL Downtime (Summed Across Lines) */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1rem',
                borderLeft: '4px solid #eab308',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
                FAL Downtime (Summed Across Lines)
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#eab308', margin: '0.3rem 0 0.15rem 0' }}>
                {hasNumber(downtimeMin) ? `${formatNumber(downtimeMin)}` : 'Unavailable'}
                <span style={{ fontSize: '0.78rem', fontWeight: 500, color: 'var(--text-muted)', marginLeft: '0.35rem' }}>min</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                {hasNumber(downtimeMin) ? `~${(Number(downtimeMin) / 60).toFixed(1)} line-hours total stoppage across FAL lines` : '—'}
              </div>
            </div>
          </div>

          {/* Operational Trade-off Analysis Narrative */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1rem',
              marginTop: '1rem',
            }}
          >
            {/* Box 1: Reject Scrap Impact */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.85rem 1rem',
              }}
            >
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f87171', display: 'inline-block' }}></span>
                FAL Reject Scrap (18,262 units, 1.84% reject rate)
              </div>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Final Assembly produced <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(rejectQty)}</strong> rejected units ({formatPercent(rejectPct)} reject rate).
                Multiplying rejects by average factory intensity cannot establish energy consumed by rejected units or the amount that could be saved.
              </p>
            </div>

            {/* Box 2: Line Downtime Duration */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.85rem 1rem',
              }}
            >
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#eab308', display: 'inline-block' }}></span>
                FAL Downtime Duration (Summed Across Lines)
              </div>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Final Assembly logged <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(downtimeMin)}</strong> line-minutes (~{(Number(downtimeMin) / 60).toFixed(1)} line-hours) of downtime summed across lines.
                Showing utility consumption during stoppage intervals requires actual readings matched by plant and hour with interval overlap accounted for; downtime duration alone does not establish wasted energy.
              </p>
            </div>

            {/* Box 3: Boundary & Lineage Assumptions */}
            <div
              style={{
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.85rem 1rem',
              }}
            >
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#38bdf8', display: 'inline-block' }}></span>
                Boundary, Lineage &amp; Intensity vs. Total Energy
              </div>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Denominators are strictly Final Assembly (FAL) good units. Numerator combines all 5 plant meters.
                Tariff: <strong style={{ color: 'var(--text-primary)' }}>{lineage.tariff_inr_per_kwh ? `₹${lineage.tariff_inr_per_kwh}/kWh` : '₹8.25/kWh'}</strong> (dataset-derived, status: {lineage.tariff_approval_status || 'UNKNOWN'}).
                Grid emissions: <strong style={{ color: 'var(--text-primary)' }}>{lineage.emissions_factor_kg_co2e_per_kwh || '0.716'} kg CO₂e/kWh</strong>.
                In the historical data, August to October intensity fell (2.0137 → 2.0069 → 2.0056 kWh/good unit) while total electricity rose (658,772 → 660,021 kWh); lower intensity reflects higher good output volume, not verified energy reductions.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
