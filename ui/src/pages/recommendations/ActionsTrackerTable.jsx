import React, { useState, useEffect, useCallback } from 'react';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDate, formatDateTime } from '../../utils/formatters';

const ACTION_STATUS_OPTIONS = [
  { value: 'ALL', label: 'All statuses' },
  { value: 'OPEN', label: 'Open' },
  { value: 'IN_PROGRESS', label: 'In progress' },
  { value: 'ASSESSMENT_REQUESTED', label: 'Assessment requested' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
];

function formatLifecycleLabel(status) {
  switch ((status || '').toUpperCase()) {
    case 'OPEN':
      return 'Open';
    case 'IN_PROGRESS':
      return 'In progress';
    case 'ASSESSMENT_REQUESTED':
      return 'Assessment requested';
    case 'IMPLEMENTED':
      return 'Implemented';
    case 'COMPLETED':
      return 'Completed';
    case 'CANCELLED':
      return 'Cancelled';
    default:
      return status || 'Unknown';
  }
}

function getLifecycleBadgeClass(status) {
  const norm = (status || '').toLowerCase().replace(/_/g, '-');
  return `badge-action-lifecycle lifecycle-${norm}`;
}

function renderApprovalBadge(reviewStatus) {
  const norm = (reviewStatus || 'PENDING_REVIEW').toUpperCase();
  if (norm === 'APPROVED') {
    return <span className="action-sub-badge approval-approved">Approval: Approved</span>;
  }
  if (norm === 'REJECTED') {
    return <span className="action-sub-badge approval-rejected">Approval: Rejected</span>;
  }
  return <span className="action-sub-badge approval-pending">Approval: Pending review</span>;
}

function renderSavingsBadge(assessmentStatus) {
  const norm = (assessmentStatus || 'NONE').toUpperCase();
  if (norm === 'VERIFIED') {
    return <span className="action-sub-badge savings-verified">Savings: Verified</span>;
  }
  if (norm === 'INCONCLUSIVE') {
    return <span className="action-sub-badge savings-inconclusive">Savings: Inconclusive</span>;
  }
  return <span className="action-sub-badge savings-unverified">Savings: Not verified</span>;
}

function formatDueDate(dueStr) {
  if (!dueStr) return '—';
  if (dueStr.includes('T')) {
    return formatDateTime(dueStr);
  }
  return formatDate(dueStr);
}

/**
 * Enterprise-grade Corrective Actions Tracker Table with five content-aware columns,
 * inline collapsible drawer for full descriptions & resolution notes, clear multi-state badges,
 * rebalanced filter toolbar, and 5-row compact pagination.
 */
export default function ActionsTrackerTable({
  onEditAction,
  onOpenRecommendation,
  onOpenWorkflowModal,
  refreshTrigger = 0,
}) {
  const [actions, setActions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [ownerSearch, setOwnerSearch] = useState('');
  const [recFilter, setRecFilter] = useState('');

  // Pagination (25 actions per page by default)
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);

  // Inline disclosure state
  const [expandedActionId, setExpandedActionId] = useState(null);

  const loadActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit, offset };
      if (statusFilter !== 'ALL') params.status = statusFilter;
      if (ownerSearch.trim()) params.owner = ownerSearch.trim();
      if (recFilter.trim()) params.recommendation_id = recFilter.trim();

      const res = await recommendationsApi.listActions(params);
      setActions(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Failed to load actions:', err);
      setError(err.message || 'Unable to load corrective actions.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, ownerSearch, recFilter, limit, offset]);

  useEffect(() => {
    loadActions();
  }, [loadActions, refreshTrigger]);

  const handleResetFilters = () => {
    setStatusFilter('ALL');
    setOwnerSearch('');
    setRecFilter('');
    setOffset(0);
    setExpandedActionId(null);
  };

  const startRecord = total > 0 ? offset + 1 : 0;
  const endRecord = Math.min(offset + limit, total);
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="action-tracker-container">
      {/* Rebalanced Filter Toolbar */}
      <section className="recommendations-toolbar action-tracker-toolbar" aria-label="Action filters">
        <div className="recommendations-filters-row action-filters-row">
          <div className="recommendations-filter-item action-filter-status">
            <label htmlFor="action-filter-status-select">Status</label>
            <select
              id="action-filter-status-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setOffset(0);
                setExpandedActionId(null);
              }}
            >
              {ACTION_STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="recommendations-filter-item action-filter-input">
            <label htmlFor="action-filter-owner-input">Owner</label>
            <input
              id="action-filter-owner-input"
              type="text"
              value={ownerSearch}
              onChange={(e) => {
                setOwnerSearch(e.target.value);
                setOffset(0);
                setExpandedActionId(null);
              }}
              placeholder="Search owner"
            />
          </div>

          <div className="recommendations-filter-item action-filter-input">
            <label htmlFor="action-filter-rec-input">Parent recommendation</label>
            <input
              id="action-filter-rec-input"
              type="text"
              value={recFilter}
              onChange={(e) => {
                setRecFilter(e.target.value);
                setOffset(0);
                setExpandedActionId(null);
              }}
              placeholder="Search recommendation ID"
            />
          </div>

          <div className="action-filter-reset-wrap">
            <button
              type="button"
              className="btn-rec-filter-reset btn-action-reset"
              onClick={handleResetFilters}
            >
              Reset filters
            </button>
          </div>
        </div>
      </section>

      {/* Actions Table Section */}
      <section className="recommendations-table-section action-tracker-table-section">
        {error ? (
          <div className="recommendations-state-box">
            <h3 style={{ color: 'var(--status-danger, #ef4444)' }}>Unable to load actions</h3>
            <p>{error}</p>
            <button type="button" className="btn-rec btn-rec-secondary" onClick={loadActions}>
              Try again
            </button>
          </div>
        ) : loading ? (
          <div className="recommendations-state-box">
            <span className="loading-spinner" />
            <h3>Loading corrective actions…</h3>
          </div>
        ) : actions.length === 0 ? (
          <div className="recommendations-state-box">
            <h3>No corrective actions found</h3>
            <p>
              No actions match the current filter criteria. Create actions directly under an active recommendation in the Recommendations tab.
            </p>
          </div>
        ) : (
          <>
            <div className="recommendations-table-container">
              <table className="recommendations-table action-tracker-table">
                <colgroup>
                  <col className="action-tracker-col-action" />
                  <col className="action-tracker-col-status" />
                  <col className="action-tracker-col-owner" />
                  <col className="action-tracker-col-due" />
                  <col className="action-tracker-col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Status</th>
                    <th>Owner</th>
                    <th>Due date</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((act) => {
                    const isExpanded = expandedActionId === act.action_id;
                    return (
                      <React.Fragment key={act.action_id}>
                        <tr className={`action-tracker-row ${isExpanded ? 'row-expanded' : ''}`}>
                          {/* Column 1: Action (~40%) */}
                          <td className="action-cell-main">
                            <div className="action-primary-content">
                              <div className="action-title-heading">{act.title}</div>
                              <div className="action-id-code">{act.action_id}</div>
                              <div className="action-parent-link-container">
                                <button
                                  type="button"
                                  className="btn-action-parent-rec"
                                  onClick={() => onOpenRecommendation(act.recommendation_id)}
                                  title="Open parent recommendation details, status, and evidence"
                                >
                                  <span className="rec-link-label">Parent:</span> {act.recommendation_id} &rarr;
                                </button>
                              </div>
                              <div className="action-details-toggle-container">
                                <button
                                  type="button"
                                  className="btn-action-toggle-disclosure"
                                  onClick={() => setExpandedActionId(isExpanded ? null : act.action_id)}
                                  aria-expanded={isExpanded}
                                >
                                  <span className="disclosure-indicator">{isExpanded ? '▲' : '▼'}</span>
                                  {isExpanded ? 'Hide details' : 'Show details'}
                                </button>
                              </div>
                            </div>
                          </td>

                          {/* Column 2: Status (~22%) */}
                          <td className="action-cell-status">
                            <div className="action-status-stack">
                              <span className={getLifecycleBadgeClass(act.status)}>
                                {formatLifecycleLabel(act.status)}
                              </span>
                              {renderApprovalBadge(act.review_status)}
                              {renderSavingsBadge(act.assessment_status)}
                            </div>
                          </td>

                          {/* Column 3: Owner (~16%) */}
                          <td className="action-cell-owner">
                            <div className="action-owner-display">
                              <span
                                className="owner-name"
                                style={{ color: act.owner ? 'var(--text-primary)' : 'var(--text-muted)' }}
                              >
                                {act.owner || 'Unassigned'}
                              </span>
                              {act.responsible_team && (
                                <span className="owner-team-tag">{act.responsible_team}</span>
                              )}
                            </div>
                          </td>

                          {/* Column 4: Due date (~11%) */}
                          <td className="action-cell-due-date">
                            <span className="due-date-value">{formatDueDate(act.due_date)}</span>
                          </td>

                          {/* Column 5: Actions (~13%) */}
                          <td className="action-cell-actions">
                            <div className="action-row-buttons">
                              <button
                                type="button"
                                className="btn-rec btn-rec-primary btn-rec-sm"
                                onClick={() => onEditAction(act)}
                              >
                                Update
                              </button>
                              {onOpenWorkflowModal && (
                                <button
                                  type="button"
                                  className="btn-rec btn-rec-secondary btn-rec-sm"
                                  onClick={() => onOpenWorkflowModal(act)}
                                  title="Open M&V measurement plan and savings verification"
                                >
                                  M&amp;V plan
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>

                        {/* Inline Drawer Expansion for Description & Resolution Notes */}
                        {isExpanded && (
                          <tr className="action-expanded-drawer-row">
                            <td colSpan={5} className="action-expanded-drawer-cell">
                              <div className="action-drawer-panel">
                                <div className="action-drawer-grid">
                                  <div className="action-drawer-field">
                                    <span className="action-drawer-label">Full description</span>
                                    <p className="action-drawer-text">
                                      {act.description || 'No description provided.'}
                                    </p>
                                  </div>
                                  {act.resolution_notes && (
                                    <div className="action-drawer-field">
                                      <span className="action-drawer-label">Resolution notes</span>
                                      <p className="action-drawer-text">{act.resolution_notes}</p>
                                    </div>
                                  )}
                                  <div className="action-drawer-meta-bar">
                                    {act.affected_equipment && (
                                      <div className="drawer-meta-item">
                                        <span className="meta-key">Equipment:</span>
                                        <span className="meta-val">{act.affected_equipment}</span>
                                      </div>
                                    )}
                                    {act.measurement_meter_id && (
                                      <div className="drawer-meta-item">
                                        <span className="meta-key">Boundary meter:</span>
                                        <span className="meta-val">{act.measurement_meter_id}</span>
                                      </div>
                                    )}
                                    {act.responsible_team && (
                                      <div className="drawer-meta-item">
                                        <span className="meta-key">Responsible team:</span>
                                        <span className="meta-val">{act.responsible_team}</span>
                                      </div>
                                    )}
                                    {act.created_at && (
                                      <div className="drawer-meta-item">
                                        <span className="meta-key">Created:</span>
                                        <span className="meta-val">{formatDateTime(act.created_at)}</span>
                                      </div>
                                    )}
                                    {act.completed_at && (
                                      <div className="drawer-meta-item">
                                        <span className="meta-key">Completed:</span>
                                        <span className="meta-val">{formatDateTime(act.completed_at)}</span>
                                      </div>
                                    )}
                                    {act.reviewed_by && (
                                      <div className="drawer-meta-item">
                                        <span className="meta-key">Reviewer:</span>
                                        <span className="meta-val">{act.reviewed_by}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls outside scroll container */}
            <footer className="recommendations-pagination action-tracker-pagination">
              <span className="pagination-range-text">
                {total > 0
                  ? `Showing ${startRecord}–${endRecord} of ${total} actions`
                  : 'Showing 0 actions'}
              </span>
              <div className="recommendations-page-buttons">
                <button
                  type="button"
                  className="btn-rec btn-rec-secondary btn-rec-sm"
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                >
                  Previous
                </button>
                <span className="pagination-page-indicator" style={{ fontSize: '0.75rem', padding: '0 0.5rem' }}>
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  className="btn-rec btn-rec-secondary btn-rec-sm"
                  onClick={() => setOffset(offset + limit)}
                  disabled={offset + limit >= total}
                >
                  Next
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
