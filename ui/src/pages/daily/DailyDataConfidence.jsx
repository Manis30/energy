import React from 'react';

const DATA_FEEDS = [
  'Energy summary',
  'Energy by meter',
  'Energy by area',
  'Power factor summary',
  'Production summary',
  'Production by line',
  'Process energy intensity',
  'Factory energy intensity',
  'Anomaly analysis',
  '7-day energy trend',
];

export default function DailyDataConfidence({
  selectedDate,
  selectedPlant,
  trendPeriod,
  energySummary,
  productionSummary,
  powerFactorData,
  processIntensity,
  factoryIntensity,
  anomaliesData,
  apiAvailability,
}) {
  const energyAvailable = apiAvailability?.['Energy summary']?.available === true;
  const productionAvailable = apiAvailability?.['Production summary']?.available === true;
  const energyReadings = energyAvailable && Number.isFinite(Number(energySummary?.total_readings))
    ? Number(energySummary.total_readings)
    : null;
  const distinctTimestamps = energyAvailable && Number.isFinite(Number(energySummary?.distinct_hours))
    ? Number(energySummary.distinct_hours)
    : null;
  const productionEvents = productionAvailable && Number.isFinite(Number(productionSummary?.event_count))
    ? Number(productionSummary.event_count)
    : null;

  const unavailableMetrics = [];
  if (productionAvailable && productionSummary?.oee?.status === 'unavailable') {
    unavailableMetrics.push(`OEE: ${productionSummary.oee.reason || 'unavailable in this response'}`);
  }
  if (apiAvailability?.['Power factor summary']?.available && powerFactorData?.avg_power_factor == null) {
    unavailableMetrics.push('Average power factor: no value returned');
  }
  if (apiAvailability?.['Process energy intensity']?.available && processIntensity) {
    if (processIntensity.smt_summary?.overall_process_sec_kwh_per_board == null) {
      unavailableMetrics.push('SMT SEC: unavailable for this selection');
    }
    if (processIntensity.fal_summary?.overall_process_sec_kwh_per_phone == null) {
      unavailableMetrics.push('FAL SEC: unavailable for this selection');
    }
  }
  if (apiAvailability?.['Factory energy intensity']?.available
      && factoryIntensity?.factory_sec_kwh_per_finished_unit == null) {
    unavailableMetrics.push('Factory SEC: unavailable for this selection');
  }
  const statisticalData = anomaliesData?.statistical_zscore;
  const insufficientGroups = statisticalData?.insufficient_observations_groups || [];
  const zeroVarianceGroups = statisticalData?.zero_variance_groups || [];
  const evidenceWarnings = [];
  if (insufficientGroups.length > 0) {
    evidenceWarnings.push(`${insufficientGroups.length} meter group(s) had insufficient observations for statistical evaluation`);
  }
  if (zeroVarianceGroups.length > 0) {
    evidenceWarnings.push(`${zeroVarianceGroups.length} meter group(s) had zero variance and could not support a meaningful z-score`);
  }

  const unavailableFeeds = DATA_FEEDS.filter((name) => apiAvailability?.[name]?.available === false);

  return (
    <section className="daily-data-confidence" aria-label="Daily analysis data coverage">
      <div className="daily-confidence-heading">
        <div>
          <h2>Data coverage &amp; interpretation</h2>
          <p>
            Analysis date: <strong>{selectedDate}</strong>
            <span className="daily-confidence-separator">·</span>
            Scope: <strong>{selectedPlant || 'All plants'}</strong>
            {trendPeriod && (
              <>
                <span className="daily-confidence-separator">·</span>
                Trend window: <strong>{trendPeriod.start_date} – {trendPeriod.end_date}</strong>
              </>
            )}
          </p>
        </div>
        <span className="daily-confidence-tag">Returned records, not completeness</span>
      </div>

      <div className="daily-confidence-sources">
        <div className={`daily-confidence-source ${energyAvailable ? 'available' : 'unavailable'}`}>
          <span className="confidence-source-label">Energy summary</span>
          <strong>
            {!energyAvailable
              ? 'Unavailable'
              : energyReadings === null
                ? 'Reading count unavailable'
                : energyReadings === 0
                ? 'No readings returned'
                : `${energyReadings.toLocaleString('en-IN')} meter readings`}
          </strong>
          {energyAvailable && energyReadings > 0 && (
            <span>{distinctTimestamps === null ? 'Timestamp count unavailable' : `${distinctTimestamps.toLocaleString('en-IN')} distinct timestamps`}</span>
          )}
        </div>
        <div className={`daily-confidence-source ${productionAvailable ? 'available' : 'unavailable'}`}>
          <span className="confidence-source-label">Production records</span>
          <strong>
            {!productionAvailable
              ? 'Unavailable'
              : productionEvents === null
                ? 'Event count unavailable'
                : productionEvents === 0
                ? 'No events returned'
                : `${productionEvents.toLocaleString('en-IN')} events`}
          </strong>
          <span>{productionAvailable ? 'Logged production event count' : 'Production summary request failed'}</span>
        </div>
      </div>

      <div className="daily-confidence-methods">
        <span><strong>Measured inputs:</strong> returned meter telemetry and logged production events</span>
        <span><strong>Calculated outputs:</strong> aggregates, rates, SEC, and detector indicators</span>
      </div>

      {(unavailableFeeds.length > 0 || unavailableMetrics.length > 0 || evidenceWarnings.length > 0) && (
        <details className="daily-confidence-details" open={unavailableFeeds.length > 0 || evidenceWarnings.length > 0}>
          <summary>
            Data limitations
            {unavailableFeeds.length > 0 && ` · ${unavailableFeeds.length} data request${unavailableFeeds.length === 1 ? '' : 's'} failed`}
          </summary>
          {evidenceWarnings.length > 0 && (
            <ul className="daily-confidence-unavailable-list">
              {evidenceWarnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          )}
          {unavailableFeeds.length > 0 && (
            <div className="daily-confidence-unavailable-list">
              <strong>Data feeds not returned:</strong>
              <span>{unavailableFeeds.join(', ')}</span>
            </div>
          )}
          {unavailableMetrics.length > 0 && (
            <ul className="daily-confidence-unavailable-list">
              {unavailableMetrics.map((metric) => <li key={metric}>{metric}</li>)}
            </ul>
          )}
        </details>
      )}

      <p className="daily-confidence-limitation">
        Coverage reports persisted records and date-level entity observations. No approved operating calendar, per-hour reporting expectation, or plant-specific energy-meter registry is available, so counts do not establish completeness.
      </p>
    </section>
  );
}
