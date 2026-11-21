import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { formatDateTime } from '../../utils/formatters';

function formatAnomalyType(type) {
  if (!type) return 'Operational Anomaly';
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function OperationalAttentionSection({
  findings = [],
  totalActiveCount = 0,
  loading = false,
  error = null,
  selectedPlant = null,
}) {
  const navigate = useNavigate();

  // Deduplicate findings by finding_id / finding_key
  const seenIds = new Set();
  const uniqueFindings = [];
  for (const f of findings || []) {
    const id = f.finding_id || f.finding_key;
    if (id && !seenIds.has(id)) {
      seenIds.add(id);
      uniqueFindings.push(f);
    }
  }

  // Priority sorting: CRITICAL -> HIGH -> MEDIUM -> LOW
  const severityRank = {
    CRITICAL: 1,
    HIGH: 2,
    MEDIUM: 3,
    LOW: 4,
    INFORMATIONAL: 5,
  };

  const sortedFindings = uniqueFindings
    .sort((a, b) => {
      const rankA = severityRank[a.severity?.toUpperCase()] || 99;
      const rankB = severityRank[b.severity?.toUpperCase()] || 99;
      if (rankA !== rankB) return rankA - rankB;
      const dateA = new Date(a.last_detected_at || a.created_at || 0).getTime();
      const dateB = new Date(b.last_detected_at || b.created_at || 0).getTime();
      return dateB - dateA;
    })
    .slice(0, 5); // Limit to top 5 high-priority findings on Dashboard

  const plantParam = selectedPlant ? `?plant=${encodeURIComponent(selectedPlant)}` : '';

  return (
    <section className="operational-attention-section" aria-label="Operational Attention Required">
      <div className="section-header-compact">
        <div className="section-title-group">
          <div className="section-title-row">
            <span className="attention-indicator-dot" aria-hidden="true" />
            <h2 className="section-title">Operational attention required</h2>
          </div>
          <p className="section-subtitle">
            Active high-priority anomalies, equipment deviations, and power factor alerts.
          </p>
        </div>
        <Link
          to={`/investigation-actions${plantParam}`}
          className="section-header-link"
          title="Open Investigation &amp; Actions Centre"
        >
          <span>View all findings {totalActiveCount > 0 ? `(${totalActiveCount})` : ''}</span>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </Link>
      </div>

      {loading ? (
        <div className="alert-list-skeleton">
          {[1, 2, 3].map((i) => (
            <div key={i} className="alert-row-skeleton">
              <div className="skeleton-pill" />
              <div className="skeleton-main" />
              <div className="skeleton-btn" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="alert-empty-box">
          <span className="error-text">Unable to load operational findings: {error}</span>
        </div>
      ) : sortedFindings.length === 0 ? (
        <div className="alert-empty-box">
          <div className="empty-shield-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <div className="empty-text-group">
            <h3 className="empty-heading">No critical operational findings returned for this period.</h3>
            <p className="empty-sub">
              Automated detector surveillance rules show no unresolved high-priority exceptions for the selected plant and time scope. Routine telemetry monitoring remains active.
            </p>
          </div>
        </div>
      ) : (
        <div className="alert-list-container" role="list">
          {sortedFindings.map((finding) => {
            const severity = (finding.severity || 'MEDIUM').toUpperCase();
            const title = finding.title || formatAnomalyType(finding.anomaly_type);
            const assetScope = [
              finding.plant_id && `Plant ${finding.plant_id}`,
              finding.meter_id,
              finding.line_id,
            ]
              .filter(Boolean)
              .join(' · ');

            const evidence =
              finding.current_actual_value != null
                ? `Measured ${finding.current_actual_value}${
                    finding.current_baseline_value != null ? ` vs baseline ${finding.current_baseline_value}` : ''
                  }`
                : finding.current_explanation || null;

            return (
              <div
                key={finding.finding_id}
                className={`alert-list-row severity-${severity.toLowerCase()}`}
                role="listitem"
              >
                {/* 1. Severity Badge */}
                <div className="alert-col-severity">
                  <span className={`alert-severity-badge ${severity.toLowerCase()}`}>
                    {severity}
                  </span>
                </div>

                {/* 2. Main Title and Evidence */}
                <div className="alert-col-main">
                  <div className="alert-title-row">
                    <span className="alert-item-title" title={title}>
                      {title}
                    </span>
                    <span className="alert-status-tag">{finding.status || 'NEW'}</span>
                  </div>
                  {evidence && (
                    <span className="alert-item-evidence" title={evidence}>
                      {evidence}
                    </span>
                  )}
                </div>

                {/* 3. Plant and Asset */}
                <div className="alert-col-asset">
                  <span className="alert-asset-text" title={assetScope}>
                    {assetScope || 'Plant-wide'}
                  </span>
                  <span className="alert-time-text">
                    {formatDateTime(finding.last_detected_at || finding.created_at)}
                  </span>
                </div>

                {/* 4. Action Button */}
                <div className="alert-col-action">
                  <button
                    type="button"
                    className="alert-investigate-btn"
                    onClick={() =>
                      navigate(`/investigation-actions?id=${encodeURIComponent(finding.finding_id)}`)
                    }
                    title={`Investigate ${finding.finding_id}`}
                  >
                    <span>Investigate</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
