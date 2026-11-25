import React from 'react';

function formatOptionDate(dateStr) {
  if (!dateStr || typeof dateStr !== 'string') return '';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const [y, m, d] = parts;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthName = months[parseInt(m, 10) - 1] || m;
  return `${d} ${monthName} ${y}`;
}

/**
 * Modern Executive Dashboard Header
 * Streamlined single-row layout with Month, Date, Plant, Shift filters and Refresh.
 */
export default function DashboardHeader({
  selectedMonth = '2026-10',
  onSelectMonth,
  selectedDate = 'ALL',
  onSelectDate,
  selectedPlant = 'ALL',
  onSelectPlant,
  selectedShift = 'ALL',
  onSelectShift,
  availableMonths = [],
  availableDates = [],
  availablePlants = [],
  availableShifts = [],
  onRefresh,
  refreshing = false,
  isDataOutOfCoverage = false,
  backendConnected = true,
}) {
  return (
    <header className="premium-dashboard-header" role="banner">
      <div className="premium-header-main">
        {/* Exactly Four Filter Selectors + Single Refresh Button in a Single Row */}
        {/* Order: Month → Date → Plant → Shift → Refresh */}
        <div className="premium-filter-toolbar" role="toolbar" aria-label="Dashboard Date, Plant and Shift Filters">
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
            <div className="select-container">
              <select
                id="dashboard-month-select"
                className="premium-select"
                value={selectedMonth}
                onChange={(e) => onSelectMonth && onSelectMonth(e.target.value)}
                aria-label="Select month"
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
            <div className="select-container">
              <select
                id="dashboard-date-select"
                className="premium-select"
                value={selectedDate}
                onChange={(e) => onSelectDate && onSelectDate(e.target.value)}
                aria-label="Select date"
              >
                <option value="ALL">All days</option>
                {availableDates.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.shortLabel || (d.value && d.value !== 'ALL' && /^\d{4}-\d{2}-\d{2}$/.test(d.value) ? formatOptionDate(d.value) : d.label)}
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

          {/* 3. Plant Selector */}
          <div className="filter-pill-control plant-selector-pill">
            <span className="control-icon" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 21h18M5 21V7l8-4v18M13 21V3l6 3v15" />
                <path d="M9 10v.01M9 14v.01M9 18v.01M17 10v.01M17 14v.01M17 18v.01" />
              </svg>
            </span>
            <div className="select-container">
              <select
                id="dashboard-plant-select"
                className="premium-select"
                value={selectedPlant}
                onChange={(e) => onSelectPlant && onSelectPlant(e.target.value)}
                aria-label="Select plant"
              >
                <option value="ALL">All plants</option>
                {availablePlants.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.shortLabel || p.label}
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

          {/* 4. Shift Selector */}
          <div className="filter-pill-control shift-selector-pill">
            <span className="control-icon" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </span>
            <div className="select-container">
              <select
                id="dashboard-shift-select"
                className="premium-select"
                value={selectedShift}
                onChange={(e) => onSelectShift && onSelectShift(e.target.value)}
                aria-label="Select shift"
              >
                <option value="ALL">All shifts</option>
                {availableShifts.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.shortLabel || s.label}
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

          {/* 5. Refresh Button */}
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
