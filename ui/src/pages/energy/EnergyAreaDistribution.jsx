import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from 'recharts';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';
import './EnergyAreaDistribution.css';

const AREA_COLOR_MAP = {
  SMT: 'var(--brand-purple, #6f3dba)',
  FAL: 'var(--brand-blue, #3b82f6)',
  COMPRESSOR: 'var(--chart-cat-4, #10b981)',
  CHILLER: 'var(--brand-cyan, #06b6d4)',
  HVAC: 'var(--brand-orange, #f97316)',
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
            {hasNumber(data.value) ? `${formatNumber(data.value, 1)} kWh` : 'Unavailable'}
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

export default function EnergyAreaDistribution({ byArea = [], dataAvailable = true, selectedShift = 'ALL' }) {
  const [expandedAreas, setExpandedAreas] = useState({});

  const toggleExpand = (rawArea) => {
    setExpandedAreas((prev) => ({
      ...prev,
      [rawArea]: !prev[rawArea],
    }));
  };

  const detailedItems = useMemo(() => {
    return (byArea || []).map((a) => {
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
  }, [byArea]);

  // Derived top area for dynamic takeaway
  const topArea = useMemo(() => {
    if (!detailedItems || detailedItems.length === 0) return null;
    const valid = detailedItems.filter((item) => hasNumber(item.value));
    if (valid.length === 0) return null;
    return valid.reduce((max, item) => (item.value > max.value ? item : max), valid[0]);
  }, [detailedItems]);

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
    <div className="area-section-card">
      {/* 1. Header with Heading, Count, and Dynamic Takeaway */}
      <div className="area-section-header">
        <div className="area-title-row">
          <div className="area-title-group">
            <h3 className="area-section-title">Energy use by area</h3>
            <span className="area-count-badge">
              {dataAvailable ? `${byArea.length} functional areas` : 'Area data unavailable'}
            </span>
            {selectedShift && selectedShift !== 'ALL' && (
              <span className="section-tag process" style={{ fontSize: '11px', padding: '2px 6px' }}>
                Shift {selectedShift}
              </span>
            )}
          </div>
        </div>

        {/* Dynamic takeaway derived from filtered data */}
        {topArea && hasNumber(topArea.share) && (
          <p className="area-takeaway-text">
            <strong>{topArea.name}</strong> used the most electricity: {formatPercent(topArea.share)} of the total.
          </p>
        )}
      </div>

      {/* 2. Content Grid: Donut + Split on Left, Table on Right */}
      <div className="area-layout-grid">
        {/* Left Column: Donut & Process/Utility Split */}
        <div className="area-donut-col">
          <div
            className="area-donut-wrapper"
            role="group"
            aria-label="Area energy distribution donut chart in kilowatt-hours"
          >
            {!dataAvailable || detailedItems.length === 0 || !canAggregate || totalKwh === 0 ? (
              <div className="chart-empty-state" style={{ height: '180px', padding: '12px' }}>
                {!dataAvailable
                  ? 'Area distribution data unavailable.'
                  : detailedItems.length === 0
                    ? 'No area records returned.'
                    : 'Records without classified energy.'}
              </div>
            ) : (
              <ResponsiveContainer width={180} height={180}>
                <PieChart width={180} height={180}>
                  <Pie
                    data={detailedItems}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={2}
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
                <span className="donut-center-sub">kWh</span>
              </div>
            )}
          </div>

          {/* Process / Utilities Split Bar directly below Donut */}
          {canAggregate && dataAvailable && (
            <div className="split-summary-bar">
              <div className="split-bar-track">
                <div
                  className="split-bar-fill process"
                  style={{ width: `${processShare || 0}%` }}
                  title={processShare === null ? 'Process share unavailable' : `Process: ${processShare.toFixed(1)}%`}
                />
                <div
                  className="split-bar-fill utility"
                  style={{ width: `${utilityShare || 0}%` }}
                  title={utilityShare === null ? 'Utility share unavailable' : `Utilities: ${utilityShare.toFixed(1)}%`}
                />
              </div>
              <div className="split-labels-stack">
                <div className="split-label-item">
                  <span className="split-box process" />
                  <span className="split-label-text">
                    <strong>Process:</strong> {processShare === null ? '—' : `${formatPercent(processShare)} (${formatNumber(processKwh, 0)} kWh)`}
                  </span>
                </div>
                <div className="split-label-item">
                  <span className="split-box utility" />
                  <span className="split-label-text">
                    <strong>Utilities:</strong> {utilityShare === null ? '—' : `${formatPercent(utilityShare)} (${formatNumber(utilityKwh, 0)} kWh)`}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Compact Table with Thin Dividers */}
        <div className="area-breakdown-col">
          <div className="area-table-wrapper">
            <table className="area-table">
              <thead>
                <tr>
                  <th className="th-area">Area</th>
                  <th className="th-type">Type</th>
                  <th className="th-kwh">Energy (kWh)</th>
                  <th className="th-share">Share</th>
                  <th className="th-action" />
                </tr>
              </thead>
              <tbody>
                {!dataAvailable || detailedItems.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '16px', color: 'var(--text-muted)' }}>
                      No area records returned for the selected filter.
                    </td>
                  </tr>
                ) : (
                  detailedItems.map((item) => {
                    const isExpanded = !!expandedAreas[item.rawArea];
                    return (
                      <React.Fragment key={item.rawArea}>
                        <tr
                          className={`area-row ${isExpanded ? 'is-expanded' : ''}`}
                          onClick={() => toggleExpand(item.rawArea)}
                          role="button"
                          tabIndex={0}
                          aria-expanded={isExpanded}
                          style={{ cursor: 'pointer' }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              toggleExpand(item.rawArea);
                            }
                          }}
                        >
                          <td>
                            <div className="td-area">
                              <span
                                className="area-dot"
                                style={{ background: AREA_COLOR_MAP[item.rawArea] || 'var(--brand-purple)' }}
                              />
                              <span className="area-name">{item.name}</span>
                            </div>
                          </td>
                          <td>
                            <span className={`area-type-pill ${item.isProcess ? 'process' : item.isUtility ? 'utility' : ''}`}>
                              {item.category}
                            </span>
                          </td>
                          <td className="td-kwh">
                            {hasNumber(item.value) ? formatNumber(item.value, 1) : '—'}
                          </td>
                          <td className="td-share">
                            {hasNumber(item.share) ? formatPercent(item.share) : '—'}
                          </td>
                          <td className="td-action">
                            <button
                              type="button"
                              className="area-disclosure-btn"
                              aria-label={`${isExpanded ? 'Collapse' : 'Expand'} details for ${item.name}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleExpand(item.rawArea);
                              }}
                            >
                              <svg
                                width="12"
                                height="12"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2.2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                className={`area-chevron ${isExpanded ? 'expanded' : ''}`}
                              >
                                <polyline points="6 9 12 15 18 9" />
                              </svg>
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="area-detail-row">
                            <td colSpan={5}>
                              <div className="area-disclosure-detail">
                                <span className="detail-item">
                                  <span className="detail-label">Est. Cost:</span>{' '}
                                  <span className="detail-val">{hasNumber(item.cost) ? formatCurrency(item.cost) : '—'}</span>
                                </span>
                                <span className="detail-separator">·</span>
                                <span className="detail-item">
                                  <span className="detail-label">Emissions:</span>{' '}
                                  <span className="detail-val">{hasNumber(item.co2e) ? `${formatNumber(item.co2e, 1)} kg CO₂e` : '—'}</span>
                                </span>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Explanation moved inside "How areas are counted" disclosure */}
          <details className="area-accounting-disclosure">
            <summary className="area-accounting-summary">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>How areas are counted · Utilities segregated from production</span>
            </summary>
            <p className="area-accounting-text">
              Facility utility systems (air compressors, chillers, cleanroom HVAC) are measured independently from production lines without arbitrary allocation, ensuring transparent operational visibility into process vs. utility loads.
            </p>
          </details>
        </div>
      </div>
    </div>
  );
}
