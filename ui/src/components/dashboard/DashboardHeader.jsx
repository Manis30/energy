import React from 'react';
import { formatDate } from '../../utils/formatters';

export default function DashboardHeader({
  dateRange,
  lastRefreshed,
  onRefresh,
  refreshing,
  selectedPlant,
  onSelectPlant,
}) {
  return (
    <div className="dashboard-header-card">
      <div className="dashboard-header-main">
        <div className="dashboard-title-group">
          <div className="dashboard-title-badge">Manufacturing Intelligence</div>
          <h2 className="dashboard-heading">Industrial Energy Dashboard</h2>
          <p className="dashboard-subheading">
            Operational overview of plant-wide energy consumption, production throughput, Specific Energy Consumption (SEC), and automated anomaly monitoring.
          </p>
        </div>

        <div className="dashboard-actions-group">
          {dateRange && (
            <div className="date-range-badge" title="Source dataset coverage">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/>
                <line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              <span>{formatDate(dateRange.start_date)} – {formatDate(dateRange.end_date)}</span>
            </div>
          )}

          <div className="filter-select-wrapper">
            <label htmlFor="plant-select" className="filter-label">Plant:</label>
            <select
              id="plant-select"
              className="plant-filter-select"
              value={selectedPlant || ''}
              onChange={(e) => onSelectPlant(e.target.value || null)}
            >
              <option value="">All Plants (TN-01 & KA-01)</option>
              <option value="IN-TN-01">Plant IN-TN-01 (Tamil Nadu)</option>
              <option value="IN-KA-01">Plant IN-KA-01 (Karnataka)</option>
            </select>
          </div>

          <button
            type="button"
            className={`dashboard-refresh-btn ${refreshing ? 'loading' : ''}`}
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh dashboard metrics"
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

      {lastRefreshed && (
        <div className="dashboard-meta-footer">
          <span className="live-pulse-dot"></span>
          <span>Verified deterministic records • Last updated: {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
        </div>
      )}
    </div>
  );
}
