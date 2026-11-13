import React from 'react';
import { formatDate } from '../../utils/formatters';

const PLANT_OPTIONS = [
  { value: '', label: 'All Plants (Consolidated)' },
  { value: 'IN-TN-01', label: 'Plant IN-TN-01 (Tamil Nadu)' },
  { value: 'IN-KA-01', label: 'Plant IN-KA-01 (Karnataka)' },
];

export default function AnalyticsPageHeader({
  badge,
  title,
  subtitle,
  selectedPlant,
  onSelectPlant,
  dateRange,
  isDaily = false,
  selectedDate,
  onDateChange,
  minDate = '2026-08-01',
  maxDate = '2026-10-31',
  dateWarning,
  onRefresh,
  refreshing = false,
  lastRefreshed,
}) {
  const handlePrevDay = () => {
    if (!selectedDate || selectedDate <= minDate) return;
    const d = new Date(selectedDate + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - 1);
    const prevDate = d.toISOString().split('T')[0];
    if (prevDate >= minDate && onDateChange) {
      onDateChange(prevDate);
    }
  };

  const handleNextDay = () => {
    if (!selectedDate || selectedDate >= maxDate) return;
    const d = new Date(selectedDate + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + 1);
    const nextDate = d.toISOString().split('T')[0];
    if (nextDate <= maxDate && onDateChange) {
      onDateChange(nextDate);
    }
  };

  // Determine display text for date coverage
  let displayDateRange = 'Aug 1, 2026 – Oct 31, 2026';
  if (typeof dateRange === 'string') {
    displayDateRange = dateRange;
  } else if (dateRange && dateRange.start_date && dateRange.end_date) {
    displayDateRange = `${formatDate(dateRange.start_date)} – ${formatDate(dateRange.end_date)}`;
  }

  const formatTimestamp = (ts) => {
    if (!ts) return '';
    if (ts instanceof Date) {
      return ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    return String(ts);
  };

  const idPrefix = (title || 'analytics').toLowerCase().replace(/[^a-z0-9]/g, '-');

  return (
    <div className="dashboard-header-card analytics-page-header">
      <div className="analytics-header-top">
        {/* Left: Title & Description */}
        <div className="dashboard-title-group">
          {badge && <span className="dashboard-title-badge">{badge}</span>}
          <h1 className="dashboard-title">{title}</h1>
          {subtitle && <p className="dashboard-subtitle">{subtitle}</p>}
        </div>

        {/* Right: Coherent Responsive Filter Toolbar */}
        <div className="filter-toolbar" role="toolbar" aria-label="Analytics Filters">
          {/* 1. Factory Scope Dropdown */}
          <div className="filter-item">
            <label htmlFor={`${idPrefix}-plant-select`} className="filter-label">
              Factory Scope:
            </label>
            <div className="custom-select-wrapper">
              <select
                id={`${idPrefix}-plant-select`}
                className="factory-scope-select"
                value={selectedPlant || ''}
                onChange={(e) => onSelectPlant && onSelectPlant(e.target.value || null)}
                aria-label="Factory Scope"
              >
                {PLANT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <span className="select-arrow" aria-hidden="true">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </span>
            </div>
          </div>

          {/* 2. Date Range Picker / Date Selector */}
          {isDaily ? (
            <div className="filter-item">
              <label htmlFor={`${idPrefix}-date-select`} className="filter-label">
                Date:
              </label>
              <div className="date-picker-controls">
                <button
                  type="button"
                  className="date-nav-btn"
                  onClick={handlePrevDay}
                  disabled={selectedDate <= minDate}
                  title="Previous Day"
                  aria-label="Previous Day"
                >
                  ‹
                </button>
                <div className="date-input-wrapper">
                  <svg className="date-calendar-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  <input
                    id={`${idPrefix}-date-select`}
                    type="date"
                    className="date-filter-input"
                    value={selectedDate}
                    min={minDate}
                    max={maxDate}
                    onChange={(e) => onDateChange && onDateChange(e.target.value)}
                    title={`Select date within verified dataset period (${minDate} to ${maxDate})`}
                  />
                </div>
                <button
                  type="button"
                  className="date-nav-btn"
                  onClick={handleNextDay}
                  disabled={selectedDate >= maxDate}
                  title="Next Day"
                  aria-label="Next Day"
                >
                  ›
                </button>
              </div>
            </div>
          ) : (
            <div className="filter-item">
              <div className="date-range-control" title="Verified source dataset coverage period">
                <svg className="date-calendar-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
                  <line x1="16" y1="2" x2="16" y2="6"/>
                  <line x1="8" y1="2" x2="8" y2="6"/>
                  <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span className="date-range-text">{displayDateRange}</span>
              </div>
            </div>
          )}

          {/* 3. Refresh Button */}
          <div className="filter-item">
            <button
              type="button"
              className={`filter-refresh-btn ${refreshing ? 'loading' : ''}`}
              onClick={onRefresh}
              disabled={refreshing}
              title="Refresh analytics data"
              aria-label="Refresh analytics data"
            >
              <svg
                className={`refresh-icon ${refreshing ? 'spinning' : ''}`}
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
              </svg>
              <span>{refreshing ? 'Updating...' : 'Refresh'}</span>
            </button>
          </div>

          {/* 4. Updated Timestamp */}
          {lastRefreshed && (
            <div className="filter-item filter-timestamp-item">
              <span className="updated-timestamp" title="Deterministic telemetry timestamp">
                <span className="updated-pulse-dot" aria-hidden="true" />
                <span>Updated {formatTimestamp(lastRefreshed)}</span>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Optional Warning Banner */}
      {dateWarning && (
        <div className="daily-warning-banner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{dateWarning}</span>
        </div>
      )}
    </div>
  );
}

