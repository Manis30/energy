import React from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from 'recharts';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';

const AREA_COLOR_MAP = {
  SMT: 'var(--brand-purple)',
  FAL: 'var(--brand-blue)',
  COMPRESSOR: 'var(--chart-cat-4)',
  CHILLER: 'var(--brand-cyan)',
  HVAC: 'var(--brand-orange)',
};

function CustomAreaTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.name}</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Category:</span>
          <span className="tooltip-val">{data.category}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Consumption:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.value, 2)} kWh</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Plant Share:</span>
          <span className="tooltip-val">{formatPercent(data.share)}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Cost:</span>
          <span className="tooltip-val">{formatCurrency(data.cost)}</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function EnergyAreaDistribution({ byArea = [] }) {
  // Categorize areas into Process (SMT, FAL) and Utilities (COMPRESSOR, CHILLER, HVAC)
  let processKwh = 0;
  let processCost = 0;
  let utilityKwh = 0;
  let utilityCost = 0;

  const detailedItems = (byArea || []).map((a) => {
    const kwh = Number(a.consumption_kwh);
    const cost = Number(a.cost_inr);
    const isProcess = a.area === 'SMT' || a.area === 'FAL';
    if (isProcess) {
      processKwh += kwh;
      processCost += cost;
    } else {
      utilityKwh += kwh;
      utilityCost += cost;
    }

    let displayName = a.area;
    if (a.area === 'SMT') displayName = 'SMT Lines (Process)';
    else if (a.area === 'FAL') displayName = 'Final Assembly (Process)';
    else if (a.area === 'COMPRESSOR') displayName = 'Air Compressors (Utility)';
    else if (a.area === 'CHILLER') displayName = 'Process Chillers (Utility)';
    else if (a.area === 'HVAC') displayName = 'Cleanroom HVAC (Utility)';

    return {
      name: displayName,
      rawArea: a.area,
      category: isProcess ? 'Manufacturing Process' : 'Facility Utilities',
      isProcess,
      value: kwh,
      share: Number(a.percentage_of_total),
      cost,
      co2e: Number(a.co2e_kg),
    };
  });

  const totalKwh = processKwh + utilityKwh;
  const processShare = totalKwh > 0 ? (processKwh / totalKwh) * 100 : 0;
  const utilityShare = totalKwh > 0 ? (utilityKwh / totalKwh) * 100 : 0;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Energy Consumption by Functional Area</h3>
          <p className="section-desc">
            Segregation of direct manufacturing processes from plant-wide facility utility systems.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag boundary-warning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            Utilities Segregated from Production Lines
          </span>
        </div>
      </div>

      <div className="area-analytics-grid">
        {/* Left: Process vs Utility Split Card */}
        <div className="chart-card area-donut-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Process vs Utilities Share</h4>
              <span className="chart-card-subtitle">
                Manufacturing lines ({processShare.toFixed(1)}%) vs Facility services ({utilityShare.toFixed(1)}%)
              </span>
            </div>
          </div>

          <div className="donut-chart-wrapper">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={detailedItems}
                  cx="50%"
                  cy="50%"
                  innerRadius={65}
                  outerRadius={95}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {detailedItems.map((entry) => (
                    <Cell
                      key={entry.rawArea}
                      fill={AREA_COLOR_MAP[entry.rawArea] || 'var(--brand-purple)'}
                    />
                  ))}
                </Pie>
                <Tooltip content={<CustomAreaTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center-label">
              <span className="donut-center-val">{formatNumber(totalKwh, 0)}</span>
              <span className="donut-center-sub">Total kWh</span>
            </div>
          </div>

          <div className="split-summary-bar">
            <div className="split-bar-track">
              <div
                className="split-bar-fill process"
                style={{ width: `${processShare}%` }}
                title={`Process: ${processShare.toFixed(1)}%`}
              ></div>
              <div
                className="split-bar-fill utility"
                style={{ width: `${utilityShare}%` }}
                title={`Utilities: ${utilityShare.toFixed(1)}%`}
              ></div>
            </div>
            <div className="split-labels-row">
              <span className="split-label-item">
                <span className="split-box process"></span>
                <strong>Process Energy:</strong> {formatPercent(processShare)} ({formatNumber(processKwh, 0)} kWh)
              </span>
              <span className="split-label-item">
                <span className="split-box utility"></span>
                <strong>Facility Utilities:</strong> {formatPercent(utilityShare)} ({formatNumber(utilityKwh, 0)} kWh)
              </span>
            </div>
          </div>
        </div>

        {/* Right: Detailed Area Progress Cards */}
        <div className="chart-card area-details-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Area Breakdown & Accounting Audit</h4>
              <span className="chart-card-subtitle">Verified meter-level energy distribution</span>
            </div>
          </div>

          <div className="area-cards-list">
            {detailedItems.map((item) => (
              <div key={item.rawArea} className="area-item-row">
                <div className="area-item-top">
                  <div className="area-name-wrap">
                    <span
                      className="area-dot"
                      style={{ background: AREA_COLOR_MAP[item.rawArea] || 'var(--brand-purple)' }}
                    ></span>
                    <span className="area-name">{item.name}</span>
                  </div>
                  <div className="area-metrics-right">
                    <span className="area-val">{formatNumber(item.value, 2)} kWh</span>
                    <span className="area-share">({formatPercent(item.share)})</span>
                  </div>
                </div>
                <div className="area-progress-track">
                  <div
                    className="area-progress-bar"
                    style={{
                      width: `${item.share}%`,
                      background: AREA_COLOR_MAP[item.rawArea] || 'var(--brand-purple)',
                    }}
                  ></div>
                </div>
                <div className="area-item-bottom">
                  <span>Spend: {formatCurrency(item.cost)}</span>
                  <span>Emissions: {formatNumber(item.co2e, 2)} kg CO₂e</span>
                </div>
              </div>
            ))}
          </div>

          <div className="segregation-callout-box">
            <div className="callout-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <span>Deterministic Accounting Boundary</span>
            </div>
            <p className="callout-text">
              In accordance with ISO 50001 energy baseline standards, facility utilities (HVAC, Chillers, Compressed Air) represent centralized plant overhead and must not be allocated to production lines or specific product models. Only dedicated process meters (MTR-SMT, MTR-FAL) feed line-level Specific Energy Consumption (SEC).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
