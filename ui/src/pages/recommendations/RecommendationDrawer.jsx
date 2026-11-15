import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDateTime, formatNumber } from '../../utils/formatters';
import { CompactProvenanceSummary } from '../findings/ProvenanceExplorer';

/**
 * Slide-out detail drawer for viewing and managing an operational recommendation,
 * its deterministic telemetry evidence, linked corrective actions, and append-only audit trail.
 */
export default function RecommendationDrawer({
  recommendationId,
  isOpen,
  onClose,
  onStatusTransition,
  onAddAction,
  onEditAction,
  onRecommendationUpdated,
}) {
  const navigate = useNavigate();
  const [rec, setRec] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'actions' | 'audit'
  const [refreshingAudit, setRefreshingAudit] = useState(false);

  const handleRefreshAudit = async () => {
    if (!rec?.recommendation_id || refreshingAudit) return;
    setRefreshingAudit(true);
    try {
      const logs = await recommendationsApi.getRecommendationAudit(rec.recommendation_id);
      setRec((prev) => (prev ? { ...prev, audit_trail: logs } : null));
    } catch (err) {
      console.warn('Failed to refresh recommendation audit trail:', err);
    } finally {
      setRefreshingAudit(false);
    }
  };

  const handleNavigateToFinding = useCallback(() => {
    const targetFindingId = rec?.source_finding?.finding_id || rec?.finding_id;
    if (targetFindingId) {
      onClose();
      navigate(`/findings?finding_id=${encodeURIComponent(targetFindingId)}`);
    }
  }, [rec, onClose, navigate]);

  const loadDetail = useCallback(async () => {
    if (!recommendationId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await recommendationsApi.getRecommendationDetail(recommendationId);
      setRec(data);
    } catch (err) {
      console.error('Failed to load recommendation detail:', err);
      setError(err.message || 'Unable to load recommendation details.');
    } finally {
      setLoading(false);
    }
  }, [recommendationId]);

  useEffect(() => {
    if (isOpen && recommendationId) {
      setActiveTab('overview');
      loadDetail();
    } else {
      setRec(null);
    }
  }, [isOpen, recommendationId, loadDetail]);

  if (!isOpen) return null;

  const evidence = rec?.evidence_context || {};
  const actions = rec?.actions || [];
  const auditTrail = rec?.audit_trail || [];

  // Determine lineage category
  const lineageStatus = evidence.lineage_status || 'UNAVAILABLE';
  let lineageBadgeClass = 'badge-lineage unavailable';
  let lineageLabel = 'Lineage Unavailable';

  if (lineageStatus === 'AVAILABLE' || (evidence.source_table && evidence.source_record_id)) {
    lineageBadgeClass = 'badge-lineage single';
    lineageLabel = 'Single-Source Lineage';
  } else if (lineageStatus === 'MULTI_SOURCE') {
    lineageBadgeClass = 'badge-lineage multi';
    lineageLabel = 'Multi-Source Lineage';
  }

  const isClosed = rec?.status === 'DISMISSED' || rec?.status === 'IMPLEMENTED';

  const handleDirectTransition = async (targetStatus) => {
    try {
      setLoading(true);
      await recommendationsApi.updateRecommendationStatus(rec.recommendation_id, {
        status: targetStatus,
      });
      await loadDetail();
      if (onRecommendationUpdated) onRecommendationUpdated();
    } catch (err) {
      setError(err.message || `Failed to transition recommendation to ${targetStatus}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="recommendations-drawer-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rec-drawer-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="recommendations-drawer">
        <header className="recommendations-drawer-header">
          <div className="recommendations-drawer-title-group">
            <span className="recommendations-eyebrow">Operational Recommendation</span>
            <div className="recommendations-drawer-id" id="rec-drawer-title">
              {rec?.recommendation_id || recommendationId}
            </div>
            {rec && (
              <div className="recommendations-drawer-badges">
                <span className={`badge-status ${rec.status.toLowerCase()}`}>{rec.status}</span>
                <span className={`badge-priority ${rec.priority.toLowerCase()}`} title="Recommendation Operational Priority (Workflow Urgency)">
                  Rec Priority: {rec.priority}
                </span>
                <span className="badge-category">{rec.category.replace(/_/g, ' ')}</span>
                <span className="badge-category">Plant: {rec.plant_id}</span>
              </div>
            )}
          </div>
          <button
            type="button"
            className="btn-drawer-close"
            onClick={onClose}
            aria-label="Close drawer"
          >
            ×
          </button>
        </header>

        {/* Inner Navigation Tabs */}
        <div style={{ display: 'flex', gap: '0.5rem', padding: '0.65rem 1.5rem 0', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-surface)' }}>
          <button
            type="button"
            className={`recommendations-drawer-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview &amp; Evidence
          </button>
          <button
            type="button"
            className={`recommendations-drawer-tab-btn ${activeTab === 'actions' ? 'active' : ''}`}
            onClick={() => setActiveTab('actions')}
          >
            Corrective Actions ({actions.length})
          </button>
          <button
            type="button"
            className={`recommendations-drawer-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Audit Trail ({auditTrail.length})
          </button>
        </div>

        {/* Drawer Body Content */}
        <div className="recommendations-drawer-body">
          {error && (
            <div className="recommendations-banner-alert error">
              <span>{error}</span>
            </div>
          )}

          {loading && !rec ? (
            <div className="recommendations-state-box">
              <span className="loading-spinner" />
              <h3>Loading Recommendation Details…</h3>
            </div>
          ) : !rec ? (
            <div className="recommendations-state-box">
              <h3>Recommendation Not Found</h3>
              <p>The requested operational recommendation could not be retrieved from the server.</p>
            </div>
          ) : (
            <>
              {/* TAB 1: OVERVIEW & EVIDENCE */}
              {activeTab === 'overview' && (
                <>
                  {/* Title & Description Card */}
                  <div className="recommendations-detail-card" style={{ background: 'var(--bg-surface)' }}>
                    <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.05rem', color: 'var(--text-primary)' }}>
                      {rec.title}
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      {rec.description}
                    </p>
                  </div>

                  {/* Dismissal Justification Card (if dismissed) */}
                  {rec.status === 'DISMISSED' && (
                    <div className="recommendations-banner-alert error" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.35rem' }}>
                      <strong style={{ fontSize: '0.82rem' }}>Dismissal Justification (Recorded Review)</strong>
                      <span style={{ fontSize: '0.8rem' }}>{rec.dismissed_reason || 'Dismissed without written justification.'}</span>
                      <small style={{ color: 'var(--text-muted)' }}>Dismissed at: {formatDateTime(rec.dismissed_at)}</small>
                    </div>
                  )}

                  {/* Implementation Info Card (if implemented) */}
                  {rec.status === 'IMPLEMENTED' && (
                    <div className="recommendations-banner-alert success" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.35rem' }}>
                      <strong style={{ fontSize: '0.82rem' }}>Operational Implementation Recorded</strong>
                      <span style={{ fontSize: '0.8rem' }}>Implemented at: {formatDateTime(rec.implemented_at)}</span>
                    </div>
                  )}

                  {/* Deterministic Telemetry Evidence & Lineage Card */}
                  <div className="recommendations-detail-card recommendations-evidence-card">
                    <h4>
                      <span>Deterministic Telemetry Evidence</span>
                      <span className={lineageBadgeClass}>{lineageLabel}</span>
                    </h4>

                    <div className="recommendations-evidence-metrics">
                      <div>
                        <label>Measured Actual</label>
                        <strong>
                          {evidence.current_actual_value !== null && evidence.current_actual_value !== undefined
                            ? formatNumber(evidence.current_actual_value, 4)
                            : '—'}
                          {rec.category === 'POWER_FACTOR_CORRECTION' ? '' : ' kWh'}
                        </strong>
                      </div>
                      <div>
                        <label>Baseline / Expected</label>
                        <strong>
                          {evidence.current_baseline_value !== null && evidence.current_baseline_value !== undefined
                            ? formatNumber(evidence.current_baseline_value, 4)
                            : '—'}
                          {rec.category === 'POWER_FACTOR_CORRECTION' ? '' : ' kWh'}
                        </strong>
                      </div>
                      <div>
                        <label>Deviation Score</label>
                        <strong>
                          {evidence.current_deviation_score !== null && evidence.current_deviation_score !== undefined
                            ? formatNumber(evidence.current_deviation_score, 4)
                            : '—'}
                        </strong>
                      </div>
                    </div>

                    {/* Compact Lineage Breakdown */}
                    <CompactProvenanceSummary
                      findingId={rec.source_finding?.finding_id || rec.finding_id}
                      occurrenceId={rec.occurrence_id}
                      evidenceContext={evidence}
                      onViewFinding={rec.finding_id || rec.source_finding?.finding_id ? handleNavigateToFinding : undefined}
                    />

                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic', borderTop: '1px dashed var(--border-color)', paddingTop: '0.5rem' }}>
                      Deterministic telemetry evidence grounded directly in sensor records. No estimated financial savings, dollar benefits, or emissions reductions are fabricated.
                    </div>
                  </div>

                  {/* Linked Source Finding Snapshot (if present) */}
                  {rec.source_finding && (
                    <div className="recommendations-detail-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <h4 style={{ margin: 0 }}>Linked Operational Finding</h4>
                        <button
                          type="button"
                          className="btn-findings-link-compact"
                          onClick={handleNavigateToFinding}
                          title="Open complete evidence and occurrence history in Findings Centre"
                        >
                          Trace in Findings Centre &rarr;
                        </button>
                      </div>
                      <div className="recommendations-detail-grid">
                        <div className="recommendations-detail-field">
                          <label>Finding ID</label>
                          <span style={{ fontFamily: 'monospace' }}>{rec.source_finding.finding_id}</span>
                        </div>
                        <div className="recommendations-detail-field">
                          <label>Anomaly Type</label>
                          <span>{rec.source_finding.anomaly_type}</span>
                        </div>
                        <div className="recommendations-detail-field">
                          <label title="Statistical anomaly severity measured by detector">Anomaly Severity</label>
                          <span
                            className={`badge-priority ${rec.source_finding.severity?.toLowerCase() || 'medium'}`}
                            title="Statistical anomaly severity (distinct from recommendation priority)"
                          >
                            Severity: {rec.source_finding.severity}
                          </span>
                        </div>
                        <div className="recommendations-detail-field">
                          <label>Last Detected</label>
                          <span>{formatDateTime(rec.source_finding.last_detected_at)}</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn-inspect-finding"
                        onClick={handleNavigateToFinding}
                        title="Trace full evidence, historical occurrences, and source lineage in Findings Centre"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8"/>
                          <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        </svg>
                        <span>Inspect Finding Evidence in Findings Centre</span>
                      </button>
                    </div>
                  )}

                  {/* Metadata Timestamps Card */}
                  <div className="recommendations-detail-card">
                    <h4>Lifecycle Timestamps</h4>
                    <div className="recommendations-detail-grid">
                      <div className="recommendations-detail-field">
                        <label>Created At</label>
                        <span>{formatDateTime(rec.created_at)}</span>
                      </div>
                      <div className="recommendations-detail-field">
                        <label>Last Updated</label>
                        <span>{formatDateTime(rec.updated_at)}</span>
                      </div>
                      <div className="recommendations-detail-field">
                        <label>Implemented At</label>
                        <span>{formatDateTime(rec.implemented_at) || 'Not implemented'}</span>
                      </div>
                      <div className="recommendations-detail-field">
                        <label>Dismissed At</label>
                        <span>{formatDateTime(rec.dismissed_at) || 'Not dismissed'}</span>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* TAB 2: CORRECTIVE ACTIONS */}
              {activeTab === 'actions' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: '0.9rem' }}>Corrective Action Items</h4>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Track discrete engineering tasks and resolution notes under this recommendation.
                      </span>
                    </div>

                    <button
                      type="button"
                      className="btn-rec btn-rec-primary btn-rec-sm"
                      onClick={() => onAddAction(rec.recommendation_id, rec)}
                      disabled={isClosed}
                      title={isClosed ? 'Reopen recommendation before adding new actions.' : 'Create corrective action'}
                    >
                      + Add Corrective Action
                    </button>
                  </div>

                  {isClosed && (
                    <div className="recommendations-banner-alert info">
                      <span>
                        Corrective actions cannot be added under a {rec.status} recommendation. Please explicitly reopen the recommendation to resume operational tasks.
                      </span>
                    </div>
                  )}

                  {actions.length === 0 ? (
                    <div className="recommendations-state-box" style={{ background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
                      <h3>No Corrective Actions Assigned</h3>
                      <p>No operational tasks have been created under this recommendation yet. Click "+ Add Corrective Action" to log an action.</p>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {actions.map((act) => (
                        <div
                          key={act.action_id}
                          className="recommendations-detail-card"
                          style={{ borderLeft: `3px solid ${act.status === 'COMPLETED' ? '#10b981' : act.status === 'CANCELLED' ? '#ef4444' : '#3b82f6'}` }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem' }}>
                                <span className={`badge-status ${act.status.toLowerCase()}`}>{act.status}</span>
                                <strong style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>{act.title}</strong>
                              </div>
                              <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                {act.action_id}
                              </span>
                            </div>

                            <button
                              type="button"
                              className="btn-rec btn-rec-secondary btn-rec-sm"
                              onClick={() => onEditAction(act, rec)}
                            >
                              Update Action
                            </button>
                          </div>

                          <p style={{ margin: '0.4rem 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                            {act.description}
                          </p>

                          <div className="recommendations-detail-grid" style={{ marginTop: '0.4rem', fontSize: '0.75rem' }}>
                            <div className="recommendations-detail-field">
                              <label>Assigned Owner</label>
                              <span>{act.owner || 'Unassigned (Free-text)'}</span>
                            </div>
                            <div className="recommendations-detail-field">
                              <label>Due Date</label>
                              <span>{act.due_date ? formatDateTime(act.due_date) : 'No due date'}</span>
                            </div>
                            <div className="recommendations-detail-field">
                              <label>Completed At</label>
                              <span>{act.completed_at ? formatDateTime(act.completed_at) : 'Incomplete'}</span>
                            </div>
                            <div className="recommendations-detail-field">
                              <label>Audit Entries</label>
                              <span>{act.audit_trail?.length || 0} events</span>
                            </div>
                          </div>

                          {act.resolution_notes && (
                            <div style={{ marginTop: '0.3rem', padding: '0.5rem 0.65rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.78rem' }}>
                              <strong style={{ display: 'block', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>Resolution Notes:</strong>
                              <span style={{ color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{act.resolution_notes}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: AUDIT TRAIL */}
              {activeTab === 'audit' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: '0.9rem' }}>Append-Only Recommendation Audit History</h4>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        Immutable record of all lifecycle events and state transitions
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn-rec btn-rec-secondary btn-rec-sm"
                      onClick={handleRefreshAudit}
                      disabled={refreshingAudit}
                      title="Fetch latest audit trail from server"
                    >
                      {refreshingAudit ? 'Refreshing…' : '↻ Refresh Audit'}
                    </button>
                  </div>

                  {auditTrail.length === 0 ? (
                    <div className="recommendations-state-box" style={{ background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
                      <p>No audit log records recorded yet.</p>
                    </div>
                  ) : (
                    <div className="recommendations-table-section">
                      <table className="recommendations-table" style={{ fontSize: '0.78rem' }}>
                        <thead>
                          <tr>
                            <th>Timestamp</th>
                            <th>Action</th>
                            <th>State Transition</th>
                            <th>Attribution</th>
                            <th>Comment / Notes</th>
                            <th>Changed Fields</th>
                          </tr>
                        </thead>
                        <tbody>
                          {auditTrail.map((log) => {
                            const changed = log.changed_fields || {};
                            const hasChanges = Object.keys(changed).length > 0;
                            return (
                              <tr key={log.audit_id || log.id}>
                                <td style={{ whiteSpace: 'nowrap' }}>{formatDateTime(log.performed_at)}</td>
                                <td><strong>{log.action}</strong></td>
                                <td>
                                  {log.from_status
                                    ? `${log.from_status} → ${log.to_status}`
                                    : log.to_status || '—'}
                                </td>
                                <td>
                                  <span
                                    className={`badge-actor ${log.actor_type === 'SYSTEM_AUTOMATION' ? 'system' : 'unverified'}`}
                                    title="Unverified client attribution; not an authenticated identity"
                                  >
                                    {log.actor_attribution ? `${log.actor_type}: ${log.actor_attribution}` : log.actor_type}
                                  </span>
                                </td>
                                <td style={{ maxWidth: '240px' }}>
                                  {log.comment || '—'}
                                </td>
                                <td style={{ maxWidth: '240px', fontSize: '0.72rem' }}>
                                  {hasChanges ? (
                                    <table className="audit-diff-table">
                                      <tbody>
                                        {Object.entries(changed).map(([key, diff]) => (
                                          <tr key={key}>
                                            <td style={{ color: 'var(--text-muted)' }}>{key}:</td>
                                            <td>{String(diff.old ?? 'null')} → {String(diff.new ?? 'null')}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Drawer Action Bar / Transitions */}
        {rec && (
          <footer className="recommendations-drawer-actions">
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Current Status: <strong style={{ color: 'var(--text-primary)' }}>{rec.status}</strong>
            </span>

            <div className="recommendations-action-buttons">
              {rec.status === 'OPEN' && (
                <>
                  <button
                    type="button"
                    className="btn-rec btn-rec-primary btn-rec-sm"
                    onClick={() => handleDirectTransition('IN_PROGRESS')}
                    disabled={loading}
                  >
                    Start Work (IN_PROGRESS)
                  </button>
                  <button
                    type="button"
                    className="btn-rec btn-rec-success btn-rec-sm"
                    onClick={() => handleDirectTransition('IMPLEMENTED')}
                    disabled={loading}
                  >
                    Mark Implemented
                  </button>
                  <button
                    type="button"
                    className="btn-rec btn-rec-danger btn-rec-sm"
                    onClick={() => onStatusTransition(rec, 'DISMISSED')}
                    disabled={loading}
                  >
                    Dismiss…
                  </button>
                </>
              )}

              {rec.status === 'IN_PROGRESS' && (
                <>
                  <button
                    type="button"
                    className="btn-rec btn-rec-secondary btn-rec-sm"
                    onClick={() => handleDirectTransition('OPEN')}
                    disabled={loading}
                  >
                    Move to OPEN
                  </button>
                  <button
                    type="button"
                    className="btn-rec btn-rec-success btn-rec-sm"
                    onClick={() => handleDirectTransition('IMPLEMENTED')}
                    disabled={loading}
                  >
                    Mark Implemented
                  </button>
                  <button
                    type="button"
                    className="btn-rec btn-rec-danger btn-rec-sm"
                    onClick={() => onStatusTransition(rec, 'DISMISSED')}
                    disabled={loading}
                  >
                    Dismiss…
                  </button>
                </>
              )}

              {rec.status === 'IMPLEMENTED' && (
                <button
                  type="button"
                  className="btn-rec btn-rec-primary btn-rec-sm"
                  onClick={() => onStatusTransition(rec, 'IN_PROGRESS')}
                  disabled={loading}
                >
                  Reopen Recommendation…
                </button>
              )}

              {rec.status === 'DISMISSED' && (
                <button
                  type="button"
                  className="btn-rec btn-rec-primary btn-rec-sm"
                  onClick={() => onStatusTransition(rec, 'OPEN')}
                  disabled={loading}
                >
                  Reopen Recommendation…
                </button>
              )}
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}

