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

const PROCESS_AREAS = new Set(['SMT', 'FAL']);
const UTILITY_AREAS = new Set(['COMPRESSOR', 'CHILLER', 'HVAC']);
const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

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
          <span className="tooltip-val font-bold">
            {hasNumber(data.value) ? `${formatNumber(data.value, 2)} kWh` : 'Unavailable'}
          </span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Share:</span>
          <span className="tooltip-val">{hasNumber(data.share) ? formatPercent(data.share) : 'Unavailable'}</span>
        </div>
        {hasNumber(data.cost) && (
          <div className="tooltip-row">
            <span className="tooltip-label">Dataset Cost:</span>
            <span className="tooltip-val">{formatCurrency(data.cost)}</span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

export default function EnergyAreaDistribution({ byArea = [], dataAvailable = true }) {
  const detailedItems = (byArea || []).map((a) => {
    const isProcess = PROCESS_AREAS.has(a.area);
    const isUtility = UTILITY_AREAS.has(a.area);

    let displayName = a.area || 'Area unavailable';
    if (a.area === 'SMT') displayName = 'SMT Lines';
    else if (a.area === 'FAL') displayName = 'Final Assembly';
    else if (a.area === 'COMPRESSOR') displayName = 'Air Compressors';
    else if (a.area === 'CHILLER') displayName = 'Chillers';
    else if (a.area === 'HVAC') displayName = 'Cleanroom HVAC';

    return {
      name: displayName,
      rawArea: a.area,
      category: isProcess ? 'Process' : isUtility ? 'Utility' : 'Other',
      isProcess,
      isUtility,
      value: hasNumber(a.consumption_kwh) ? Number(a.consumption_kwh) : null,
      share: hasNumber(a.percentage_of_total) ? Number(a.percentage_of_total) : null,
      cost: hasNumber(a.cost_inr) ? Number(a.cost_inr) : null,
      co2e: hasNumber(a.co2e_kg) ? Number(a.co2e_kg) : null,
    };
  });

  const hasProcessArea = detailedItems.some((item) => item.isProcess);
  const hasUtilityArea = detailedItems.some((item) => item.isUtility);
  const canAggregate = detailedItems.length > 0
    && hasProcessArea
    && hasUtilityArea
    && detailedItems.every((item) => (item.isProcess || item.isUtility) && hasNumber(item.value));
  const processKwh = canAggregate
    ? detailedItems.filter((item) => item.isProcess).reduce((sum, item) => sum + item.value, 0)
    : null;
  const utilityKwh = canAggregate
    ? detailedItems.filter((item) => item.isUtility).reduce((sum, item) => sum + item.value, 0)
    : null;
  const totalKwh = canAggregate ? processKwh + utilityKwh : null;
  const processShare = totalKwh > 0 ? (processKwh / totalKwh) * 100 : null;
  const utilityShare = totalKwh > 0 ? (utilityKwh / totalKwh) * 100 : null;
  const canRenderSplit = dataAvailable && canAggregate && totalKwh > 0;

  return (
    <div className="dashboard-section" style={{ marginBottom: '1.25rem' }}>
      <div className="section-header">
        <div className="section-title-group">
          <h3 className="section-title">Energy Consumption by Functional Area</h3>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">
            {dataAvailable ? `${byArea.length} functional areas` : 'Area data unavailable'}
          </span>
          <span className="section-tag boundary-warning">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            Utilities Segregated from Production
          </span>
        </div>
      </div>

      <div className="area-analytics-grid">
        {/* Left: Process vs Utility Split Card */}
        <div className="chart-card area-donut-card">
          <div className="chart-card-header">
            <div className="chart-title-wrap">
              <h4 className="chart-card-title">Functional Area Distribution</h4>
            </div>
          </div>

          <div
            className="donut-chart-wrapper"
            role="group"
            aria-label="Area energy distribution donut chart in kilowatt-hours"
          >
            {!dataAvailable || detailedItems.length === 0 || !canAggregate || totalKwh === 0 ? (
              <div className="chart-empty-state" style={{ minHeight: '210px' }}>
                {!dataAvailable
                  ? 'Area distribution data is unavailable from the server.'
                  : detailedItems.length === 0
                    ? 'No area records returned for the selected filter period.'
                    : 'Area records returned without valid classified energy values.'}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={210}>
                <PieChart>
                  <Pie
                    data={detailedItems}
                    cx="50%"
                    cy="50%"
                    innerRadius={58}
                    outerRadius={88}
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
            )}
            {canRenderSplit && (
              <div className="donut-center-label">
                <span className="donut-center-val">{formatNumber(totalKwh, 0)}</span>
                <span className="donut-center-sub">Total Area kWh</span>
              </div>
            )}
          </div>

          {canAggregate && dataAvailable && (
            <div className="split-summary-bar">
              <div className="split-bar-track">
                <div
                  className="split-bar-fill process"
                  style={{ width: `${processShare || 0}%` }}
                  title={processShare === null ? 'Process share unavailable' : `Process: ${processShare.toFixed(1)}%`}
                ></div>
                <div
                  className="split-bar-fill utility"
                  style={{ width: `${utilityShare || 0}%` }}
                  title={utilityShare === null ? 'Utility share unavailable' : `Utilities: ${utilityShare.toFixed(1)}%`}
                ></div>
              </div>
              <div className="split-labels-row">
                <span className="split-label-item">
                  <span className="split-box process"></span>
                  <strong>Process:</strong> {processShare === null ? 'Unavailable' : `${formatPercent(processShare)} (${formatNumber(processKwh, 0)} kWh)`}
                </span>
                <span className="split-label-item">
                  <span className="split-box utility"></span>
                  <strong>Utilities:</strong> {utilityShare === null ? 'Unavailable' : `${formatPercent(utilityShare)} (${formatNumber(utilityKwh, 0)} kWh)`}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right: Detailed Area Progress Cards */}
        <div className="chart-card area-details-card">
          <div className="chart-card-header">
            <div className="chart-title-wrap">
              <h4 className="chart-card-title">Functional Area Breakdown</h4>
            </div>
          </div>

          <div className="area-cards-list">
            {!dataAvailable || detailedItems.length === 0 ? (
              <div className="chart-empty-state" style={{ minHeight: '180px' }}>
                {!dataAvailable ? 'Area breakdown data is unavailable.' : 'No area records returned.'}
              </div>
            ) : (
              detailedItems.map((item) => (
                <div key={item.rawArea} className="area-item-row">
                  <div className="area-item-top">
                    <div className="area-name-wrap">
                      <span
                        className="area-dot"
                        style={{ background: AREA_COLOR_MAP[item.rawArea] || 'var(--brand-purple)' }}
                      ></span>
                      <span className="area-name font-semibold">{item.name}</span>
                      <span className={`area-category-badge ${item.isProcess ? 'process' : item.isUtility ? 'utility' : ''}`}>
                        {item.category}
                      </span>
                    </div>
                    <div className="area-metrics-right">
                      <span className="area-val font-mono">{hasNumber(item.value) ? `${formatNumber(item.value, 1)} kWh` : '—'}</span>
                      <span className="area-share text-secondary">({hasNumber(item.share) ? formatPercent(item.share) : '—'})</span>
                    </div>
                  </div>
                  <div className="area-progress-track">
                    <div
                      className="area-progress-bar"
                      style={{
                        width: `${hasNumber(item.share) ? Math.min(100, Math.max(0, item.share)) : 0}%`,
                        background: AREA_COLOR_MAP[item.rawArea] || 'var(--brand-purple)',
                      }}
                    ></div>
                  </div>
                  <div className="area-item-bottom">
                    <span>Est. Cost: {hasNumber(item.cost) ? formatCurrency(item.cost) : '—'}</span>
                    <span>CO₂e: {hasNumber(item.co2e) ? `${formatNumber(item.co2e, 1)} kg` : '—'}</span>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="segregation-callout-box">
            <div className="callout-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>Deterministic Accounting Boundary</span>
            </div>
            <p className="callout-text">
              Facility utility systems (chillers, compressors, cleanroom HVAC) are measured independently from production lines without arbitrary allocation.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
