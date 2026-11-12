import React from 'react';
import { formatDate } from '../../utils/formatters';

const MIN_DATE = '2026-08-01';
const MAX_DATE = '2026-10-31';

export default function DailyPageHeader({
  selectedDate,
  onDateChange,
  selectedPlant,
  onSelectPlant,
  lastRefreshed,
  onRefresh,
  refreshing,
  dateWarning,
}) {
  const handlePrevDay = () => {
    if (!selectedDate || selectedDate <= MIN_DATE) return;
    const d = new Date(selectedDate + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - 1);
    const prevDate = d.toISOString().split('T')[0];
    if (prevDate >= MIN_DATE) {
      onDateChange(prevDate);
    }
  };

  const handleNextDay = () => {
    if (!selectedDate || selectedDate >= MAX_DATE) return;
    const d = new Date(selectedDate + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + 1);
    const nextDate = d.toISOString().split('T')[0];
    if (nextDate <= MAX_DATE) {
      onDateChange(nextDate);
    }
  };

  return (
    <div className="dashboard-header-card">
      <div className="dashboard-header-main">
        <div className="dashboard-title-group">
          <div className="dashboard-title-badge">Operational Intelligence</div>
          <h2 className="dashboard-heading">Daily Analysis</h2>
          <p className="dashboard-subheading">
            Daily energy and production performance overview, Specific Energy Consumption (SEC) benchmarks, and automated anomaly auditing.
          </p>
        </div>

        <div className="dashboard-actions-group">
          <div className="date-range-badge" title="Verified source dataset coverage period">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            <span>Aug 1, 2026 – Oct 31, 2026</span>
          </div>

          {/* Date Selector with Step Controls */}
          <div className="filter-select-wrapper date-filter-wrapper">
            <label htmlFor="daily-date-select" className="filter-label">Date:</label>
            <div className="date-picker-controls">
              <button
                type="button"
                className="date-nav-btn"
                onClick={handlePrevDay}
                disabled={selectedDate <= MIN_DATE}
                title="Previous Day"
                aria-label="Previous Day"
              >
                ‹
              </button>
              <input
                id="daily-date-select"
                type="date"
                className="date-filter-input"
                value={selectedDate}
                min={MIN_DATE}
                max={MAX_DATE}
                onChange={(e) => onDateChange(e.target.value)}
                title="Select date within verified dataset period (2026-08-01 to 2026-10-31)"
              />
              <button
                type="button"
                className="date-nav-btn"
                onClick={handleNextDay}
                disabled={selectedDate >= MAX_DATE}
                title="Next Day"
                aria-label="Next Day"
              >
                ›
              </button>
            </div>
          </div>

          {/* Plant Selector */}
          <div className="filter-select-wrapper">
            <label htmlFor="daily-plant-select" className="filter-label">Plant:</label>
            <select
              id="daily-plant-select"
              className="plant-filter-select"
              value={selectedPlant || ''}
              onChange={(e) => onSelectPlant(e.target.value || null)}
            >
              <option value="">All Plants (TN-01 & KA-01)</option>
              <option value="IN-TN-01">Plant IN-TN-01 (Tamil Nadu)</option>
              <option value="IN-KA-01">Plant IN-KA-01 (Karnataka)</option>
            </select>
          </div>

          {/* Refresh Action */}
          <button
            type="button"
            className={`dashboard-refresh-btn ${refreshing ? 'loading' : ''}`}
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh daily analytics"
          >
            <svg
              className={`refresh-icon ${refreshing ? 'spin' : ''}`}
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/>
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
              <path d="M16 21h5v-5"/>
            </svg>
            <span>{refreshing ? 'Updating...' : 'Refresh'}</span>
          </button>
        </div>
      </div>

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

      {lastRefreshed && (
        <div className="dashboard-meta-footer">
          <span className="dataset-status-dot"></span>
          <span>
            Last refreshed: {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })} • Historical dataset records for {formatDate(selectedDate)} ({selectedPlant || 'All Plants'})
          </span>
        </div>
      )}
    </div>
  );
}

