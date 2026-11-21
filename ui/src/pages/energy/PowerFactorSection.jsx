import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

export default function PowerFactorSection({
  powerFactorData,
  byMeter = [],
  dataAvailable = true,
  meterDataAvailable = true,
}) {
  const avgPf = hasNumber(powerFactorData?.avg_power_factor) ? Number(powerFactorData.avg_power_factor) : null;
  const minPf = hasNumber(powerFactorData?.min_power_factor) ? Number(powerFactorData.min_power_factor) : null;
  const maxPf = hasNumber(powerFactorData?.max_power_factor) ? Number(powerFactorData.max_power_factor) : null;
  const threshold = hasNumber(powerFactorData?.threshold) ? Number(powerFactorData.threshold) : 0.90;
  const totalReadings = hasNumber(powerFactorData?.total_readings) ? Number(powerFactorData.total_readings) : null;
  const lowPfEvents = hasNumber(powerFactorData?.low_pf_events_count)
    ? Number(powerFactorData.low_pf_events_count)
    : null;
  const lowPfPct = hasNumber(powerFactorData?.low_pf_percentage)
    ? Number(powerFactorData.low_pf_percentage)
    : null;

  const hasReadings = totalReadings !== null && totalReadings > 0;
  const isWithinThreshold = hasReadings && lowPfEvents === 0 && threshold !== null;
  const statusLabel = !dataAvailable
    ? 'Telemetry unavailable'
    : !powerFactorData || totalReadings === 0
      ? 'No readings returned'
      : isWithinThreshold
        ? `Compliant · 0 readings below ${threshold.toFixed(2)}`
        : `${formatNumber(lowPfEvents)} readings below ${threshold.toFixed(2)}`;

  return (
    <div className="dashboard-section" style={{ marginBottom: '1.25rem' }}>
      <div className="section-header">
        <div className="section-title-group">
          <h3 className="section-title">Power Factor Monitoring</h3>
        </div>
        <div className="section-tag-group">
          <span className={`section-tag ${isWithinThreshold ? 'process' : lowPfEvents > 0 ? 'boundary-warning' : 'info'}`}>
            {statusLabel}
          </span>
        </div>
      </div>

      {(!dataAvailable || !powerFactorData || totalReadings === 0) && (
        <div className="chart-empty-state" style={{ marginBottom: '1rem', minHeight: '120px' }}>
          {!dataAvailable
            ? 'Power factor telemetry is unavailable from the server.'
            : 'No power factor readings returned for the selected filter period.'}
        </div>
      )}

      {/* 4 Summary Metric Cards */}
      <div className="pf-overview-grid">
        {/* Card 1: Average PF */}
        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Average Power Factor</span>
            <span className={`pf-metric-badge ${avgPf !== null && avgPf >= threshold ? 'success' : 'boundary-warning'}`}>
              {avgPf === null ? '—' : avgPf >= threshold ? 'Compliant' : 'Below Threshold'}
            </span>
          </div>
          <div className="pf-metric-value">{avgPf !== null ? avgPf.toFixed(4) : '—'}</div>
          <div className="pf-metric-sub">
            {totalReadings !== null ? `Across ${formatNumber(totalReadings)} hourly readings` : 'Reading count unavailable'}
          </div>
        </div>

        {/* Card 2: Minimum PF */}
        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Minimum Observed</span>
            <span className={`pf-metric-badge ${minPf !== null && minPf >= threshold ? 'success' : 'boundary-warning'}`}>
              {minPf === null ? '—' : minPf >= threshold ? 'Compliant' : 'Below Threshold'}
            </span>
          </div>
          <div className="pf-metric-value">{minPf !== null ? minPf.toFixed(4) : '—'}</div>
          <div className="pf-metric-sub">
            {minPf !== null && threshold !== null
              ? minPf >= threshold
                ? `Exceeds threshold by +${(minPf - threshold).toFixed(4)}`
                : `Deficit: ${(threshold - minPf).toFixed(4)} from threshold`
              : `Threshold: ${threshold.toFixed(2)}`}
          </div>
        </div>

        {/* Card 3: Maximum PF */}
        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Maximum Observed</span>
            <span className="pf-metric-badge purple">Peak</span>
          </div>
          <div className="pf-metric-value">{maxPf !== null ? maxPf.toFixed(4) : '—'}</div>
          <div className="pf-metric-sub">Highest recorded hourly reading</div>
        </div>

        {/* Card 4: Below Threshold */}
        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Readings Below Threshold</span>
            <span className={`pf-metric-badge ${lowPfEvents === 0 ? 'success' : 'boundary-warning'}`}>
              {lowPfEvents === null ? '—' : lowPfEvents === 0 ? 'Zero Events' : `${formatNumber(lowPfEvents)} Events`}
            </span>
          </div>
          <div className={`pf-metric-value ${lowPfEvents === 0 ? 'text-success' : 'text-warning'}`}>
            {lowPfEvents !== null ? formatNumber(lowPfEvents) : '—'}
          </div>
          <div className="pf-metric-sub">
            {threshold !== null ? `Baseline: PF < ${threshold.toFixed(2)}` : 'Threshold: 0.90'}
            {lowPfPct !== null ? ` (${formatPercent(lowPfPct)} of readings)` : ''}
          </div>
        </div>
      </div>

      {/* Meter-level PF Comparison and Threshold Context */}
      <div className="pf-details-grid">
        {/* Left: Submeter PF Ranking */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div className="chart-title-wrap">
              <h4 className="chart-card-title">Average Power Factor by Submeter</h4>
            </div>
            <div className="chart-legend-custom">
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--status-success)' }}></span>
                ≥ {threshold.toFixed(2)}
              </span>
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--brand-orange)' }}></span>
                &lt; {threshold.toFixed(2)}
              </span>
            </div>
          </div>

          <div className="pf-meter-list">
            {!meterDataAvailable || !byMeter.length ? (
              <div className="chart-empty-state" style={{ minHeight: '160px' }}>
                {!meterDataAvailable ? 'Meter power factor data unavailable.' : 'No meter records returned.'}
              </div>
            ) : (
              byMeter.map((m) => {
                const pfVal = hasNumber(m.avg_power_factor) ? Number(m.avg_power_factor) : null;
                const fillPct = pfVal === null
                  ? 0
                  : Math.min(100, Math.max(0, ((pfVal - 0.85) / (1.0 - 0.85)) * 100));
                const isCompliant = pfVal !== null && pfVal >= threshold;

                return (
                  <div key={m.meter_id} className="pf-meter-row">
                    <div className="pf-meter-meta">
                      <span className="font-semibold">{m.meter_id}</span>
                      <span className="text-secondary text-xs">({m.area})</span>
                    </div>
                    <div className="pf-meter-bar-wrap">
                      <div className="pf-meter-bar-track">
                        {threshold !== null && (
                          <div
                            className="pf-threshold-line"
                            style={{ left: `${Math.min(100, Math.max(0, ((threshold - 0.85) / 0.15) * 100))}%` }}
                            title={`Threshold: ${threshold.toFixed(2)}`}
                          ></div>
                        )}
                        <div
                          className={`pf-meter-bar-fill ${isCompliant ? 'compliant' : 'non-compliant'}`}
                          style={{
                            width: `${fillPct}%`,
                            backgroundColor: isCompliant ? 'var(--status-success, #10b981)' : 'var(--brand-orange, #f59e0b)',
                          }}
                        ></div>
                      </div>
                    </div>
                    <div className="pf-meter-val font-mono font-semibold" style={{ color: isCompliant ? 'var(--status-success, #10b981)' : 'var(--brand-orange, #f59e0b)' }}>
                      {pfVal !== null ? pfVal.toFixed(4) : '—'}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Monitoring Threshold Context */}
        <div className="chart-card pf-compliance-card">
          <div className="chart-card-header">
            <div className="chart-title-wrap">
              <h4 className="chart-card-title">Power Factor Compliance Status</h4>
            </div>
          </div>

          <div className="pf-compliance-content">
            <div className={`pf-compliance-badge-large ${isWithinThreshold ? 'badge-success' : 'badge-warning'}`}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                {isWithinThreshold ? (
                  <polyline points="9 12 11 14 15 10" />
                ) : (
                  <>
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </>
                )}
              </svg>
              <span>{statusLabel}</span>
            </div>

            <ul className="pf-compliance-points">
              <li>
                <strong>Threshold Monitoring:</strong> {totalReadings !== null ? `${formatNumber(totalReadings)} hourly intervals evaluated` : 'Telemetry verified'}. {lowPfEvents !== null && lowPfEvents > 0 ? `${formatNumber(lowPfEvents)} intervals dipped below ${threshold.toFixed(2)}` : `Zero intervals below ${threshold.toFixed(2)} baseline`}{minPf !== null ? ` (minimum: ${minPf.toFixed(4)})` : ''}.
              </li>
              <li>
                <strong>Inductive Load Tracking:</strong> All submeters are tracked against baseline. Maintaining PF &ge; {threshold.toFixed(2)} prevents apparent power penalties and improves distribution efficiency.
              </li>
              <li>
                <strong>Commercial Tariffs:</strong> Engineering telemetry directly informs utility surcharge prevention and capacitor bank health.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
