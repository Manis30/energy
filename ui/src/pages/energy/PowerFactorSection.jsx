import React, { useMemo } from 'react';
import { formatNumber } from '../../utils/formatters';
import './PowerFactorSection.css';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

export default function PowerFactorSection({
  powerFactorData,
  byMeter = [],
  dataAvailable = true,
  meterDataAvailable = true,
  selectedShift = 'ALL',
}) {
  const avgPf = hasNumber(powerFactorData?.avg_power_factor) ? Number(powerFactorData.avg_power_factor) : null;
  const minPf = hasNumber(powerFactorData?.min_power_factor) ? Number(powerFactorData.min_power_factor) : null;
  const maxPf = hasNumber(powerFactorData?.max_power_factor) ? Number(powerFactorData.max_power_factor) : null;
  const threshold = hasNumber(powerFactorData?.threshold) ? Number(powerFactorData.threshold) : 0.90;
  const totalReadings = hasNumber(powerFactorData?.total_readings) ? Number(powerFactorData.total_readings) : null;
  const lowPfEvents = hasNumber(powerFactorData?.low_pf_events_count)
    ? Number(powerFactorData.low_pf_events_count)
    : 0;

  const hasReadings = dataAvailable && totalReadings !== null && totalReadings > 0;

  // Prominent headline summary
  const headlineText = !hasReadings
    ? 'No readings available'
    : `${formatNumber(lowPfEvents)} of ${formatNumber(totalReadings)} readings below ${threshold.toFixed(2)}`;

  // Sort lowest average first
  const sortedMeters = useMemo(() => {
    return [...(byMeter || [])].sort((a, b) => {
      const aVal = hasNumber(a.avg_power_factor) ? Number(a.avg_power_factor) : Infinity;
      const bVal = hasNumber(b.avg_power_factor) ? Number(b.avg_power_factor) : Infinity;
      return aVal - bVal;
    });
  }, [byMeter]);

  // Shared Scale configuration: 0.85 to 1.00
  const scaleMin = 0.85;
  const scaleMax = 1.00;
  const scaleSpan = scaleMax - scaleMin;

  const getScalePct = (val) => {
    if (!hasNumber(val)) return 0;
    const num = Number(val);
    return Math.min(100, Math.max(0, ((num - scaleMin) / scaleSpan) * 100));
  };

  const thresholdPct = getScalePct(threshold);

  return (
    <div className="pf-section-card">
      {/* 1. Section Header */}
      <div className="pf-section-header">
        <div className="pf-title-group">
          <h3 className="pf-section-title">Power Factor Monitoring</h3>
          {selectedShift && selectedShift !== 'ALL' && (
            <span className="section-tag process" style={{ fontSize: '11px', padding: '2px 6px' }}>
              Shift {selectedShift}
            </span>
          )}
        </div>
      </div>

      {/* 2. Prominent Headline Summary */}
      <div className="pf-headline-summary-row">
        <div className={`pf-headline-summary ${hasReadings && lowPfEvents > 0 ? 'has-warning' : ''}`}>
          {headlineText}
        </div>
      </div>

      {/* 3. Compact Metrics Strip: Average, Minimum, Maximum (unitless, 4 decimal places) */}
      <div className="pf-metrics-strip">
        <div className="pf-metric-item">
          <span className="pf-metric-label">Average</span>
          <span className="pf-metric-val">{avgPf !== null ? avgPf.toFixed(4) : '—'}</span>
          <span className="pf-metric-sub">
            {hasReadings ? `Across ${formatNumber(totalReadings)} hourly readings` : 'Reading count unavailable'}
          </span>
        </div>

        <div className="pf-metric-item">
          <span className="pf-metric-label">Minimum</span>
          <span className="pf-metric-val">{minPf !== null ? minPf.toFixed(4) : '—'}</span>
          <span className="pf-metric-sub">
            {minPf !== null && threshold !== null
              ? minPf >= threshold
                ? `Above threshold (+${(minPf - threshold).toFixed(4)})`
                : `Deficit: ${(threshold - minPf).toFixed(4)} from threshold`
              : `Threshold: ${threshold.toFixed(2)}`}
          </span>
        </div>

        <div className="pf-metric-item">
          <span className="pf-metric-label">Maximum</span>
          <span className="pf-metric-val">{maxPf !== null ? maxPf.toFixed(4) : '—'}</span>
          <span className="pf-metric-sub">Highest recorded hourly reading</span>
        </div>
      </div>

      {/* 4. Submeter Dot Scale (Sorted Lowest Average First) */}
      <div className="pf-scale-panel">
        <div className="pf-scale-note">
          Submeter averages (headline counts individual readings)
        </div>

        {/* Labeled Axis Header Row */}
        <div className="pf-scale-axis-row">
          <span className="pf-axis-label-col">Submeter</span>
          <div className="pf-scale-ticks">
            <span className="pf-scale-tick" style={{ left: '0%' }}>0.85</span>
            <span
              className="pf-scale-tick is-threshold"
              style={{ left: `${thresholdPct}%` }}
            >
              {threshold.toFixed(2)} Threshold
            </span>
            <span className="pf-scale-tick" style={{ left: `${getScalePct(0.95)}%` }}>0.95</span>
            <span className="pf-scale-tick" style={{ left: '100%' }}>1.00</span>
          </div>
          <span className="pf-axis-val-col">Average</span>
        </div>

        {/* Meter Rows with Dot on Shared Scale */}
        <div className="pf-meter-rows-list">
          {!meterDataAvailable || sortedMeters.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '16px', color: 'var(--text-muted)', fontSize: '13px' }}>
              {!meterDataAvailable ? 'Meter power factor data unavailable.' : 'No meter records returned.'}
            </div>
          ) : (
            sortedMeters.map((m) => {
              const pfVal = hasNumber(m.avg_power_factor) ? Number(m.avg_power_factor) : null;
              const isCompliant = pfVal !== null && pfVal >= threshold;
              const dotLeftPct = getScalePct(pfVal);

              return (
                <div key={m.meter_id} className="pf-meter-dot-row">
                  <div className="pf-meter-name-wrap">
                    <span className="pf-meter-id-text">{m.meter_id}</span>
                    {m.area && (
                      <span className="pf-meter-area-badge">
                        ({m.area})
                      </span>
                    )}
                  </div>

                  {/* Shared Scale Track with Threshold Line and Dot */}
                  <div className="pf-dot-track-wrap">
                    <div className="pf-dot-track-line" />
                    <div
                      className="pf-threshold-indicator-line"
                      style={{ left: `${thresholdPct}%` }}
                      title={`Threshold: ${threshold.toFixed(2)}`}
                    />
                    {pfVal !== null && (
                      <div
                        className={`pf-dot-marker ${isCompliant ? 'compliant' : 'non-compliant'}`}
                        style={{ left: `${dotLeftPct}%` }}
                        title={`${m.meter_id} Average: ${pfVal.toFixed(4)}`}
                      />
                    )}
                  </div>

                  {/* Exact Average Value */}
                  <div className={`pf-meter-val-text ${isCompliant ? '' : 'non-compliant'}`}>
                    {pfVal !== null ? pfVal.toFixed(4) : '—'}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
