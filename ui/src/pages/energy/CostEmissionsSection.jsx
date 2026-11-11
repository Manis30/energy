import React from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

const AREA_COLOR_MAP = {
  SMT: 'var(--brand-purple)',
  FAL: 'var(--brand-blue)',
  COMPRESSOR: 'var(--chart-cat-4)',
  CHILLER: 'var(--brand-cyan)',
  HVAC: 'var(--brand-orange)',
};

export default function CostEmissionsSection({ energySummary, byArea = [] }) {
  const totalCost = energySummary ? Number(energySummary.total_cost_inr) : 16154228.24;
  const totalCo2e = energySummary ? Number(energySummary.total_co2e_kg) : 1401991.13;
  const totalCo2eTonnes = totalCo2e / 1000;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Cost & Carbon Emissions Accounting</h3>
          <p className="section-desc">
            Direct financial and carbon footprint breakdown derived strictly from validated source dataset constants.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">Constant Tariff: ₹8.25/kWh</span>
          <span className="section-tag process">Grid Factor: 0.716 kg CO₂e/kWh</span>
        </div>
      </div>

      <div className="cost-emissions-grid">
        {/* Left: Financial Accounting Card */}
        <div className="chart-card cost-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Total Electricity Spend</h4>
              <span className="chart-card-subtitle">Calculated strictly at fixed ₹8.25/kWh</span>
            </div>
            <div className="cost-total-badge">
              {formatCurrency(totalCost)}
            </div>
          </div>

          <div className="breakdown-list">
            {(byArea || []).map((areaItem) => (
              <div key={areaItem.area} className="breakdown-item">
                <div className="breakdown-header">
                  <span className="breakdown-name">
                    <span
                      className="breakdown-dot"
                      style={{ background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-blue)' }}
                    ></span>
                    {areaItem.area}
                  </span>
                  <span className="breakdown-val font-mono">{formatCurrency(areaItem.cost_inr)}</span>
                </div>
                <div className="breakdown-bar-track">
                  <div
                    className="breakdown-bar-fill"
                    style={{
                      width: `${areaItem.percentage_of_total}%`,
                      background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-blue)',
                    }}
                  ></div>
                </div>
                <div className="breakdown-sub">
                  <span>{formatPercent(areaItem.percentage_of_total)} of total spend</span>
                  <span>{formatNumber(areaItem.consumption_kwh, 0)} kWh</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Environmental Impact Card */}
        <div className="chart-card emissions-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Greenhouse Gas Emissions</h4>
              <span className="chart-card-subtitle">Grid factor: 0.716 kg CO₂e / kWh</span>
            </div>
            <div className="emissions-total-badge">
              {formatNumber(totalCo2eTonnes, 2)} t CO₂e
            </div>
          </div>

          <div className="breakdown-list">
            {(byArea || []).map((areaItem) => {
              const itemTonnes = Number(areaItem.co2e_kg) / 1000;
              return (
                <div key={areaItem.area} className="breakdown-item">
                  <div className="breakdown-header">
                    <span className="breakdown-name">
                      <span
                        className="breakdown-dot"
                        style={{ background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-cyan)' }}
                      ></span>
                      {areaItem.area}
                    </span>
                    <span className="breakdown-val font-mono">{formatNumber(areaItem.co2e_kg, 2)} kg</span>
                  </div>
                  <div className="breakdown-bar-track">
                    <div
                      className="breakdown-bar-fill"
                      style={{
                        width: `${areaItem.percentage_of_total}%`,
                        background: AREA_COLOR_MAP[areaItem.area] || 'var(--brand-cyan)',
                      }}
                    ></div>
                  </div>
                  <div className="breakdown-sub">
                    <span>{formatPercent(areaItem.percentage_of_total)} of emissions</span>
                    <span>{formatNumber(itemTonnes, 2)} metric tons</span>
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
            Electricity spend is computed using the constant contractual tariff rate of <strong>₹8.25 / kWh</strong> recorded in the source factory dataset. This is a constant rate and is not subject to time-of-day or peak-demand billing structures in the current telemetry. Carbon emissions are calculated using the source grid emission factor of <strong>0.716 kg CO₂e / kWh</strong>. No hypothetical cost savings, tariff adjustments, or unverified financial projections are introduced.
          </p>
        </div>
      </div>
    </div>
  );
}

