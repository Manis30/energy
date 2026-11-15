import React from 'react';
import { formatDate, formatDateTime, formatNumber } from '../../utils/formatters';
import './daily-coverage.css';

const COVERAGE_LABELS = {
  NO_RECORDS: 'No records',
  PARTIAL_OBSERVED: 'Partial observed',
  ALL_REGISTERED_OBSERVED: 'All registered lines observed',
  UNDETERMINED: 'Expected coverage unavailable',
};

function CoverageTable({ title, rows, stream, emptyMessage }) {
  return (
    <div className="daily-coverage-stream">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="daily-coverage-empty">{emptyMessage}</p>
      ) : (
        <div className="daily-coverage-table-wrap">
          <table className="daily-coverage-table">
            <thead>
              <tr>
                <th>Date / plant</th>
                <th>Status</th>
                <th>Records / timestamps</th>
                <th>Entities observed</th>
                <th>First / last timestamp</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const statusLabel = row.coverage_status === 'UNDETERMINED'
                  && row.record_status === 'OBSERVED'
                  && stream === 'energy'
                  ? 'Observed · expected meters unavailable'
                  : COVERAGE_LABELS[row.coverage_status] || 'Coverage unavailable';
                return (
                  <tr key={`${row.plant_id}-${row.reporting_date}`}>
                    <td>
                      <strong>{formatDate(row.reporting_date)}</strong>
                      <span className="daily-coverage-subvalue">{row.plant_id}</span>
                    </td>
                    <td>
                      <span className={`daily-coverage-status ${row.coverage_status.toLowerCase()}`}>
                        {statusLabel}
                      </span>
                    </td>
                    <td>
                      <strong>{formatNumber(row.record_count)}</strong> records
                      <span className="daily-coverage-subvalue">
                        {formatNumber(row.observed_hours)} distinct timestamps
                      </span>
                    </td>
                    <td>
                      {row.expected_entities === null ? (
                        <span className="daily-coverage-subvalue">
                          Expected {stream === 'energy' ? 'meters' : 'lines'} unavailable for plant
                        </span>
                      ) : (
                        <span className="daily-coverage-subvalue">
                          Registered: {row.expected_entities.length
                            ? row.expected_entities.join(', ')
                            : 'Unavailable'}
                        </span>
                      )}
                      <span className="daily-coverage-subvalue">
                        Observed: {row.observed_entities.length
                          ? row.observed_entities.join(', ')
                          : 'None'}
                      </span>
                      {row.unobserved_registered_entities?.length > 0 && (
                        <span className="daily-coverage-subvalue">
                          Unobserved this date: {row.unobserved_registered_entities.join(', ')}
                        </span>
                      )}
                    </td>
                    <td>
                      <span>{formatDateTime(row.first_observed_timestamp)}</span>
                      <span className="daily-coverage-subvalue">
                        Last: {formatDateTime(row.last_observed_timestamp)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function DailyCoverageSection({
  coverage,
  selectedPlant,
  loading,
  error,
  onRetry,
  reportingDate,
}) {
  const energyRows = (coverage?.energy_coverage || [])
    .filter((row) => !selectedPlant || row.plant_id === selectedPlant);
  const productionRows = (coverage?.production_coverage || [])
    .filter((row) => !selectedPlant || row.plant_id === selectedPlant);

  return (
    <section className="daily-coverage-section" aria-label="Daily persisted data coverage">
      <div className="daily-coverage-heading">
        <div>
          <h2>Persisted data coverage</h2>
          <p>Reporting date: {formatDate(reportingDate)}{selectedPlant ? ` · ${selectedPlant}` : ' · All plants'}</p>
        </div>
        {loading && <span className="daily-coverage-state" role="status">Loading coverage…</span>}
      </div>

      {error ? (
        <div className="daily-coverage-error" role="alert">
          <span>Coverage could not be loaded: {error}</span>
          <button type="button" onClick={onRetry}>Retry coverage</button>
        </div>
      ) : loading ? (
        <p className="daily-coverage-empty" role="status">Retrieving coverage for the selected date.</p>
      ) : !coverage ? (
        <p className="daily-coverage-empty">Coverage is unavailable for this date.</p>
      ) : (
        <>
          <div className="daily-coverage-meter-catalog">
            <strong>Configured energy meter catalog:</strong>{' '}
            {coverage.registered_energy_meters?.length
              ? coverage.registered_energy_meters.join(', ')
              : 'Unavailable'}
            <span> · Catalog is global; plant-specific expected meter coverage is unavailable.</span>
          </div>

          {selectedPlant && energyRows.length === 0 && productionRows.length === 0 ? (
            <p className="daily-coverage-empty">
              No coverage row was returned for this plant; it has no records in either stream and no registered production line in the available master data.
            </p>
          ) : !selectedPlant && energyRows.length === 0 && productionRows.length === 0 ? (
            <p className="daily-coverage-empty">
              No plant records or registered production lines were returned for this date range.
            </p>
          ) : (
            <>
              <CoverageTable
                title="Energy"
                rows={energyRows}
                stream="energy"
                emptyMessage="No energy coverage rows are available for this plant/date scope."
              />
              <CoverageTable
                title="Production"
                rows={productionRows}
                stream="production"
                emptyMessage="No production coverage rows are available for this plant/date scope."
              />
            </>
          )}

          <p className="daily-coverage-note">
            “All registered lines observed” means each currently registered production line appeared at least once on the date; it does not mean every line reported every hour. Missing hours and 24-hour completeness are unavailable because no approved operating calendar is provided.
          </p>
        </>
      )}
    </section>
  );
}
