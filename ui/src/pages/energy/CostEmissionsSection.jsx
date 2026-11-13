import React from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

const AREA_COLOR_MAP = {
  SMT: 'var(--brand-purple)',
  FAL: 'var(--brand-blue)',
  COMPRESSOR: 'var(--chart-cat-4)',
  CHILLER: 'var(--brand-cyan)',
  HVAC: 'var(--brand-orange)',
};

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

export default function CostEmissionsSection({
  energySummary,
  byArea = [],
  summaryAvailable = true,
  areaAvailable = true,
}) {
  const totalCost = hasNumber(energySummary?.total_cost_inr) ? Number(energySummary.total_cost_inr) : null;
  const totalCo2e = hasNumber(energySummary?.total_co2e_kg) ? Number(energySummary.total_co2e_kg) : null;
  const totalCo2eTonnes = totalCo2e === null ? null : totalCo2e / 1000;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Dataset Cost & Estimated Emissions</h3>
          <p className="section-desc">
            Cost and CO₂e values are calculated from dataset inputs; they are not verified utility bills or emissions measurements.
          </p>
        </div>
      </div>

      <div className="cost-emissions-grid">
        {/* Left: Financial Accounting Card */}
        <div className="chart-card cost-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Dataset-calculated cost</h4>
              <span className="chart-card-subtitle">Not a verified utility bill</span>
            </div>
            <div className="cost-total-badge">
              {summaryAvailable && totalCost !== null ? formatCurrency(totalCost) : 'Unavailable'}
            </div>
          </div>

          <div className="breakdown-list">
            {!areaAvailable || !byArea.length ? (
              <div className="chart-empty-state">
                {!areaAvailable ? 'Area cost data is unavailable.' : 'No area cost records were returned.'}
              </div>
            ) : byArea.map((areaItem) => (
              <div key={areaItem.area} className="breakdown-item">
                <div className="breakdown-header">
                  <span className="breakdown-name">
                    <span
                      className="breakdown-dot"
                      style={{ background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-blue)' }}
                    ></span>
                    {areaItem.area || 'Area unavailable'}
                  </span>
                  <span className="breakdown-val font-mono">
                    {hasNumber(areaItem.cost_inr) ? formatCurrency(areaItem.cost_inr) : 'Unavailable'}
                  </span>
                </div>
                <div className="breakdown-bar-track">
                  <div
                    className="breakdown-bar-fill"
                    style={{
                      width: `${hasNumber(areaItem.percentage_of_total) ? Math.min(100, Math.max(0, Number(areaItem.percentage_of_total))) : 0}%`,
                      background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-blue)',
                    }}
                  ></div>
                </div>
                <div className="breakdown-sub">
                  <span>{hasNumber(areaItem.percentage_of_total) ? `${formatPercent(areaItem.percentage_of_total)} of returned energy` : 'Energy share unavailable'}</span>
                  <span>{hasNumber(areaItem.consumption_kwh) ? `${formatNumber(areaItem.consumption_kwh, 0)} kWh` : 'Energy unavailable'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Environmental Impact Card */}
        <div className="chart-card emissions-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Estimated CO₂e</h4>
              <span className="chart-card-subtitle">Calculated using the dataset emission factor</span>
            </div>
            <div className="emissions-total-badge">
              {summaryAvailable && totalCo2eTonnes !== null ? `${formatNumber(totalCo2eTonnes, 2)} t CO₂e` : 'Unavailable'}
            </div>
          </div>

          <div className="breakdown-list">
            {!areaAvailable || !byArea.length ? (
              <div className="chart-empty-state">
                {!areaAvailable ? 'Area emissions data is unavailable.' : 'No area emissions records were returned.'}
              </div>
            ) : byArea.map((areaItem) => {
              const itemTonnes = hasNumber(areaItem.co2e_kg) ? Number(areaItem.co2e_kg) / 1000 : null;
              return (
                <div key={areaItem.area} className="breakdown-item">
                  <div className="breakdown-header">
                    <span className="breakdown-name">
                      <span
                        className="breakdown-dot"
                        style={{ background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-cyan)' }}
                      ></span>
                      {areaItem.area || 'Area unavailable'}
                    </span>
                    <span className="breakdown-val font-mono">
                      {hasNumber(areaItem.co2e_kg) ? `${formatNumber(areaItem.co2e_kg, 2)} kg` : 'Unavailable'}
                    </span>
                  </div>
                  <div className="breakdown-bar-track">
                    <div
                      className="breakdown-bar-fill"
                      style={{
                        width: `${hasNumber(areaItem.percentage_of_total) ? Math.min(100, Math.max(0, Number(areaItem.percentage_of_total))) : 0}%`,
                        background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-cyan)',
                      }}
                    ></div>
                  </div>
                  <div className="breakdown-sub">
                    <span>{hasNumber(areaItem.percentage_of_total) ? `${formatPercent(areaItem.percentage_of_total)} of returned energy` : 'Energy share unavailable'}</span>
                    <span>{itemTonnes !== null ? `${formatNumber(itemTonnes, 2)} t CO₂e` : 'Unavailable'}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Mandatory Data Integrity Callout */}
      <div className="data-integrity-notice-box">
        <div className="integrity-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
        <div className="integrity-content">
          <div className="integrity-title">Source Data Accounting Notice</div>
          <p className="integrity-text">
            Cost is dataset-calculated and may not match the current electricity contract or bill. CO₂e is an estimate based on a dataset emission factor, not a verified emissions measurement. No cost savings or tariff adjustments are inferred here.
          </p>
        </div>
      </div>
    </div>
  );
}

