import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

export default function PowerFactorSection({
  powerFactorData,
  byMeter = [],
  dataAvailable = true,
  meterDataAvailable = true,
}) {
  const avgPf = hasNumber(powerFactorData?.avg_power_factor) ? Number(powerFactorData.avg_power_factor) : null;
  const minPf = hasNumber(powerFactorData?.min_power_factor) ? Number(powerFactorData.min_power_factor) : null;
  const maxPf = hasNumber(powerFactorData?.max_power_factor) ? Number(powerFactorData.max_power_factor) : null;
  const threshold = hasNumber(powerFactorData?.threshold) ? Number(powerFactorData.threshold) : null;
  const totalReadings = hasNumber(powerFactorData?.total_readings) ? Number(powerFactorData.total_readings) : null;
  const lowPfEvents = hasNumber(powerFactorData?.low_pf_events_count)
    ? Number(powerFactorData.low_pf_events_count)
    : null;
  const lowPfPct = hasNumber(powerFactorData?.low_pf_percentage)
    ? Number(powerFactorData.low_pf_percentage)
    : null;

  const hasReadings = totalReadings !== null && totalReadings > 0;
  const isWithinThreshold = hasReadings && lowPfEvents === 0 && threshold !== null;
  const thresholdLabel = threshold === null ? 'unavailable' : threshold.toFixed(2);
  const statusLabel = !dataAvailable
    ? 'Power factor summary request failed.'
    : !powerFactorData
      ? 'No power factor summary was returned.'
      : totalReadings === 0
        ? 'No power factor readings were returned for this period.'
        : totalReadings === null
          ? 'Reading count is unavailable.'
        : lowPfEvents === null || threshold === null
          ? 'Below-threshold evidence or threshold is unavailable.'
          : isWithinThreshold
            ? 'No readings below the returned threshold.'
            : `${formatNumber(lowPfEvents)} readings below the returned threshold.`;

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Power Factor Monitoring</h3>
          <p className="section-desc">
            Returned power factor readings and the application threshold, when provided. This is not a utility-billing assessment.
          </p>
        </div>
        <div className="section-tag-group">
          <span className={`section-tag ${isWithinThreshold ? 'quality' : 'info'}`}>
            {statusLabel}
          </span>
        </div>
      </div>

      {(!dataAvailable || !powerFactorData || totalReadings === 0) && (
        <div className="chart-empty-state">{statusLabel}</div>
      )}

      <div className="pf-overview-grid">
        {/* 4 Summary Metric Cards */}
        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Average Power Factor</span>
            <span className="pf-metric-badge info">
              {avgPf === null || threshold === null
                ? 'Unavailable'
                : avgPf >= threshold ? 'At or Above Threshold' : 'Below Threshold'}
            </span>
          </div>
          <div className="pf-metric-value">{avgPf !== null ? avgPf.toFixed(4) : 'Unavailable'}</div>
          <div className="pf-metric-sub">
            {totalReadings !== null ? `Across ${formatNumber(totalReadings)} returned readings` : 'Reading count unavailable'}
          </div>
        </div>

        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Minimum Observed</span>
            <span className="pf-metric-badge info">
              {minPf === null || threshold === null
                ? 'Unavailable'
                : minPf >= threshold ? 'At or Above Threshold' : 'Below Threshold'}
            </span>
          </div>
          <div className="pf-metric-value">{minPf !== null ? minPf.toFixed(4) : 'Unavailable'}</div>
          <div className="pf-metric-sub">
            {minPf !== null && threshold !== null
              ? `Difference from ${threshold.toFixed(2)} threshold: ${(minPf - threshold).toFixed(4)}`
              : `Configured threshold: ${thresholdLabel}`}
          </div>
        </div>

        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Maximum Observed</span>
            <span className="pf-metric-badge purple">Peak</span>
          </div>
          <div className="pf-metric-value">{maxPf !== null ? maxPf.toFixed(4) : 'Unavailable'}</div>
          <div className="pf-metric-sub">Highest returned reading</div>
        </div>

        <div className="pf-metric-card">
          <div className="pf-metric-top">
            <span className="pf-metric-title">Readings Below Threshold</span>
            <span className={`pf-metric-badge ${isWithinThreshold ? 'success' : 'info'}`}>
              {lowPfEvents === null ? 'Unavailable' : `${formatNumber(lowPfEvents)} readings`}
            </span>
          </div>
          <div className={`pf-metric-value ${isWithinThreshold ? 'text-success' : ''}`}>
            {lowPfEvents !== null ? formatNumber(lowPfEvents) : 'Unavailable'}
          </div>
          <div className="pf-metric-sub">
            {threshold !== null ? `Threshold: PF < ${threshold.toFixed(2)}` : 'Threshold unavailable'}
            {lowPfPct !== null ? ` (${formatPercent(lowPfPct)} of readings)` : ' (percentage unavailable)'}
          </div>
        </div>
      </div>

      {/* Meter-level PF Comparison and Threshold Context */}
      <div className="pf-details-grid">
        {/* Left: Submeter PF Ranking */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Average Power Factor by Submeter</h4>
              <span className="chart-card-subtitle">
                {threshold !== null ? `Returned averages relative to ${threshold.toFixed(2)} threshold` : 'Returned averages; threshold unavailable'}
              </span>
            </div>
          </div>

          <div className="pf-meter-list">
            {!meterDataAvailable || !byMeter.length ? (
              <div className="chart-empty-state">
                {!meterDataAvailable ? 'Meter-level power factor data is unavailable.' : 'No meter records were returned.'}
              </div>
            ) : byMeter.map((m) => {
              const pfVal = hasNumber(m.avg_power_factor) ? Number(m.avg_power_factor) : null;
              const fillPct = pfVal === null
                ? 0
                : Math.min(100, Math.max(0, ((pfVal - 0.85) / (1.0 - 0.85)) * 100));
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
                          title={`Application threshold: ${threshold.toFixed(2)}`}
                        ></div>
                      )}
                      <div
                        className="pf-meter-bar-fill"
                        style={{ width: `${fillPct}%` }}
                      ></div>
                    </div>
                  </div>
                  <div className="pf-meter-val font-mono font-semibold">
                    {pfVal !== null ? pfVal.toFixed(4) : 'Unavailable'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Monitoring Threshold Context */}
        <div className="chart-card pf-compliance-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Power Factor Threshold Context</h4>
              <span className="chart-card-subtitle">Evaluation against application-configured threshold</span>
            </div>
          </div>

          <div className="pf-compliance-content">
            <div className="pf-compliance-badge-large">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
              <span>{statusLabel}</span>
            </div>

            <ul className="pf-compliance-points">
              <li>
                <strong>Threshold Tracking:</strong> {totalReadings !== null ? `${formatNumber(totalReadings)} readings were returned` : 'Reading count is unavailable'}; {lowPfEvents !== null && threshold !== null ? `${formatNumber(lowPfEvents)} were below the ${threshold.toFixed(2)} application threshold` : 'below-threshold evidence is unavailable'}{minPf !== null ? ` (minimum returned value: ${minPf.toFixed(4)})` : ''}.
              </li>
              <li>
                <strong>Billing Tariff Boundary:</strong> Commercial penalty calculations and utility billing surcharges require site-specific utility tariff schedules, which are not configured in this dataset.
              </li>
              <li>
                <strong>Submeter Observations:</strong> Meter averages are shown as returned; capacitor-bank sizing or physical equipment conditions cannot be validated from these values alone.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
