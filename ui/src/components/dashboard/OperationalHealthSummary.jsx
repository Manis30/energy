import React from 'react';
import { useNavigate } from 'react-router-dom';
import { formatNumber, formatPercent } from '../../utils/formatters';

export default function OperationalHealthSummary({
  activeFindingsCount = 0,
  criticalHighCount = 0,
  openRecommendationsCount = 0,
  productionSummary,
  loading = false,
  selectedPlant = null,
}) {
  const navigate = useNavigate();

  const goodRate =
    productionSummary?.good_rate != null ? Number(productionSummary.good_rate) : null;
  const rejectRate =
    productionSummary?.reject_rate != null ? Number(productionSummary.reject_rate) : null;

  const plantParam = selectedPlant ? `&plant=${encodeURIComponent(selectedPlant)}` : '';

  return (
    <section className="operational-health-strip" aria-label="Operational Health Summary">
      {/* Block 1: Active Findings */}
      <div
        className="health-strip-block"
        role="button"
        tabIndex={0}
        onClick={() => navigate(`/investigation-actions?status=ACTIVE${plantParam}`)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            navigate(`/investigation-actions?status=ACTIVE${plantParam}`);
          }
        }}
        title="View active findings queue in Investigation Centre"
      >
        <div className="health-block-icon purple" aria-hidden="true">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <div className="health-block-text">
          <div className="health-label-row">
            <span className="health-block-label">Active Findings</span>
          </div>
          <div className="health-block-val-group">
            <span className="health-block-value">
              {loading ? '…' : formatNumber(activeFindingsCount)}
            </span>
            <span className="health-block-sub">unresolved</span>
          </div>
        </div>
      </div>

      <div className="health-strip-divider" aria-hidden="true" />

      {/* Block 2: Critical / High Priority */}
      <div
        className={`health-strip-block ${criticalHighCount > 0 ? 'status-critical-active' : ''}`}
        role="button"
        tabIndex={0}
        onClick={() => navigate(`/investigation-actions?status=ACTIVE&severity=CRITICAL${plantParam}`)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            navigate(`/investigation-actions?status=ACTIVE&severity=CRITICAL${plantParam}`);
          }
        }}
        title="Filter high-priority critical findings"
      >
        <div
          className={`health-block-icon ${criticalHighCount > 0 ? 'red' : 'green'}`}
          aria-hidden="true"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            {criticalHighCount > 0 ? (
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            ) : (
              <polyline points="20 6 9 17 4 12" />
            )}
          </svg>
        </div>
        <div className="health-block-text">
          <div className="health-label-row">
            <span className="health-block-label">Critical / High</span>
            {criticalHighCount > 0 && (
              <span className="health-strip-pill danger">Action Req</span>
            )}
          </div>
          <div className="health-block-val-group">
            <span className={`health-block-value ${criticalHighCount > 0 ? 'val-danger' : ''}`}>
              {loading ? '…' : formatNumber(criticalHighCount)}
            </span>
            <span className="health-block-sub">
              {criticalHighCount > 0 ? 'priority signals' : 'none flagged'}
            </span>
          </div>
        </div>
      </div>

      <div className="health-strip-divider" aria-hidden="true" />

      {/* Block 3: Open Recommendations */}
      <div
        className="health-strip-block"
        role="button"
        tabIndex={0}
        onClick={() => navigate('/investigation-actions?tab=recommendations')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            navigate('/investigation-actions?tab=recommendations');
          }
        }}
        title="View recommendations directory"
      >
        <div className="health-block-icon blue" aria-hidden="true">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </div>
        <div className="health-block-text">
          <div className="health-label-row">
            <span className="health-block-label">Recommendations</span>
          </div>
          <div className="health-block-val-group">
            <span className="health-block-value">
              {loading ? '…' : formatNumber(openRecommendationsCount)}
            </span>
            <span className="health-block-sub">efficiency measures</span>
          </div>
        </div>
      </div>

      <div className="health-strip-divider" aria-hidden="true" />

      {/* Block 4: Production Quality Yield */}
      <div
        className="health-strip-block"
        role="button"
        tabIndex={0}
        onClick={() => navigate('/production-analytics')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            navigate('/production-analytics');
          }
        }}
        title="View production performance analytics"
      >
        <div className="health-block-icon teal" aria-hidden="true">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </div>
        <div className="health-block-text">
          <div className="health-label-row">
            <span className="health-block-label">Quality Yield</span>
          </div>
          <div className="health-block-val-group">
            <span className="health-block-value">
              {loading ? '…' : goodRate != null ? formatPercent(goodRate, 1) : 'Unavailable'}
            </span>
            <span className="health-block-sub">
              {rejectRate != null ? `${formatPercent(rejectRate, 1)} scrap rate` : 'first-pass yield'}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
