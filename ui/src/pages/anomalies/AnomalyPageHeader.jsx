import React from 'react';
import { formatDate } from '../../utils/formatters';

export default function AnomalyPageHeader({
  filters,
  onChangeFilters,
  onApplyFilters,
  dateRange,
  lastRefreshed,
  onRefresh,
  refreshing,
}) {
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
        <span>
          Data period: {typeof dateRange === 'string'
            ? dateRange
            : `${formatDate(dateRange.start_date)} – ${formatDate(dateRange.end_date)}`}
        </span>
        {lastRefreshed && (
          <span>Updated {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        )}
      </div>
    </header>
  );
}
