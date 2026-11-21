import React from 'react';

/**
 * Modern Executive Dashboard Header
 * Streamlined layout with title, live status, and Month & Date filter controls.
 */
export default function DashboardHeader({
  selectedMonth = '2026-10',
  onSelectMonth,
  selectedDate = 'ALL',
  onSelectDate,
  availableMonths = [],
  availableDates = [],
  onRefresh,
  refreshing = false,
  isDataOutOfCoverage = false,
  backendConnected = true,
}) {
  const activeMonthObj = availableMonths.find((m) => m.value === selectedMonth);
  const monthLabel = activeMonthObj ? activeMonthObj.label : selectedMonth;

  return (
    <header className="premium-dashboard-header" role="banner">
      <div className="premium-header-main">


        {/* Exactly Two Filter Selectors + Single Refresh Button */}
        <div className="premium-filter-toolbar" role="toolbar" aria-label="Dashboard Date Filters">
          {/* 1. Month Selector */}
          <div className="filter-pill-control month-selector-pill">
            <span className="control-icon" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </span>
            <label htmlFor="dashboard-month-select" className="filter-control-label">
              Month
            </label>
            <div className="select-container">
              <select
                id="dashboard-month-select"
                className="premium-select"
                value={selectedMonth}
                onChange={(e) => onSelectMonth && onSelectMonth(e.target.value)}
                aria-label="Select Aggregated Month"
              >
                {availableMonths.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
              <span className="select-chevron" aria-hidden="true">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </span>
            </div>
          </div>

          {/* 2. Date Selector */}
          <div className="filter-pill-control date-selector-pill">
            <span className="control-icon" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </span>
            <label htmlFor="dashboard-date-select" className="filter-control-label">
              Date
            </label>
            <div className="select-container">
              <select
                id="dashboard-date-select"
                className="premium-select"
                value={selectedDate}
                onChange={(e) => onSelectDate && onSelectDate(e.target.value)}
                aria-label="Select Date for Daily View or All Days for Monthly View"
              >
                <option value="ALL">
                  All Days ({monthLabel} — Monthly View)
                </option>
                {availableDates.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
              <span className="select-chevron" aria-hidden="true">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </span>
            </div>
          </div>

          {/* 3. Single Refresh Button */}
          <button
            type="button"
            className={`premium-btn-action refresh-btn ${refreshing ? 'loading' : ''}`}
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh live telemetry from backend"
            aria-label="Refresh live telemetry"
          >
            <span className={`refresh-spin-icon ${refreshing ? 'spinning' : ''}`} aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.19" />
              </svg>
            </span>
            <span>{refreshing ? 'Refreshing…' : 'Refresh'}</span>
          </button>
        </div>
      </div>

      {isDataOutOfCoverage && (
        <div className="coverage-advisory-pill" role="status" style={{ marginTop: '0.4rem' }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>No telemetry recorded for this period in PostgreSQL. Displaying empty states gracefully without fallback.</span>
        </div>
      )}
    </header>
  );
}
