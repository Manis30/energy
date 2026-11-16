import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { recommendationsApi } from '../services/recommendationsApi';
import { formatDateTime } from '../utils/formatters';
import RecommendationDrawer from './recommendations/RecommendationDrawer';
import StatusModal from './recommendations/StatusModal';
import ActionModal from './recommendations/ActionModal';
import GenerateModal from './recommendations/GenerateModal';
import ActionsTrackerTable from './recommendations/ActionsTrackerTable';
import './recommendations/recommendations.css';

const REC_STATUSES = ['ALL', 'OPEN', 'IN_PROGRESS', 'IMPLEMENTED', 'DISMISSED'];
const PRIORITIES = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'];
const CATEGORIES = [
  { value: 'ALL', label: 'All Categories' },
  { value: 'POWER_FACTOR_CORRECTION', label: 'Power Factor Correction' },
  { value: 'STANDBY_SHUTDOWN', label: 'Standby Shutdown' },
  { value: 'LOAD_BALANCING', label: 'Load Balancing / Peak Demand' },
  { value: 'OPERATIONAL_TUNING', label: 'Operational Tuning (SEC)' },
  { value: 'MAINTENANCE_INSPECTION', label: 'Maintenance & Electrical Inspection' },
];

export default function RecommendationsActions() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlFindingId = searchParams.get('finding_id');
  const urlRecId = searchParams.get('recommendation_id') || searchParams.get('id');
  const urlTab = searchParams.get('tab');
  const urlGenFindingId = searchParams.get('generate_finding_id');

  // Navigation View Tab
  const [activeTab, setActiveTab] = useState(urlTab === 'actions' ? 'actions' : 'recommendations');

  // Filter & Pagination State
  const [plantFilter, setPlantFilter] = useState('');
  const [findingFilter, setFindingFilter] = useState(urlFindingId || '');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  // Recommendations Data State
  const [recommendations, setRecommendations] = useState([]);
  const [totalRecs, setTotalRecs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Top-Level KPI State
  const [kpiCounts, setKpiCounts] = useState({
    total: 0,
    open: 0,
    inProgress: 0,
    implemented: 0,
    dismissed: 0,
    totalActions: 0,
    openActions: 0,
  });

  // Banner Feedback State
  const [bannerAlert, setBannerAlert] = useState(null);

  // Drawer & Modal States
  const [drawerRecId, setDrawerRecId] = useState(urlRecId || null);
  const [statusModal, setStatusModal] = useState({
    open: false,
    rec: null,
    targetStatus: 'DISMISSED',
    loading: false,
    error: null,
  });
  const [actionModal, setActionModal] = useState({
    open: false,
    mode: 'create', // 'create' | 'edit'
    recId: '',
    action: null,
    parentRec: null,
    loading: false,
    error: null,
  });
  const [generateModal, setGenerateModal] = useState({
    open: Boolean(urlGenFindingId),
    prefillFindingId: urlGenFindingId || '',
    loading: false,
    error: null,
  });

  // Synchronize URL search params
  useEffect(() => {
    if (urlFindingId && urlFindingId !== findingFilter) {
      setFindingFilter(urlFindingId);
      setOffset(0);
    }
    if (urlRecId && urlRecId !== drawerRecId) {
      setDrawerRecId(urlRecId);
    }
    if (urlTab === 'actions') {
      setActiveTab('actions');
    }
    if (urlGenFindingId) {
      setGenerateModal((prev) => ({
        ...prev,
        open: true,
        prefillFindingId: urlGenFindingId,
      }));
    }
  }, [urlFindingId, urlRecId, urlTab, urlGenFindingId]);

  // Debounce free-text search (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Load KPI counts from backend endpoints
  const loadKpiMetrics = useCallback(async () => {
    try {
      const [allRecs, openRecs, inProgRecs, implRecs, dismRecs, allActs, openActs] = await Promise.all([
        recommendationsApi.listRecommendations({ limit: 1 }),
        recommendationsApi.listRecommendations({ status: 'OPEN', limit: 1 }),
        recommendationsApi.listRecommendations({ status: 'IN_PROGRESS', limit: 1 }),
        recommendationsApi.listRecommendations({ status: 'IMPLEMENTED', limit: 1 }),
        recommendationsApi.listRecommendations({ status: 'DISMISSED', limit: 1 }),
        recommendationsApi.listActions({ limit: 1 }),
        recommendationsApi.listActions({ status: 'OPEN', limit: 1 }),
      ]);

      setKpiCounts({
        total: allRecs.total || 0,
        open: openRecs.total || 0,
        inProgress: inProgRecs.total || 0,
        implemented: implRecs.total || 0,
        dismissed: dismRecs.total || 0,
        totalActions: allActs.total || 0,
        openActions: openActs.total || 0,
      });
    } catch (kpiErr) {
      console.warn('Unable to load recommendation summary metrics:', kpiErr);
    }
  }, []);

  // Load paginated persistent recommendations
  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit, offset };
      if (plantFilter.trim()) params.plant_id = plantFilter.trim();
      if (findingFilter.trim()) params.finding_id = findingFilter.trim();
      if (statusFilter !== 'ALL') params.status = statusFilter;
      if (priorityFilter !== 'ALL') params.priority = priorityFilter;
      if (categoryFilter !== 'ALL') params.category = categoryFilter;

      const res = await recommendationsApi.listRecommendations(params);
      setRecommendations(res.items || []);
      setTotalRecs(res.total || 0);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
      setError(err.message || 'Unable to connect to the persistent recommendation service.');
    } finally {
      setLoading(false);
    }
  }, [plantFilter, findingFilter, statusFilter, priorityFilter, categoryFilter, limit, offset]);

  // Initial and reactive load
  useEffect(() => {
    loadRecommendations();
    loadKpiMetrics();
  }, [loadRecommendations, loadKpiMetrics, refreshTrigger]);

  const handleRefresh = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleResetFilters = () => {
    setPlantFilter('');
    setFindingFilter('');
    setStatusFilter('ALL');
    setPriorityFilter('ALL');
    setCategoryFilter('ALL');
    setSearchTerm('');
    setOffset(0);
    if (searchParams.get('finding_id')) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete('finding_id');
        return next;
      }, { replace: true });
    }
  };

  // Client-side text filter on title, description, recommendation_id, plant_id, finding_id
  const filteredRecommendations = useMemo(() => {
    if (!debouncedSearch.trim()) return recommendations;
    const q = debouncedSearch.toLowerCase();
    return recommendations.filter(
      (r) =>
        (r.title && r.title.toLowerCase().includes(q)) ||
        (r.description && r.description.toLowerCase().includes(q)) ||
        (r.recommendation_id && r.recommendation_id.toLowerCase().includes(q)) ||
        (r.plant_id && r.plant_id.toLowerCase().includes(q)) ||
        (r.finding_id && r.finding_id.toLowerCase().includes(q))
    );
  }, [recommendations, debouncedSearch]);

  // -------------------------------------------------------------------------
  // Status Modal Handlers
  // -------------------------------------------------------------------------
  const openStatusModal = (rec, targetStatus) => {
    setStatusModal({
      open: true,
      rec,
      targetStatus,
      loading: false,
      error: null,
    });
  };

  const handleStatusSubmit = async ({ status, reason, caller_attribution }) => {
    if (!statusModal.rec) return;
    setStatusModal((prev) => ({ ...prev, loading: true, error: null }));
    try {
      await recommendationsApi.updateRecommendationStatus(statusModal.rec.recommendation_id, {
        status,
        reason,
        caller_attribution,
      });

      setStatusModal({ open: false, rec: null, targetStatus: 'DISMISSED', loading: false, error: null });
      setBannerAlert({
        type: 'success',
        message: `Recommendation ${statusModal.rec.recommendation_id} transitioned to ${status}.`,
      });
      handleRefresh();
    } catch (err) {
      setStatusModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message || 'Failed to update recommendation status.',
      }));
    }
  };

  // -------------------------------------------------------------------------
  // Action Modal Handlers
  // -------------------------------------------------------------------------
  const openCreateActionModal = (recId, parentRec = null) => {
    setActionModal({
      open: true,
      mode: 'create',
      recId,
      action: null,
      parentRec,
      loading: false,
      error: null,
    });
  };

  const openEditActionModal = (action, parentRec = null) => {
    setActionModal({
      open: true,
      mode: 'edit',
      recId: action.recommendation_id,
      action,
      parentRec,
      loading: false,
      error: null,
    });
  };

  const handleActionSubmit = async (payload) => {
    setActionModal((prev) => ({ ...prev, loading: true, error: null }));
    try {
      if (actionModal.mode === 'create') {
        const created = await recommendationsApi.createAction(actionModal.recId, payload);
        setBannerAlert({
          type: 'success',
          message: `Corrective action ${created.action_id} created successfully.`,
        });
      } else {
        const updated = await recommendationsApi.updateAction(actionModal.action.action_id, payload);
        setBannerAlert({
          type: 'success',
          message: `Corrective action ${updated.action_id} updated successfully.`,
        });
      }

      setActionModal({ open: false, mode: 'create', recId: '', action: null, loading: false, error: null });
      handleRefresh();
    } catch (err) {
      setActionModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message || 'Failed to save corrective action.',
      }));
    }
  };

  // -------------------------------------------------------------------------
  // Generate Modal Handlers
  // -------------------------------------------------------------------------
  const handleGenerateSubmit = async ({ finding_id, caller_attribution }) => {
    setGenerateModal((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await recommendationsApi.generateFromFinding(finding_id, {
        caller_attribution,
      });

      setGenerateModal({ open: false, loading: false, error: null });
      setBannerAlert({
        type: 'success',
        message: res.message || `Generated ${res.generated_count} recommendation(s) for finding ${finding_id}.`,
      });
      handleRefresh();
    } catch (err) {
      setGenerateModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message || 'Failed to generate recommendations from finding.',
      }));
    }
  };

  return (
    <div className="recommendations-page">
      {/* Page Header */}
      <header className="recommendations-header">
        <div className="recommendations-heading">
          <span className="recommendations-eyebrow">Operational Intelligence &amp; Actions</span>
          <h1>Recommendations &amp; Corrective Actions</h1>
          <p>
            Evidence-grounded operational guidance, task ownership, due date tracking, and immutable audit history.
          </p>
        </div>
        <div className="recommendations-header-actions">
          <button
            type="button"
            className="btn-rec btn-rec-primary"
            onClick={() => setGenerateModal({ open: true, loading: false, error: null })}
          >
            + Generate from Finding
          </button>
          <button
            type="button"
            className="btn-rec btn-rec-secondary"
            onClick={handleRefresh}
            disabled={loading}
          >
            Refresh Data
          </button>
        </div>
      </header>

      {/* KPI Overview Grid */}
      <section className="recommendations-kpi-grid" aria-label="Recommendation Summary KPIs">
        <div className="recommendations-kpi-card kpi-total">
          <span className="recommendations-kpi-label">Total Recommendations</span>
          <strong className="recommendations-kpi-value">{kpiCounts.total.toLocaleString('en-IN')}</strong>
          <span className="recommendations-kpi-meta">Across all plants</span>
        </div>
        <div className="recommendations-kpi-card kpi-open">
          <span className="recommendations-kpi-label">Open / Evaluation</span>
          <strong className="recommendations-kpi-value">{kpiCounts.open.toLocaleString('en-IN')}</strong>
          <span className="recommendations-kpi-meta">Awaiting assignment</span>
        </div>
        <div className="recommendations-kpi-card kpi-in-progress">
          <span className="recommendations-kpi-label">In Progress (Active)</span>
          <strong className="recommendations-kpi-value">{kpiCounts.inProgress.toLocaleString('en-IN')}</strong>
          <span className="recommendations-kpi-meta">Under active investigation</span>
        </div>
        <div className="recommendations-kpi-card kpi-implemented">
          <span className="recommendations-kpi-label">Implemented</span>
          <strong className="recommendations-kpi-value">{kpiCounts.implemented.toLocaleString('en-IN')}</strong>
          <span className="recommendations-kpi-meta">Verified operational tuning</span>
        </div>
        <div className="recommendations-kpi-card kpi-dismissed">
          <span className="recommendations-kpi-label">Dismissed</span>
          <strong className="recommendations-kpi-value">{kpiCounts.dismissed.toLocaleString('en-IN')}</strong>
          <span className="recommendations-kpi-meta">Reviewed with logged reason</span>
        </div>
        <div className="recommendations-kpi-card kpi-actions">
          <span className="recommendations-kpi-label">Corrective Actions</span>
          <strong className="recommendations-kpi-value">
            {kpiCounts.openActions.toLocaleString('en-IN')} / {kpiCounts.totalActions.toLocaleString('en-IN')}
          </strong>
          <span className="recommendations-kpi-meta">Open / Total operational tasks</span>
        </div>
      </section>

      {/* Banner Notice / Notification */}
      {bannerAlert && (
        <div className={`recommendations-banner-alert ${bannerAlert.type}`}>
          <span>{bannerAlert.message}</span>
          <button
            type="button"
            className="btn-drawer-close"
            onClick={() => setBannerAlert(null)}
            style={{ fontSize: '1rem' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Primary View Switcher Tabs */}
      <nav className="recommendations-view-tabs" aria-label="Views">
        <button
          type="button"
          className={`recommendations-view-tab ${activeTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          Operational Recommendations
          <span className="recommendations-tab-count">{totalRecs}</span>
        </button>
        <button
          type="button"
          className={`recommendations-view-tab ${activeTab === 'actions' ? 'active' : ''}`}
          onClick={() => setActiveTab('actions')}
        >
          All Corrective Actions
          <span className="recommendations-tab-count">{kpiCounts.totalActions}</span>
        </button>
      </nav>

      {/* TAB 1: OPERATIONAL RECOMMENDATIONS VIEW */}
      {activeTab === 'recommendations' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Filters Toolbar */}
          <section className="recommendations-toolbar" aria-label="Recommendation Filters">
            <div className="recommendations-filters-row">
              <div className="recommendations-filter-item">
                <label>Plant / Facility</label>
                <input
                  type="text"
                  value={plantFilter}
                  onChange={(e) => {
                    setPlantFilter(e.target.value);
                    setOffset(0);
                  }}
                  placeholder="e.g. PLANT-01"
                />
              </div>

              <div className="recommendations-filter-item">
                <label>Status</label>
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setOffset(0);
                  }}
                >
                  {REC_STATUSES.map((st) => (
                    <option key={st} value={st}>
                      {st === 'ALL' ? 'All Statuses' : st}
                    </option>
                  ))}
                </select>
              </div>

              <div className="recommendations-filter-item">
                <label>Priority</label>
                <select
                  value={priorityFilter}
                  onChange={(e) => {
                    setPriorityFilter(e.target.value);
                    setOffset(0);
                  }}
                >
                  {PRIORITIES.map((pr) => (
                    <option key={pr} value={pr}>
                      {pr === 'ALL' ? 'All Priorities' : pr}
                    </option>
                  ))}
                </select>
              </div>

              <div className="recommendations-filter-item">
                <label>Category</label>
                <select
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(e.target.value);
                    setOffset(0);
                  }}
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="recommendations-filter-item search-grow">
                <label>Search Text / IDs</label>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search title, description, finding ID, recommendation ID…"
                />
              </div>

              <button
                type="button"
                className="btn-rec btn-rec-secondary"
                onClick={handleResetFilters}
                style={{ minHeight: '36px' }}
              >
                Reset
              </button>
            </div>
          </section>

          {/* Active Finding Filter Notice */}
          {findingFilter && (
            <div className="recommendations-banner-alert info" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <span>
                Filtered by Operational Finding: <strong style={{ fontFamily: 'monospace' }}>{findingFilter}</strong>
              </span>
              <button
                type="button"
                className="btn-rec btn-rec-secondary btn-rec-sm"
                onClick={() => {
                  setFindingFilter('');
                  setOffset(0);
                  setSearchParams((prev) => {
                    const next = new URLSearchParams(prev);
                    next.delete('finding_id');
                    return next;
                  }, { replace: true });
                }}
              >
                Clear Finding Filter
              </button>
            </div>
          )}

          {/* Recommendations Table Section */}
          <section className="recommendations-table-section">
            {error ? (
              <div className="recommendations-state-box">
                <h3 style={{ color: 'var(--status-danger, #ef4444)' }}>Unable to Load Recommendations</h3>
                <p>{error}</p>
                <button type="button" className="btn-rec btn-rec-secondary" onClick={loadRecommendations}>
                  Try Again
                </button>
              </div>
            ) : loading ? (
              <div className="recommendations-state-box">
                <span className="loading-spinner" />
                <h3>Loading Persistent Recommendations…</h3>
              </div>
            ) : filteredRecommendations.length === 0 ? (
              <div className="recommendations-state-box">
                <h3>No Recommendations Found</h3>
                <p>
                  No operational recommendations match the current filter criteria. Use "Generate from Finding" to create actionable recommendations from existing energy findings, or adjust your filters.
                </p>
                <button
                  type="button"
                  className="btn-rec btn-rec-primary"
                  onClick={() => setGenerateModal({ open: true, loading: false, error: null })}
                >
                  + Generate from Finding
                </button>
              </div>
            ) : (
              <>
                <div className="recommendations-table-container">
                  <table className="recommendations-table">
                    <thead>
                      <tr>
                        <th title="Operational urgency for implementing this recommendation (separate from finding severity)">Rec Priority</th>
                        <th>Recommendation Details</th>
                        <th>Category</th>
                        <th>Plant &amp; Finding</th>
                        <th>Status</th>
                        <th>Actions</th>
                        <th>Created</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRecommendations.map((rec) => {
                        const openCount = rec.open_action_count || 0;
                        const actionCount = rec.action_count || 0;
                        return (
                          <tr
                            key={rec.recommendation_id}
                            className="clickable-row"
                            onClick={() => setDrawerRecId(rec.recommendation_id)}
                          >
                            <td>
                              <span className={`badge-priority ${rec.priority.toLowerCase()}`}>
                                {rec.priority}
                              </span>
                            </td>
                            <td style={{ maxWidth: '340px' }}>
                              <strong style={{ display: 'block', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                                {rec.title}
                              </strong>
                              <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                {rec.recommendation_id}
                              </span>
                              <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.35, maxHeight: '38px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {rec.description}
                              </p>
                            </td>
                            <td>
                              <span className="badge-category">{rec.category.replace(/_/g, ' ')}</span>
                            </td>
                            <td>
                              <span style={{ display: 'block', fontWeight: 600 }}>{rec.plant_id}</span>
                              {rec.finding_id && (
                                <button
                                  type="button"
                                  className="btn-finding-link"
                                  title="View Evidence & Provenance in Findings Centre"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    navigate(`/investigation-actions?finding_id=${encodeURIComponent(rec.finding_id)}`);
                                  }}
                                >
                                  {rec.finding_id} &rarr;
                                </button>
                              )}
                            </td>
                            <td>
                              <span className={`badge-status ${rec.status.toLowerCase()}`}>
                                {rec.status}
                              </span>
                            </td>
                            <td>
                              <span className={`action-count-pill ${openCount > 0 ? 'has-open' : ''}`}>
                                {actionCount} {actionCount === 1 ? 'task' : 'tasks'}
                                {openCount > 0 && ` (${openCount} open)`}
                              </span>
                            </td>
                            <td>
                              <span style={{ fontSize: '0.78rem' }}>{formatDateTime(rec.created_at)}</span>
                            </td>
                            <td>
                              <button
                                type="button"
                                className="btn-rec btn-rec-secondary btn-rec-sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDrawerRecId(rec.recommendation_id);
                                }}
                              >
                                View Details
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination Controls */}
                <footer className="recommendations-pagination">
                  <span>
                    Showing <strong>{filteredRecommendations.length}</strong> of <strong>{totalRecs}</strong> recommendations
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
                      Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(totalRecs / limit))}
                    </span>
                    <button
                      type="button"
                      className="btn-rec btn-rec-secondary btn-rec-sm"
                      onClick={() => setOffset(offset + limit)}
                      disabled={offset + limit >= totalRecs}
                    >
                      Next
                    </button>
                  </div>
                </footer>
              </>
            )}
          </section>
        </div>
      ) : (
        /* TAB 2: ALL CORRECTIVE ACTIONS TRACKER */
        <ActionsTrackerTable
          onEditAction={openEditActionModal}
          onOpenRecommendation={(id) => {
            setDrawerRecId(id);
          }}
          refreshTrigger={refreshTrigger}
        />
      )}

      {/* Recommendation Detail Drawer */}
      <RecommendationDrawer
        recommendationId={drawerRecId}
        isOpen={Boolean(drawerRecId)}
        onClose={() => setDrawerRecId(null)}
        onStatusTransition={(rec, targetStatus) => openStatusModal(rec, targetStatus)}
        onAddAction={(recId, parentRec) => openCreateActionModal(recId, parentRec)}
        onEditAction={(act, parentRec) => openEditActionModal(act, parentRec)}
        onRecommendationUpdated={handleRefresh}
      />

      {/* Status Transition Modal */}
      <StatusModal
        isOpen={statusModal.open}
        rec={statusModal.rec}
        targetStatus={statusModal.targetStatus}
        onClose={() => setStatusModal({ open: false, rec: null, targetStatus: 'DISMISSED', loading: false, error: null })}
        onSubmit={handleStatusSubmit}
        loading={statusModal.loading}
        error={statusModal.error}
      />

      {/* Create / Edit Action Modal */}
      <ActionModal
        isOpen={actionModal.open}
        mode={actionModal.mode}
        recId={actionModal.recId}
        action={actionModal.action}
        parentRec={actionModal.parentRec}
        onClose={() => setActionModal({ open: false, mode: 'create', recId: '', action: null, parentRec: null, loading: false, error: null })}
        onSubmit={handleActionSubmit}
        loading={actionModal.loading}
        error={actionModal.error}
      />

      {/* Generate from Finding Modal */}
      <GenerateModal
        isOpen={generateModal.open}
        prefillFindingId={generateModal.prefillFindingId}
        onClose={() => setGenerateModal({ open: false, prefillFindingId: '', loading: false, error: null })}
        onSubmit={handleGenerateSubmit}
        loading={generateModal.loading}
        error={generateModal.error}
      />
    </div>
  );
}
