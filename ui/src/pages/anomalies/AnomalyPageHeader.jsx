import React from 'react';

const PLANT_OPTIONS = [
  { value: '', label: 'All Plants (Consolidated)' },
  { value: 'IN-TN-01', label: 'Plant IN-TN-01 (Tamil Nadu)' },
  { value: 'IN-KA-01', label: 'Plant IN-KA-01 (Karnataka)' },
];

export default function AnomalyPageHeader({
  dateRange,
  lastRefreshed,
  onRefresh,
  refreshing,
  selectedPlant,
  onSelectPlant,
}) {
  const formattedDateRange = dateRange
    ? `${dateRange.start_date} to ${dateRange.end_date}`
    : '2026-08-01 to 2026-10-31 (92 Days)';

  return (
    <div className="dashboard-header-container">
      <div className="dashboard-header-left">
        <div className="dashboard-title-row">
          <h1 className="dashboard-title">Anomaly Monitoring</h1>
          <span className="live-badge">
            <span className="pulse-dot"></span>
            Deterministic Exception Surveillance
          </span>
        </div>
        <p className="dashboard-subtitle">
          Continuous statistical Z-score surveillance, rolling baseline deviations, power factor compliance, and zero-production standby energy draw.
        </p>
      </div>

      <div className="dashboard-header-right">
        {/* Plant Filter Dropdown */}
        <div className="filter-group">
          <label htmlFor="plant-select" className="filter-label">Factory Scope:</label>
          <select
            id="plant-select"
            className="filter-select"
            value={selectedPlant || ''}
            onChange={(e) => onSelectPlant(e.target.value ? e.target.value : null)}
          >
            {PLANT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Date Range Badge */}
        <div className="date-range-badge" title="Source Data Coverage Period">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/>
            <line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <span>{formattedDateRange}</span>
        </div>

        {/* Refresh Action */}
        <button
          type="button"
          className="refresh-btn"
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh anomaly data"
        >
          <svg
            className={`refresh-icon ${refreshing ? 'spinning' : ''}`}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
          </svg>
          <span>{refreshing ? 'Refreshing...' : 'Refresh'}</span>
        </button>

        {lastRefreshed && (
          <span className="last-refreshed-text">
            Updated {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>
    </div>
  );
}

