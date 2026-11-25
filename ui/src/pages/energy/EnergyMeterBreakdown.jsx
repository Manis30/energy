import React, { useState, useMemo } from 'react';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';
import './EnergyMeterBreakdown.css';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

const METER_COLOR_MAP = {
  'MTR-SMT': 'var(--brand-purple, #6f3dba)',
  'MTR-COMPRESSOR': 'var(--chart-cat-4, #10b981)',
  'MTR-CHILLER': 'var(--brand-cyan, #06b6d4)',
  'MTR-FAL': 'var(--brand-blue, #3b82f6)',
  'MTR-HVAC': 'var(--brand-orange, #f97316)',
};

export default function EnergyMeterBreakdown({ byMeter = [], dataAvailable = true, selectedShift = 'ALL' }) {
  const [expandedMeters, setExpandedMeters] = useState({});

  const toggleMeter = (meterId) => {
    setExpandedMeters((prev) => ({
      ...prev,
      [meterId]: !prev[meterId],
    }));
  };

  const sortedMeters = useMemo(() => {
    return [...(byMeter || [])].sort(
      (a, b) => (hasNumber(b.consumption_kwh) ? Number(b.consumption_kwh) : -Infinity)
        - (hasNumber(a.consumption_kwh) ? Number(a.consumption_kwh) : -Infinity)
    );
  }, [byMeter]);

  const maxConsumption = useMemo(() => {
    return sortedMeters.reduce((max, m) => {
      const val = hasNumber(m.consumption_kwh) ? Number(m.consumption_kwh) : 0;
      return val > max ? val : max;
    }, 0);
  }, [sortedMeters]);

  return (
    <div className="meter-breakdown-card">
      {/* 1. Header with Title and Dynamic Meter Count */}
      <div className="meter-breakdown-header">
        <div className="meter-breakdown-title-group">
          <h3 className="meter-breakdown-title">Energy Consumption by Meter</h3>
          <span className="meter-breakdown-count">
            {dataAvailable ? `${byMeter.length} monitored meters` : 'Meter data unavailable'}
          </span>
          {selectedShift && selectedShift !== 'ALL' && (
            <span className="section-tag process" style={{ fontSize: '11px', padding: '2px 6px' }}>
              Shift {selectedShift}
            </span>
          )}
        </div>
      </div>

      {/* 2. Full-Width Ranked Table */}
      <div className="meter-table-wrap">
        <table className="meter-ranked-table">
          <thead>
            <tr>
              <th className="col-meter">Meter</th>
              <th className="col-right" style={{ minWidth: '150px' }}>Energy consumed (kWh)</th>
              <th className="col-right">Share (%)</th>
              <th className="col-right meter-col-desktop">Peak hourly consumption (kWh)</th>
              <th className="col-right meter-col-desktop">Estimated cost (₹)</th>
              <th className="col-right meter-col-desktop">Average power factor</th>
            </tr>
          </thead>
          <tbody>
            {!dataAvailable || sortedMeters.length === 0 ? (
              <tr>
                <td colSpan={6} className="meter-table-empty">
                  {!dataAvailable ? 'Meter data unavailable' : 'No meter records returned for the selected filter.'}
                </td>
              </tr>
            ) : (
              sortedMeters.map((meter, index) => {
                const isExpanded = !!expandedMeters[meter.meter_id];
                const isTop = index === 0;
                const consumptionVal = hasNumber(meter.consumption_kwh) ? Number(meter.consumption_kwh) : 0;
                const barPct = maxConsumption > 0 ? Math.min(100, Math.max(0, (consumptionVal / maxConsumption) * 100)) : 0;

                return (
                  <React.Fragment key={meter.meter_id}>
                    <tr className={isExpanded ? 'is-expanded' : ''}>
                      <td className="col-meter">
                        <div className="meter-cell-content">
                          <span
                            className="meter-color-indicator"
                            style={{ background: METER_COLOR_MAP[meter.meter_id] || 'var(--brand-purple)' }}
                          />
                          <div>
                            <span className="meter-id-text">{meter.meter_id}</span>
                            {meter.meter_id === 'MTR-COMPRESSOR' && (
                              <div className="meter-sub-note">
                                Compressor electricity (input)
                              </div>
                            )}
                          </div>
                          <button
                            type="button"
                            className="meter-disclosure-btn"
                            aria-expanded={isExpanded}
                            aria-label={`Toggle telemetry details for ${meter.meter_id}`}
                            onClick={() => toggleMeter(meter.meter_id)}
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 20 20"
                              fill="currentColor"
                              style={{
                                transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                                transition: 'transform 0.15s ease',
                              }}
                            >
                              <path
                                fillRule="evenodd"
                                d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
                                clipRule="evenodd"
                              />
                            </svg>
                          </button>
                        </div>
                      </td>

                      <td className="col-right">
                        <div className="meter-energy-cell">
                          <span className="meter-energy-val">
                            {hasNumber(meter.consumption_kwh) ? formatNumber(meter.consumption_kwh, 2) : '—'}
                          </span>
                          <div className="meter-energy-bar-track">
                            <div
                              className={`meter-energy-bar-fill ${isTop ? 'is-highest' : ''}`}
                              style={{ width: `${barPct}%` }}
                            />
                          </div>
                        </div>
                      </td>

                      <td className="col-right">
                        {hasNumber(meter.percentage_of_total) ? formatPercent(meter.percentage_of_total, 2) : '—'}
                      </td>

                      <td className="col-right meter-col-desktop">
                        {hasNumber(meter.peak_kwh) ? formatNumber(meter.peak_kwh, 2) : '—'}
                      </td>

                      <td className="col-right meter-col-desktop">
                        {hasNumber(meter.cost_inr) ? formatCurrency(meter.cost_inr) : '—'}
                      </td>

                      <td className="col-right meter-col-desktop">
                        {hasNumber(meter.avg_power_factor) ? Number(meter.avg_power_factor).toFixed(4) : '—'}
                      </td>
                    </tr>

                    {/* Accessible Row Disclosure for Narrow Screens */}
                    <tr className={`meter-disclosure-row ${isExpanded ? 'is-open' : ''}`}>
                      <td colSpan={3}>
                        <div className="meter-disclosure-content">
                          <div className="meter-disclosure-item">
                            <span className="meter-disclosure-label">Peak hourly consumption</span>
                            <span className="meter-disclosure-val">
                              {hasNumber(meter.peak_kwh) ? `${formatNumber(meter.peak_kwh, 2)} kWh` : '—'}
                            </span>
                          </div>
                          <div className="meter-disclosure-item">
                            <span className="meter-disclosure-label">Estimated cost</span>
                            <span className="meter-disclosure-val">
                              {hasNumber(meter.cost_inr) ? formatCurrency(meter.cost_inr) : '—'}
                            </span>
                          </div>
                          <div className="meter-disclosure-item">
                            <span className="meter-disclosure-label">Average power factor</span>
                            <span className="meter-disclosure-val">
                              {hasNumber(meter.avg_power_factor) ? Number(meter.avg_power_factor).toFixed(4) : '—'}
                            </span>
                          </div>
                        </div>
                      </td>
                    </tr>
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
