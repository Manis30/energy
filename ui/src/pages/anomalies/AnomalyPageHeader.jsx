import React from 'react';
import { formatDate, formatDateTime } from '../../utils/formatters';

export default function AnomalyPageHeader({
  filters,
  onChangeFilters,
  onApplyFilters,
  dateRange,
  evaluationPeriod,
  baselinePeriod,
  lastRefreshed,
  onRefresh,
  refreshing,
}) {
  const evalStart = evaluationPeriod?.start_time;
  const evalEnd = evaluationPeriod?.end_time;
  const baseStart = baselinePeriod?.start_time;
  const baseEnd = baselinePeriod?.end_time;
  const lookbackDays = baselinePeriod?.lookback_days ?? 30;

  let evalPeriodText = 'All available dates';
  if (evalStart && evalEnd) {
    evalPeriodText = `${formatDateTime(evalStart)} – ${formatDateTime(evalEnd)}`;
  } else if (typeof dateRange === 'object' && dateRange?.start_date && dateRange?.end_date) {
    evalPeriodText = `${formatDate(dateRange.start_date)} – ${formatDate(dateRange.end_date)}`;
  } else if (typeof dateRange === 'string') {
    evalPeriodText = dateRange;
  }

  const baselinePeriodText = baseStart && baseEnd
    ? `${formatDateTime(baseStart)} – ${formatDateTime(baseEnd)} (${lookbackDays}d lookback)`
    : 'Baseline unavailable';

  return (
    <header className="alert-centre-header">
      <div className="alert-centre-heading">
        <span className="alert-centre-eyebrow">Industrial Energy Intelligence</span>
        <h1>Alert Centre</h1>
        <p>Review detected energy and power-quality deviations across monitored plants.</p>
      </div>
      <form className="alert-centre-filter-form" onSubmit={onApplyFilters}>
        <label>
          <span>Plant</span>
          <select
            value={filters.plant_id || ''}
            onChange={(event) => onChangeFilters((current) => ({
              ...current,
              plant_id: event.target.value || null,
            }))}
          >
            <option value="">All plants</option>
            <option value="IN-TN-01">IN-TN-01</option>
            <option value="IN-KA-01">IN-KA-01</option>
          </select>
        </label>
        <label>
          <span>From</span>
          <input
            type="date"
            value={filters.start_date}
            max={filters.end_date || undefined}
            onChange={(event) => onChangeFilters((current) => ({
              ...current,
              start_date: event.target.value,
            }))}
          />
        </label>
        <label>
          <span>To</span>
          <input
            type="date"
            value={filters.end_date}
            min={filters.start_date || undefined}
            onChange={(event) => onChangeFilters((current) => ({
              ...current,
              end_date: event.target.value,
            }))}
          />
        </label>
        <button className="alert-apply-filters" type="submit" disabled={refreshing}>
          Apply
        </button>
        <button className="alert-refresh" type="button" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </form>
      <div className="alert-centre-period">
        <div className="period-indicators">
          <span>
            <strong>Evaluation Period:</strong> {evalPeriodText}
          </span>
          <span className="period-separator">·</span>
          <span>
            <strong>Historical Baseline:</strong> {baselinePeriodText}
          </span>
        </div>
        {lastRefreshed && (
          <span>Updated {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        )}
      </div>
    </header>
  );
}
