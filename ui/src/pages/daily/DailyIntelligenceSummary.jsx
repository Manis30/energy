import React from 'react';
import { formatCurrency, formatDate, formatDateTime, formatNumber } from '../../utils/formatters';

const hasNumber = (value) => value !== null
  && value !== undefined
  && value !== ''
  && Number.isFinite(Number(value));

function getFailedFeeds(apiAvailability) {
  if (!apiAvailability) return [];
  return Object.entries(apiAvailability)
    .filter(([, status]) => status?.available === false)
    .map(([name]) => name);
}

function observationClass(tone) {
  return `daily-intelligence-item${tone ? ` ${tone}` : ''}`;
}

export default function DailyIntelligenceSummary({
  selectedDate,
  selectedPlant,
  energySummary,
  productionSummary,
  powerFactorData,
  processIntensity,
  factoryIntensity,
  anomaliesData,
  dailyTrend = [],
  apiAvailability,
  error,
  dateWarning,
}) {
  const energyAvailable = apiAvailability?.['Energy summary']?.available === true;
  const productionAvailable = apiAvailability?.['Production summary']?.available === true;
  const pfAvailable = apiAvailability?.['Power factor summary']?.available === true;
  const anomalyAvailable = apiAvailability?.['Anomaly analysis']?.available === true;
  const trendAvailable = apiAvailability?.['7-day energy trend']?.available === true;
  const failedFeeds = getFailedFeeds(apiAvailability);

  const energyReadings = hasNumber(energySummary?.total_readings)
    ? Number(energySummary.total_readings)
    : null;
  const energyKwh = hasNumber(energySummary?.total_consumption_kwh)
    ? Number(energySummary.total_consumption_kwh)
    : null;
  const energyCost = hasNumber(energySummary?.total_cost_inr)
    ? Number(energySummary.total_cost_inr)
    : null;
  const productionQty = hasNumber(productionSummary?.actual_qty)
    ? Number(productionSummary.actual_qty)
    : null;

  const detectorResults = [
    ['Statistical Z-score', anomaliesData?.statistical_zscore],
    ['Rolling baseline', anomaliesData?.rolling_baseline],
    ['Low power factor', anomaliesData?.low_power_factor],
    ['Zero-output energy', anomaliesData?.zero_production_standby],
  ];
  const returnedFlags = detectorResults.flatMap(([detector, result]) => (
    (result?.anomalies || []).map((anomaly) => ({ ...anomaly, detector }))
  ));
  const priorityFlags = returnedFlags.filter((flag) => (
    ['HIGH', 'CRITICAL'].includes(String(flag.severity || '').toUpperCase())
  ));
  const totalDetectorFlags = hasNumber(anomaliesData?.total_anomalies_detected)
    ? Number(anomaliesData.total_anomalies_detected)
    : returnedFlags.length;

  const trendRecords = (dailyTrend || [])
    .filter((record) => typeof record?.date === 'string' && hasNumber(record.consumption_kwh))
    .sort((a, b) => a.date.localeCompare(b.date));
  const selectedTrendRecord = trendRecords.find((record) => record.date === selectedDate);
  const previousTrendRecord = trendRecords
    .filter((record) => record.date < selectedDate)
    .slice(-1)[0];
  const comparisonCurrentKwh = energyKwh !== null
    ? energyKwh
    : selectedTrendRecord
      ? Number(selectedTrendRecord.consumption_kwh)
      : null;

  const pfAverage = hasNumber(powerFactorData?.avg_power_factor)
    ? Number(powerFactorData.avg_power_factor)
    : null;
  const lowPfEvents = hasNumber(powerFactorData?.low_pf_events_count)
    ? Number(powerFactorData.low_pf_events_count)
    : null;
  const pfThreshold = hasNumber(powerFactorData?.threshold)
    ? Number(powerFactorData.threshold)
    : 0.90;

  const followUps = [];
  if (priorityFlags.length > 0) {
    followUps.push(`${priorityFlags.length} high/critical detector flag(s) were returned; review the associated telemetry and operating records.`);
  }
  if (lowPfEvents > 0) {
    followUps.push(`${formatNumber(lowPfEvents)} power-factor reading(s) were below the application threshold; review the meter context.`);
  }
  if (hasNumber(anomaliesData?.zero_production_standby?.total_events_detected)
      && Number(anomaliesData.zero_production_standby.total_events_detected) > 0) {
    followUps.push('Positive process-meter energy was recorded during zero-output intervals; verify operating context before drawing conclusions.');
  }
  if (failedFeeds.length > 0) {
    followUps.push(`Some data requests failed (${failedFeeds.join(', ')}); consider the available results partial.`);
  }

  const energyText = !energyAvailable
    ? 'Energy summary unavailable'
    : energyReadings === 0
      ? 'No energy meter readings were returned'
      : energyKwh !== null
        ? `${formatNumber(energyKwh, 2)} kWh returned`
        : 'Energy total unavailable';

  const productionText = !productionAvailable
    ? 'Production summary unavailable'
    : productionQty !== null
      ? `${formatNumber(productionQty)} units reported`
      : 'Production quantity unavailable';

  const pfText = !pfAvailable
    ? 'Power-factor summary unavailable'
    : pfAverage !== null
      ? `Average PF ${pfAverage.toFixed(4)}`
      : 'Average power factor unavailable';

  const historicalText = !trendAvailable
    ? 'Historical trend request unavailable'
    : comparisonCurrentKwh !== null && previousTrendRecord
      ? (() => {
        const previousKwh = Number(previousTrendRecord.consumption_kwh);
        const difference = comparisonCurrentKwh - previousKwh;
        const sign = difference > 0 ? '+' : '';
        return `${formatNumber(comparisonCurrentKwh, 2)} kWh on ${formatDate(selectedDate)} vs ${formatNumber(previousKwh, 2)} kWh on ${formatDate(previousTrendRecord.date)} (${sign}${formatNumber(difference, 2)} kWh)`;
      })()
      : `${trendRecords.length} daily trend record(s) returned; no earlier comparison record is available`;

  const intensityValues = [
    processIntensity?.smt_summary?.overall_process_sec_kwh_per_board != null
      ? `SMT ${formatNumber(processIntensity.smt_summary.overall_process_sec_kwh_per_board, 4)} kWh/board`
      : null,
    processIntensity?.fal_summary?.overall_process_sec_kwh_per_phone != null
      ? `FAL ${formatNumber(processIntensity.fal_summary.overall_process_sec_kwh_per_phone, 4)} kWh/phone`
      : null,
    factoryIntensity?.factory_sec_kwh_per_finished_unit != null
      ? `Factory ${formatNumber(factoryIntensity.factory_sec_kwh_per_finished_unit, 4)} kWh/finished phone`
      : null,
  ].filter(Boolean);

  return (
    <section className="daily-intelligence-summary" aria-label="Daily intelligence summary">
      <div className="daily-intelligence-heading">
        <div>
          <h2>Daily Intelligence Summary</h2>
          <p>
            {formatDate(selectedDate)} · {selectedPlant || 'All plants'} · Based on returned analytics
          </p>
        </div>
        <span className={`daily-intelligence-status${error || dateWarning || failedFeeds.length > 0 ? ' attention' : ''}`}>
          {dateWarning ? 'Date unavailable' : error || failedFeeds.length > 0 ? 'Partial analysis' : 'Evidence-based'}
        </span>
      </div>

      {dateWarning ? (
        <p className="daily-intelligence-empty">{dateWarning}</p>
      ) : (
        <>
          <div className="daily-intelligence-grid">
            <details className={observationClass()}>
              <summary>
                <span className="daily-intelligence-label">Energy use &amp; cost</span>
                <strong>{energyText}</strong>
              </summary>
              <p>
                {energyKwh !== null && energyCost !== null
                  ? `Calculated cost: ${formatCurrency(energyCost)} using the dataset tariff; this is not confirmation of the current utility bill.`
                  : energyKwh !== null
                    ? 'Consumption is a returned daily aggregate. Cost was not available.'
                    : 'No energy total is available to support an energy or cost observation.'}
              </p>
              {energyAvailable && hasNumber(energySummary?.total_readings) && (
                <span className="daily-intelligence-evidence">
                  {formatNumber(energySummary.total_readings)} meter readings · {formatNumber(energySummary?.distinct_hours)} distinct timestamps
                </span>
              )}
            </details>

            <details className={observationClass()}>
              <summary>
                <span className="daily-intelligence-label">Production</span>
                <strong>{productionText}</strong>
              </summary>
              <p>
                {productionQty !== null
                  ? `Good units: ${formatNumber(productionSummary?.good_qty)}; rejects: ${formatNumber(productionSummary?.reject_qty)}; reported downtime: ${formatNumber(productionSummary?.downtime_min)} minutes. These are returned production aggregates, not evidence of a cause.`
                  : 'Production output is unavailable; production performance cannot be assessed for this selection.'}
              </p>
              {productionAvailable && hasNumber(productionSummary?.event_count) && (
                <span className="daily-intelligence-evidence">
                  {formatNumber(productionSummary.event_count)} logged production event(s)
                </span>
              )}
            </details>

            <details className={observationClass(lowPfEvents > 0 ? 'attention' : '')}>
              <summary>
                <span className="daily-intelligence-label">Power factor</span>
                <strong>{pfText}</strong>
              </summary>
              <p>
                {lowPfEvents !== null
                  ? `${formatNumber(lowPfEvents)} reading(s) below the application threshold of ${pfThreshold.toFixed(2)}. Low readings warrant meter/context review but do not establish an equipment fault.`
                  : 'Under-threshold reading count is unavailable; no threshold conclusion can be drawn.'}
              </p>
              {pfAvailable && (
                <span className="daily-intelligence-evidence">
                  {hasNumber(powerFactorData?.total_readings)
                    ? `${formatNumber(powerFactorData.total_readings)} PF readings`
                    : 'PF reading count unavailable'}
                  {hasNumber(powerFactorData?.min_power_factor) && hasNumber(powerFactorData?.max_power_factor)
                    ? ` · range ${Number(powerFactorData.min_power_factor).toFixed(4)}–${Number(powerFactorData.max_power_factor).toFixed(4)}`
                    : ''}
                </span>
              )}
            </details>

            <details className={observationClass(priorityFlags.length > 0 ? 'attention' : '')}>
              <summary>
                <span className="daily-intelligence-label">Anomaly findings</span>
                <strong>
                  {!anomalyAvailable
                    ? 'Anomaly analysis unavailable'
                    : `${formatNumber(totalDetectorFlags)} detector flag(s)`}
                </strong>
              </summary>
              <p>
                {!anomalyAvailable
                  ? 'No anomaly conclusion is available because this request did not return results.'
                  : totalDetectorFlags > 0
                    ? 'Flags can overlap on the same underlying observation; they are not a count of unique incidents or confirmed equipment failures.'
                    : 'No detector flags were returned for this selection. This does not establish data completeness or the absence of operational issues.'}
              </p>
              {priorityFlags.length > 0 && (
                <ul className="daily-intelligence-flag-list">
                  {priorityFlags.slice(0, 4).map((flag, index) => (
                    <li key={`${flag.detector}-${flag.timestamp}-${flag.meter_id}-${index}`}>
                      <strong>{String(flag.severity).toUpperCase()}</strong>
                      {' · '}{flag.detector}
                      {' · '}{flag.meter_id || flag.line_id || flag.plant_id || 'Meter unavailable'}
                      {flag.timestamp ? ` · ${formatDateTime(flag.timestamp)}` : ''}
                      {hasNumber(flag.actual_value)
                        ? ` · ${formatNumber(flag.actual_value, 2)} ${flag.detector === 'Low power factor' ? 'PF' : 'kWh'}`
                        : ''}
                      {flag.explanation ? <span>{flag.explanation}</span> : null}
                    </li>
                  ))}
                  {priorityFlags.length > 4 && <li>{formatNumber(priorityFlags.length - 4)} additional high/critical returned flag(s)</li>}
                </ul>
              )}
            </details>

            <details className={observationClass()}>
              <summary>
                <span className="daily-intelligence-label">Energy intensity</span>
                <strong>{intensityValues.length > 0 ? intensityValues.join(' · ') : 'Not available for this selection'}</strong>
              </summary>
              <p>
                These are calculated SEC values with different meter and production scopes; they are not directly interchangeable or an approved target.
                {productionQty === 0 ? ' No production was reported, so a zero-output intensity conclusion is unavailable.' : ''}
              </p>
              {!intensityValues.length && (
                <span className="daily-intelligence-evidence">
                  Process or factory intensity responses did not provide a usable value.
                </span>
              )}
            </details>

            <details className={observationClass()}>
              <summary>
                <span className="daily-intelligence-label">Historical context</span>
                <strong>{historicalText}</strong>
              </summary>
              <p>
                The comparison is total daily energy against the previous returned date, which may not be the previous calendar day. It is not production-normalized and does not establish improved efficiency or achieved savings.
              </p>
            </details>
          </div>

          <details className={`daily-intelligence-follow-up${followUps.length > 0 ? ' attention' : ''}`}>
            <summary>
              <strong>Human review</strong>
              <span>
                {followUps.length > 0
                  ? `${formatNumber(followUps.length)} item(s) to consider`
                  : 'No specific follow-up indicated by returned findings'}
              </span>
            </summary>
            {followUps.length > 0 ? (
              <ul>
                {followUps.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : (
              <p>Returned results do not identify a specific follow-up item; this is not proof that no operational issue exists.</p>
            )}
          </details>

          <p className="daily-intelligence-limitation">
            {failedFeeds.length > 0
              ? `Unavailable requests: ${failedFeeds.join(', ')}. Interpret this summary as partial.`
              : 'Returned record counts do not establish completeness. No expected-energy target, verified savings, or equipment-level diagnosis is inferred.'}
          </p>
        </>
      )}
    </section>
  );
}
