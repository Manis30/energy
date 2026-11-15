import React, { useState, useEffect, useCallback } from 'react';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDateTime } from '../../utils/formatters';

const ACTION_STATUSES = ['ALL', 'OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'];

/**
 * Filterable table view of all persistent corrective actions across recommendations.
 */
export default function ActionsTrackerTable({
  onEditAction,
  onOpenRecommendation,
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
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

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
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Filter Toolbar */}
      <section className="recommendations-toolbar" aria-label="Action Filters">
        <div className="recommendations-filters-row">
          <div className="recommendations-filter-item">
            <label>Action Status</label>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setOffset(0);
              }}
            >
              {ACTION_STATUSES.map((st) => (
                <option key={st} value={st}>
                  {st === 'ALL' ? 'All Statuses' : st}
                </option>
              ))}
            </select>
          </div>

          <div className="recommendations-filter-item">
            <label>Owner / Assignee</label>
            <input
              type="text"
              value={ownerSearch}
              onChange={(e) => {
                setOwnerSearch(e.target.value);
                setOffset(0);
              }}
              placeholder="Filter by owner substring…"
            />
          </div>

          <div className="recommendations-filter-item">
            <label>Recommendation ID</label>
            <input
              type="text"
              value={recFilter}
              onChange={(e) => {
                setRecFilter(e.target.value);
                setOffset(0);
              }}
              placeholder="e.g. REC-PLANT-01-…"
            />
          </div>

          <button
            type="button"
            className="btn-rec btn-rec-secondary"
            onClick={handleResetFilters}
            style={{ minHeight: '36px' }}
          >
            Reset Filters
          </button>
        </div>
      </section>

      {/* Actions Table Section */}
      <section className="recommendations-table-section">
        {error ? (
          <div className="recommendations-state-box">
            <h3 style={{ color: 'var(--status-danger, #ef4444)' }}>Unable to Load Actions</h3>
            <p>{error}</p>
            <button type="button" className="btn-rec btn-rec-secondary" onClick={loadActions}>
              Try Again
            </button>
          </div>
        ) : loading ? (
          <div className="recommendations-state-box">
            <span className="loading-spinner" />
            <h3>Loading Corrective Actions…</h3>
          </div>
        ) : actions.length === 0 ? (
          <div className="recommendations-state-box">
            <h3>No Corrective Actions Found</h3>
            <p>
              No actions match the current filter criteria. Create actions directly under an active recommendation in the Recommendations tab.
            </p>
          </div>
        ) : (
          <>
            <div className="recommendations-table-container">
              <table className="recommendations-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Action Details</th>
                    <th>Parent Recommendation</th>
                    <th>Assigned Owner</th>
                    <th>Due Date</th>
                    <th>Resolution Notes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((act) => (
                    <tr key={act.action_id}>
                      <td>
                        <span className={`badge-status ${act.status.toLowerCase()}`}>
                          {act.status}
                        </span>
                      </td>
                      <td style={{ maxWidth: '320px' }}>
                        <strong style={{ display: 'block', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                          {act.title}
                        </strong>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {act.action_id}
                        </span>
                        <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                          {act.description}
                        </p>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-rec btn-rec-secondary btn-rec-sm"
                          style={{ fontFamily: 'monospace', fontSize: '0.74rem' }}
                          onClick={() => onOpenRecommendation(act.recommendation_id)}
                          title="Open parent recommendation details, status, and evidence"
                        >
                          {act.recommendation_id} &rarr;
                        </button>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.8rem', color: act.owner ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                          {act.owner || 'Unassigned'}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.78rem' }}>
                          {act.due_date ? formatDateTime(act.due_date) : '—'}
                        </span>
                      </td>
                      <td style={{ maxWidth: '240px', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {act.resolution_notes ? (
                          <div style={{ maxHeight: '48px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {act.resolution_notes}
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>—</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-rec btn-rec-primary btn-rec-sm"
                          onClick={() => onEditAction(act)}
                        >
                          Update
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <footer className="recommendations-pagination">
              <span>
                Showing <strong>{actions.length}</strong> of <strong>{total}</strong> actions
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
                <span style={{ fontSize: '0.75rem', padding: '0 0.5rem' }}>
                  Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}
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

