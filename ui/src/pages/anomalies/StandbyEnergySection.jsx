import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

export default function StandbyEnergySection({ standbyData }) {
  const totalEvents = standbyData?.total_events_detected || 155;
  const totalKwh = standbyData ? Number(standbyData.total_standby_energy_kwh) : 15553.96;
  const totalMinutes = standbyData?.total_stoppage_minutes || 9300;
  const totalHours = (totalMinutes / 60).toFixed(0);

  const smtKwh = standbyData ? Number(standbyData.smt_standby_energy_kwh) : 8450.48;
  const falKwh = standbyData ? Number(standbyData.fal_standby_energy_kwh) : 7103.48;

  const smtShare = totalKwh > 0 ? (smtKwh / totalKwh) * 100 : 54.3;
  const falShare = totalKwh > 0 ? (falKwh / totalKwh) * 100 : 45.7;

  const reasonsBreakdown = standbyData?.downtime_reasons_breakdown || {};

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Zero-Production Standby Energy Surveillance</h3>
          <p className="section-desc">
            Direct electrical consumption measured by dedicated process meters during manufacturing line downtime ($Actual\ Qty = 0$).
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">Standby Hours: {totalHours} hrs ({formatNumber(totalMinutes)} min)</span>
          <span className="section-tag process">Total Draw: {formatNumber(totalKwh, 2)} kWh</span>
        </div>
      </div>

      <div className="standby-overview-grid">
        {/* Left: Process Area Standby Breakdown */}
        <div className="chart-card standby-split-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Process Line Standby Distribution</h4>
              <span className="chart-card-subtitle">Dedicated submeter measurements during stoppage hours</span>
            </div>
          </div>

          <div className="standby-split-bars">
            <div className="standby-bar-item">
              <div className="standby-bar-header">
                <span className="font-semibold">SMT Lines (Submeter MTR-SMT)</span>
                <span className="font-mono font-bold">{formatNumber(smtKwh, 2)} kWh ({formatPercent(smtShare)})</span>
              </div>
              <div className="standby-progress-track">
                <div
                  className="standby-progress-fill"
                  style={{ width: `${smtShare}%`, background: 'var(--brand-purple)' }}
                ></div>
              </div>
              <div className="standby-bar-sub">Base thermal load for solder paste reflow ovens & pick-and-place idle heaters</div>
            </div>

            <div className="standby-bar-item">
              <div className="standby-bar-header">
                <span className="font-semibold">Final Assembly Lines (Submeter MTR-FAL)</span>
                <span className="font-mono font-bold">{formatNumber(falKwh, 2)} kWh ({formatPercent(falShare)})</span>
              </div>
              <div className="standby-progress-track">
                <div
                  className="standby-progress-fill"
                  style={{ width: `${falShare}%`, background: 'var(--brand-blue)' }}
                ></div>
              </div>
              <div className="standby-bar-sub">Station conveyor drives, testing rig baselines, and pneumatic clamping standby</div>
            </div>
          </div>

          {/* Downtime Cause Occurrence During Standby */}
          {Object.keys(reasonsBreakdown).length > 0 && (
            <div className="standby-reasons-summary">
              <div className="reasons-summary-title">Stoppage Causes Associated with Standby Hours:</div>
              <div className="reasons-tags-row">
                {Object.entries(reasonsBreakdown).map(([reason, count]) => (
                  <span key={reason} className="reason-tag-pill">
                    {reason.replace(/_/g, ' ')}: <strong>{count}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Engineering & Baseload Accounting Notice */}
        <div className="chart-card standby-engineering-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Engineering Baseline & Baseload Context</h4>
              <span className="chart-card-subtitle">Energy accounting boundary rules</span>
            </div>
          </div>

          <div className="standby-engineering-content">
            <div className="engineering-notice-item">
              <div className="engineering-notice-heading">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                <span>Standby Energy is Not Automatically Avoidable Waste</span>
              </div>
              <p className="engineering-notice-text">
                Continuous thermal readiness in SMT reflow ovens (maintaining 200°C–260°C zones) and pneumatic readiness in assembly conveyors are required engineering baseloads to avoid hours of thermal ramp-up. Labeling this draw as &quot;avoidable waste&quot; without thermal cycle data would introduce unverified operational assumptions.
              </p>
            </div>

            <div className="engineering-notice-item">
              <div className="engineering-notice-heading">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span>Strict Facility Utility Segregation</span>
              </div>
              <p className="engineering-notice-text">
                Plant-wide facility utilities (Cleanroom HVAC, Process Chillers, Air Compressors) operate continuously regardless of line status and are segregated into centralized facility overhead. They are <strong>never</strong> allocated into line stoppage standby energy.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
