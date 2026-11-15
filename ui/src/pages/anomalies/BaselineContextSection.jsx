import React from 'react';
import { formatDateTime } from '../../utils/formatters';

export default function BaselineContextSection({ statisticalData, rollingData, analysisPeriod }) {
  // Statistical baseline metrics
  const statBaselinePeriod = statisticalData?.baseline_period;
  const statEvalPeriod = statisticalData?.evaluation_period || analysisPeriod;
  const lookbackDays = statisticalData?.lookback_days ?? statBaselinePeriod?.lookback_days ?? 30;
  const eligibleGroupsCount = statisticalData?.eligible_groups_count ?? null;
  const insufficientGroups = statisticalData?.insufficient_observations_groups || [];
  const zeroVarGroups = statisticalData?.zero_variance_groups || [];
  const minObs = statisticalData?.min_observations ?? 10;

  // Rolling baseline metrics
  const rollingEvalPeriod = rollingData?.evaluation_period || analysisPeriod;
  const windowHours = rollingData?.window_size_hours ?? 24;
  const rollingMinObs = rollingData?.min_observations ?? 12;
  const totalEvaluated = rollingData?.total_evaluated_observations ?? null;
  const insufficientHistoryCount = rollingData?.insufficient_history_count ?? null;
  const zeroVarCount = rollingData?.zero_variance_count ?? null;
  const rollingAnomaliesCount = rollingData?.total_anomalies_detected ?? null;
  const insufficientMeters = rollingData?.insufficient_history_meters || [];
  const zeroVarMeters = rollingData?.zero_variance_meters || [];

  return (
    <section className="alert-baseline-section" aria-label="Historical Baseline Surveillance Diagnostics">
      <div className="baseline-context-grid">
        {/* Card 1: Statistical Z-Score Baseline & Groups */}
        <div className="baseline-context-card">
          <div className="baseline-card-header">
            <div>
              <span className="baseline-card-eyebrow">Statistical Z-Score Baseline</span>
              <h3 className="baseline-card-title">Historical Baseline &amp; Evaluation Periods</h3>
            </div>
            <span className="baseline-card-badge">Strictly Historical ({lookbackDays}d Lookback)</span>
          </div>

          <div className="baseline-periods-grid">
            <div className="baseline-period-box evaluation">
              <span className="period-box-label">Evaluation Period (Observed)</span>
              <strong className="period-box-val">
                {statEvalPeriod?.start_time && statEvalPeriod?.end_time
                  ? `${formatDateTime(statEvalPeriod.start_time)} → ${formatDateTime(statEvalPeriod.end_time)}`
                  : 'Unavailable'}
              </strong>
              <span className="period-box-sub">Observations analyzed for statistical deviations</span>
            </div>

            <div className="baseline-period-box historical">
              <span className="period-box-label">Historical Baseline Window (Sample)</span>
              <strong className="period-box-val">
                {statBaselinePeriod?.start_time && statBaselinePeriod?.end_time
                  ? `${formatDateTime(statBaselinePeriod.start_time)} → ${formatDateTime(statBaselinePeriod.end_time)}`
                  : 'Unavailable'}
              </strong>
              <span className="period-box-sub">Strictly prior history ({lookbackDays} days); current evaluation excluded</span>
            </div>
          </div>

          <div className="baseline-group-diagnostics">
            <div className="baseline-stat-row">
              <span className="stat-label">Eligible Meter Groups Evaluated:</span>
              <strong className="stat-val font-mono">
                {eligibleGroupsCount !== null ? eligibleGroupsCount.toLocaleString('en-IN') : 'Unavailable'}
              </strong>
            </div>

            {/* Insufficient-History Groups */}
            <div className="baseline-group-block">
              <div className="baseline-group-heading">
                <span className="group-title">Insufficient-History Groups ({insufficientGroups.length}):</span>
                {insufficientGroups.length > 0 && (
                  <span className="status-pill status-unavailable">Baseline Unavailable</span>
                )}
              </div>
              {insufficientGroups.length > 0 ? (
                <>
                  <div className="baseline-group-tags">
                    {insufficientGroups.map((grp) => (
                      <span key={grp} className="baseline-tag badge-insufficient" title="Baseline unavailable: Less than minimum required observations in lookback window">
                        {grp} <small>(&lt; {minObs} obs)</small>
                      </span>
                    ))}
                  </div>
                  <p className="baseline-notice-text">
                    <strong>Unavailable Baseline Notice:</strong> Observations for these groups are excluded from Z-score evaluation due to insufficient prior historical samples in the lookback period. This indicates an <em>unavailable baseline</em>, not normal energy consumption.
                  </p>
                </>
              ) : (
                <span className="baseline-empty-text">None (All active meter groups meet the {minObs}-observation baseline threshold)</span>
              )}
            </div>

            {/* Zero-Variance Groups */}
            <div className="baseline-group-block">
              <div className="baseline-group-heading">
                <span className="group-title">Zero-Variance Groups ({zeroVarGroups.length}):</span>
                {zeroVarGroups.length > 0 && (
                  <span className="status-pill status-zerovar">Baseline Unavailable</span>
                )}
              </div>
              {zeroVarGroups.length > 0 ? (
                <>
                  <div className="baseline-group-tags">
                    {zeroVarGroups.map((grp) => (
                      <span key={grp} className="baseline-tag badge-zerovar" title="Baseline unavailable: Standard deviation is zero in lookback window">
                        {grp} <small>(σ = 0 kWh)</small>
                      </span>
                    ))}
                  </div>
                  <p className="baseline-notice-text">
                    <strong>Unavailable Baseline Notice:</strong> Historical sample standard deviation is zero for these groups. Statistical Z-scores cannot divide by zero; these groups are excluded from outlier flagging.
                  </p>
                </>
              ) : (
                <span className="baseline-empty-text">None (All active meter groups exhibit non-zero historical variance)</span>
              )}
            </div>
          </div>
        </div>

        {/* Card 2: Rolling Baseline Surveillance */}
        <div className="baseline-context-card">
          <div className="baseline-card-header">
            <div>
              <span className="baseline-card-eyebrow">Rolling-Baseline Surveillance</span>
              <h3 className="baseline-card-title">Dynamic Window Diagnostics</h3>
            </div>
            <span className="baseline-card-badge">Moving {windowHours}h Window (Self-Excluded)</span>
          </div>

          <div className="rolling-kpis-grid">
            <div className="rolling-kpi-card">
              <span className="kpi-label">Configured Window</span>
              <strong className="kpi-val font-mono">{windowHours} hours</strong>
              <span className="kpi-sub">Preceding duration (min {rollingMinObs} obs)</span>
            </div>
            <div className="rolling-kpi-card">
              <span className="kpi-label">Evaluated Observations</span>
              <strong className="kpi-val font-mono">
                {totalEvaluated !== null ? totalEvaluated.toLocaleString('en-IN') : 'Unavailable'}
              </strong>
              <span className="kpi-sub">Hourly readings in evaluation window</span>
            </div>
            <div className="rolling-kpi-card">
              <span className="kpi-label">Rolling Anomalies</span>
              <strong className="kpi-val font-mono">
                {rollingAnomaliesCount !== null ? rollingAnomaliesCount.toLocaleString('en-IN') : 'Unavailable'}
              </strong>
              <span className="kpi-sub">Deviations meeting Z-score threshold</span>
            </div>
            <div className="rolling-kpi-card">
              <span className="kpi-label">Insufficient History</span>
              <strong className="kpi-val font-mono status-text-amber">
                {insufficientHistoryCount !== null ? insufficientHistoryCount.toLocaleString('en-IN') : 'Unavailable'}
              </strong>
              <span className="kpi-sub">
                {insufficientMeters.length > 0 ? `Meters: ${insufficientMeters.join(', ')}` : 'Readings with < min observations'}
              </span>
            </div>
            <div className="rolling-kpi-card">
              <span className="kpi-label">Zero Variance</span>
              <strong className="kpi-val font-mono status-text-blue">
                {zeroVarCount !== null ? zeroVarCount.toLocaleString('en-IN') : 'Unavailable'}
              </strong>
              <span className="kpi-sub">
                {zeroVarMeters.length > 0 ? `Meters: ${zeroVarMeters.join(', ')}` : 'Readings with zero window variance'}
              </span>
            </div>
          </div>

          <div className="baseline-disclaimers-box">
            <div className="disclaimer-entry">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>
                <strong>Historical Continuity:</strong> Rolling windows dynamically aggregate available database records in the preceding {windowHours} hours. Telemetry gaps or missing readings do not guarantee continuous hourly coverage.
              </span>
            </div>
            <div className="disclaimer-entry">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>
                <strong>Operational Boundary:</strong> Statistical anomalies indicate mathematical deviations for review; they do not infer equipment faults, mechanical failures, or avoidable energy waste.
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

