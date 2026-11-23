import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { marked } from 'marked';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDateTime } from '../../utils/formatters';

const REC_STATUS_OPTIONS = [
  { value: 'OPEN', label: 'Open (Open & In Progress)' },
  { value: 'ALL', label: 'All statuses' },
  { value: 'OPEN_ONLY', label: 'Open only' },
  { value: 'IN_PROGRESS', label: 'In progress' },
  { value: 'IMPLEMENTED', label: 'Implemented' },
  { value: 'DISMISSED', label: 'Dismissed' },
];

const REC_PRIORITY_OPTIONS = [
  { value: 'ALL', label: 'All priorities' },
  { value: 'CRITICAL', label: 'Critical' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
  { value: 'INFORMATIONAL', label: 'Informational' },
];

const REC_CATEGORY_OPTIONS = [
  { value: 'ALL', label: 'All categories' },
  { value: 'STANDBY_SHUTDOWN', label: 'Standby shutdown' },
  { value: 'POWER_FACTOR_CORRECTION', label: 'Power factor correction' },
  { value: 'LOAD_BALANCING', label: 'Load balancing / peak demand' },
  { value: 'OPERATIONAL_TUNING', label: 'Operational tuning (SEC)' },
  { value: 'MAINTENANCE_INSPECTION', label: 'Maintenance & electrical inspection' },
];

function formatDateClean(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const day = d.getDate();
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[d.getMonth()];
    const year = d.getFullYear();
    return `${day} ${month} ${year}`;
  } catch {
    return ts;
  }
}

function formatTimeClean(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function formatPriorityLabel(priority) {
  switch ((priority || '').toUpperCase()) {
    case 'CRITICAL': return 'Critical';
    case 'HIGH': return 'High';
    case 'MEDIUM': return 'Medium';
    case 'LOW': return 'Low';
    case 'INFORMATIONAL': return 'Informational';
    default: return priority || 'Medium';
  }
}

function formatStatusLabel(status) {
  switch ((status || '').toUpperCase()) {
    case 'OPEN': return 'Open';
    case 'IN_PROGRESS': return 'In progress';
    case 'IMPLEMENTED': return 'Implemented';
    case 'DISMISSED': return 'Dismissed';
    default: return status || 'Open';
  }
}

function formatCategoryLabel(cat) {
  switch ((cat || '').toUpperCase()) {
    case 'STANDBY_SHUTDOWN': return 'Standby shutdown';
    case 'POWER_FACTOR_CORRECTION': return 'Power factor correction';
    case 'LOAD_BALANCING': return 'Load balancing / peak demand';
    case 'OPERATIONAL_TUNING': return 'Operational tuning (SEC)';
    case 'MAINTENANCE_INSPECTION': return 'Maintenance & electrical inspection';
    default:
      if (!cat) return 'General';
      return cat.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
  }
}

/**
 * Render Markdown safely with raw HTML disabled and visibly labeled hypotheses.
 * Supports older plain-text records gracefully while preserving source values and units.
 */
function renderSafeMarkdown(rawText) {
  if (!rawText) return '';
  // 1. Disable raw HTML by escaping tags
  let text = String(rawText)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // 2. Visually highlight Hypothesis and Limitation labels
  text = text.replace(/(\*\*Hypothesis(?:\s*\d*)?:\*\*|Hypothesis(?:\s*\d*)?:)/gi, () => {
    return '<span class="rec-narrative-hypothesis-badge">Hypothesis</span>';
  });
  text = text.replace(/(\*\*Limitation(?:\s*\d*)?:\*\*|Limitation(?:\s*\d*)?:)/gi, () => {
    return '<span class="rec-narrative-limitation-badge">Limitation</span>';
  });

  // 3. Parse with marked (breaks enabled, gfm enabled)
  try {
    return marked.parse(text, { gfm: true, breaks: true });
  } catch (err) {
    console.warn('Failed to parse recommendation markdown:', err);
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${text}</pre>`;
  }
}

/**
 * Redesigned Enterprise Recommendations Directory Table
 * Five content-aware columns, compact 5-row pagination, inline expandable
 * investigation drawer with safe markdown rendering, and streamlined single-row toolbar.
 */
export default function RecommendationsDirectoryTable({
  onOpenRecommendation,
  onStatusChange,
  onAddAction,
  onFindingClick,
  onSynthesize,
  refreshTrigger = 0,
  selectedFindingId = null,
  onClearFindingFilter,
  selectedDate = '',
  plantScope = '',
  initialStatus = 'OPEN',
  onTotalCountChange,
}) {
  const [recommendations, setRecommendations] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter State
  const [plantFilter, setPlantFilter] = useState(plantScope || '');
  const [findingFilter, setFindingFilter] = useState(selectedFindingId || '');
  const [statusFilter, setStatusFilter] = useState(initialStatus);
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  // 5 recommendations per page by default (matching Corrective Actions)
  const [limit, setLimit] = useState(5);
  const [offset, setOffset] = useState(0);

  // Inline "View details" disclosure state
  const [expandedRecId, setExpandedRecId] = useState(null);

  // Sync prop changes for plant scope
  useEffect(() => {
    if (plantScope !== undefined) {
      setPlantFilter(plantScope || '');
      setOffset(0);
      setExpandedRecId(null);
    }
  }, [plantScope]);

  // Sync prop changes for finding filter
  useEffect(() => {
    if (selectedFindingId !== undefined) {
      setFindingFilter(selectedFindingId || '');
      setOffset(0);
      setExpandedRecId(null);
    }
  }, [selectedFindingId]);

  // Reset pagination when selectedDate changes
  useEffect(() => {
    setOffset(0);
    setExpandedRecId(null);
  }, [selectedDate]);

  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch matching set for backend filters
      const params = {
        limit: 500,
        offset: 0,
      };
      if (statusFilter === 'OPEN') {
        params.status = 'OPEN,IN_PROGRESS';
      } else if (statusFilter === 'OPEN_ONLY') {
        params.status = 'OPEN';
      } else if (statusFilter !== 'ALL') {
        params.status = statusFilter;
      }
      if (priorityFilter !== 'ALL') params.priority = priorityFilter;
      if (categoryFilter !== 'ALL') params.category = categoryFilter;
      if (plantFilter.trim()) params.plant_id = plantFilter.trim();
      if (findingFilter.trim()) params.finding_id = findingFilter.trim();

      const res = await recommendationsApi.listRecommendations(params);
      setRecommendations(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
      setError(err.message || 'Unable to retrieve persistent recommendations.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, priorityFilter, categoryFilter, plantFilter, findingFilter]);

  useEffect(() => {
    loadRecommendations();
  }, [loadRecommendations, refreshTrigger]);

  const handleResetFilters = () => {
    setPlantFilter(plantScope || '');
    setFindingFilter('');
    setStatusFilter(initialStatus);
    setPriorityFilter('ALL');
    setCategoryFilter('ALL');
    setSearchTerm('');
    setOffset(0);
    setExpandedRecId(null);
    if (onClearFindingFilter) onClearFindingFilter();
  };

  // Client-side text filter for search query and toolbar date filter
  const filteredItems = useMemo(() => {
    let list = recommendations;
    if (selectedDate) {
      list = list.filter((r) => r.created_at && r.created_at.startsWith(selectedDate));
    }
    if (!searchTerm.trim()) return list;
    const q = searchTerm.toLowerCase();
    return list.filter((r) =>
      (r.title && r.title.toLowerCase().includes(q)) ||
      (r.description && r.description.toLowerCase().includes(q)) ||
      (r.recommendation_id && r.recommendation_id.toLowerCase().includes(q)) ||
      (r.finding_id && r.finding_id.toLowerCase().includes(q)) ||
      (r.plant_id && r.plant_id.toLowerCase().includes(q)) ||
      (r.category && r.category.toLowerCase().includes(q))
    );
  }, [recommendations, searchTerm, selectedDate]);

  const totalCount = filteredItems.length;

  useEffect(() => {
    if (onTotalCountChange) {
      onTotalCountChange(totalCount);
    }
  }, [totalCount, onTotalCountChange]);

  const displayedItems = useMemo(() => {
    return filteredItems.slice(offset, offset + limit);
  }, [filteredItems, offset, limit]);

  const hasActiveFilters = Boolean(
    statusFilter !== initialStatus ||
    priorityFilter !== 'ALL' ||
    categoryFilter !== 'ALL' ||
    plantFilter.trim() !== (plantScope || '').trim() ||
    findingFilter.trim() ||
    searchTerm.trim() ||
    selectedDate
  );

  const startRecord = totalCount > 0 ? offset + 1 : 0;
  const endRecord = Math.min(offset + limit, totalCount);
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(totalCount / limit));

  return (
    <div className="recommendations-directory-container">
      {/* Compact Rebalanced Filter Toolbar */}
      <section className="recommendations-toolbar rec-directory-toolbar" aria-label="Recommendation filters">
        <div className="rec-toolbar-row">
          {/* Widest Field: Search */}
          <div className="rec-toolbar-item rec-toolbar-search">
            <div className="rec-search-input-wrap">
              <svg className="rec-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                id="rec-filter-search-input"
                type="text"
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setOffset(0);
                  setExpandedRecId(null);
                }}
                placeholder="Search recommendation"
                aria-label="Search recommendations"
              />
              {searchTerm && (
                <button
                  type="button"
                  className="rec-search-clear"
                  onClick={() => {
                    setSearchTerm('');
                    setOffset(0);
                    setExpandedRecId(null);
                  }}
                  aria-label="Clear search text"
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          {/* Plant Filter */}
          <div className="rec-toolbar-item rec-toolbar-plant">
            <input
              id="rec-filter-plant-input"
              type="text"
              value={plantFilter}
              onChange={(e) => {
                setPlantFilter(e.target.value);
                setOffset(0);
                setExpandedRecId(null);
              }}
              placeholder="e.g. IN-TN-01"
              aria-label="Filter by Plant"
            />
          </div>

          {/* Status Filter */}
          <div className="rec-toolbar-item rec-toolbar-status">
            <select
              id="rec-filter-status-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setOffset(0);
                setExpandedRecId(null);
              }}
              aria-label="Filter by Status"
            >
              {REC_STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Priority Filter */}
          <div className="rec-toolbar-item rec-toolbar-priority">
            <select
              id="rec-filter-priority-select"
              value={priorityFilter}
              onChange={(e) => {
                setPriorityFilter(e.target.value);
                setOffset(0);
                setExpandedRecId(null);
              }}
              aria-label="Filter by Priority"
            >
              {REC_PRIORITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Category Filter */}
          <div className="rec-toolbar-item rec-toolbar-category">
            <select
              id="rec-filter-category-select"
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setOffset(0);
                setExpandedRecId(null);
              }}
              aria-label="Filter by Category"
            >
              {REC_CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Reset Filters */}
          {hasActiveFilters && (
            <div className="rec-toolbar-item rec-toolbar-reset">
              <button
                type="button"
                className="btn-rec-filter-reset"
                onClick={handleResetFilters}
                title="Reset all filters to default"
              >
                Reset filters
              </button>
            </div>
          )}

          {/* Primary Action at the Right: "Create from finding" */}
          {onSynthesize && (
            <div className="rec-toolbar-item rec-toolbar-action">
              <button
                type="button"
                className="btn-rec btn-rec-primary btn-create-finding"
                onClick={onSynthesize}
                title="Create recommendation from operational finding"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                <span>Create from finding</span>
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Linked Finding Active Notice */}
      {findingFilter && (
        <div className="recommendations-banner-alert info" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <span>
            Filtered by operational finding: <strong style={{ fontFamily: 'monospace' }}>{findingFilter}</strong>
          </span>
          <button
            type="button"
            className="btn-rec btn-rec-secondary btn-rec-sm"
            onClick={() => {
              setFindingFilter('');
              setOffset(0);
              setExpandedRecId(null);
              if (onClearFindingFilter) onClearFindingFilter();
            }}
          >
            Clear finding filter
          </button>
        </div>
      )}

      {/* Directory Table Content */}
      <section className="recommendations-table-section rec-directory-table-section">
        {error ? (
          <div className="recommendations-state-box" style={{ padding: '2.5rem 1.5rem', textAlign: 'center' }}>
            <h3 style={{ color: 'var(--status-danger, #ef4444)', marginBottom: '0.5rem' }}>Unable to load recommendations</h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.85rem' }}>{error}</p>
            <button type="button" className="btn-rec btn-rec-secondary" onClick={loadRecommendations}>
              Retry connection
            </button>
          </div>
        ) : loading ? (
          <div className="recommendations-state-box" style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
            <span className="loading-spinner" style={{ margin: '0 auto 1rem' }} />
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-primary)' }}>Loading persistent recommendations…</h3>
          </div>
        ) : totalCount === 0 ? (
          <div className="recommendations-state-box" style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
            <h3 style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
              {hasActiveFilters ? 'No matching recommendations' : 'No recommendations available'}
            </h3>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '520px', margin: '0 auto 1.25rem', fontSize: '0.82rem' }}>
              {selectedDate
                ? `No recommendations match the selected date (${formatDateClean(selectedDate)}). Clear date or reset filters to view all.`
                : hasActiveFilters
                  ? 'No operational recommendations match your filter criteria. Try adjusting your status, priority, or search term.'
                  : 'No recommendations have been generated yet. Inspect findings in Investigation Centre to synthesize actionable recommendations.'}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
              {hasActiveFilters ? (
                <button type="button" className="btn-rec btn-rec-secondary" onClick={handleResetFilters}>
                  Reset filters
                </button>
              ) : onSynthesize ? (
                <button type="button" className="btn-rec btn-rec-primary" onClick={onSynthesize}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: '0.35rem' }}>
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  Create from finding
                </button>
              ) : null}
            </div>
          </div>
        ) : (
          <>
            <div className="recommendations-table-container">
              <table className="recommendations-table rec-directory-table" aria-label="Recommendations directory table">
                <colgroup>
                  <col className="rec-col-recommendation" />
                  <col className="rec-col-priority" />
                  <col className="rec-col-plant-finding" />
                  <col className="rec-col-status" />
                  <col className="rec-col-tasks" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Recommendation</th>
                    <th>Priority</th>
                    <th>Plant &amp; finding</th>
                    <th>Status</th>
                    <th>Tasks</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedItems.map((rec) => {
                    const openCount = rec.open_action_count || 0;
                    const actionCount = rec.action_count || 0;
                    const priorityClass = rec.priority ? rec.priority.toLowerCase() : 'medium';
                    const statusClass = rec.status ? rec.status.toLowerCase().replace(/_/g, '-') : 'open';
                    const isExpanded = expandedRecId === rec.recommendation_id;

                    return (
                      <React.Fragment key={rec.recommendation_id}>
                        <tr
                          className={`rec-directory-row ${isExpanded ? 'row-expanded' : ''}`}
                          tabIndex={0}
                          role="row"
                          onClick={() => onOpenRecommendation && onOpenRecommendation(rec.recommendation_id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              if (onOpenRecommendation) onOpenRecommendation(rec.recommendation_id);
                            }
                          }}
                        >
                          {/* 1. Recommendation (~45%) */}
                          <td className="rec-cell-main">
                            <div className="rec-primary-content">
                              <div
                                className="rec-title-heading"
                                title={rec.title}
                              >
                                {rec.title}
                              </div>
                              <div className="rec-meta-subline">
                                <span className="rec-id-text">{rec.recommendation_id}</span>
                                <span className="rec-subline-bullet">•</span>
                                <span className="rec-category-text">{formatCategoryLabel(rec.category)}</span>
                              </div>
                              <div className="rec-details-toggle-wrap">
                                <button
                                  type="button"
                                  className="btn-rec-toggle-disclosure"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedRecId(isExpanded ? null : rec.recommendation_id);
                                  }}
                                  aria-expanded={isExpanded}
                                >
                                  <span className="disclosure-indicator">{isExpanded ? '▲' : '▼'}</span>
                                  <span>{isExpanded ? 'Hide details' : 'View details'}</span>
                                </button>
                                <button
                                  type="button"
                                  className="btn-rec-drawer-inspect"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (onOpenRecommendation) onOpenRecommendation(rec.recommendation_id);
                                  }}
                                  title="Open full slide-out drawer with telemetry evidence and audit trail"
                                >
                                  Open drawer &rarr;
                                </button>
                              </div>
                            </div>
                          </td>

                          {/* 2. Priority (~12%) */}
                          <td className="rec-cell-priority">
                            <span className={`rec-priority-badge ${priorityClass}`}>
                              {formatPriorityLabel(rec.priority)}
                            </span>
                          </td>

                          {/* 3. Plant & Finding (~17%) */}
                          <td className="rec-cell-plant-finding">
                            <div className="rec-plant-finding-cell">
                              <div className="rec-plant-id">{rec.plant_id || '—'}</div>
                              {rec.finding_id ? (
                                <button
                                  type="button"
                                  className="rec-finding-link"
                                  title={`Inspect finding ${rec.finding_id}`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (onFindingClick) onFindingClick(rec.finding_id);
                                  }}
                                >
                                  <span>{rec.finding_id}</span>
                                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                    <polyline points="9 18 15 12 9 6" />
                                  </svg>
                                </button>
                              ) : (
                                <span className="rec-empty-finding">—</span>
                              )}
                            </div>
                          </td>

                          {/* 4. Status (~12%) */}
                          <td className="rec-cell-status">
                            <span className={`rec-status-badge ${statusClass}`}>
                              {formatStatusLabel(rec.status)}
                            </span>
                          </td>

                          {/* 5. Tasks (~14%) */}
                          <td className="rec-cell-tasks">
                            <div className="rec-tasks-cell-stack">
                              <button
                                type="button"
                                className={`rec-tasks-pill ${openCount > 0 ? 'has-open' : ''}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (onOpenRecommendation) onOpenRecommendation(rec.recommendation_id);
                                }}
                                title={`Inspect ${actionCount} corrective task${actionCount === 1 ? '' : 's'} in drawer`}
                              >
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
                                  <path d="m9 14 2 2 4-4" />
                                </svg>
                                <span>
                                  {actionCount} {actionCount === 1 ? 'task' : 'tasks'}
                                  {openCount > 0 ? ` (${openCount} open)` : ''}
                                </span>
                              </button>
                              {onAddAction && (
                                <button
                                  type="button"
                                  className="btn-rec btn-rec-secondary btn-rec-xs btn-add-action"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onAddAction(rec);
                                  }}
                                  title="Create corrective action for this recommendation"
                                >
                                  + Task
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>

                        {/* Inline Full-Width Investigation Details Panel */}
                        {isExpanded && (
                          <tr className="rec-details-panel-row">
                            <td colSpan={5} className="rec-details-panel-cell">
                              <div
                                className="rec-details-expanded-panel"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {/* Header with full untruncated title & tags */}
                                <div className="rec-panel-header">
                                  <div className="rec-panel-title-area">
                                    <h4 className="rec-panel-full-title">{rec.title}</h4>
                                    <div className="rec-panel-meta-tags">
                                      <span className="rec-panel-id-code">{rec.recommendation_id}</span>
                                      <span className="rec-panel-category-pill">{formatCategoryLabel(rec.category)}</span>
                                      <span className={`rec-priority-badge ${priorityClass}`}>
                                        {formatPriorityLabel(rec.priority)}
                                      </span>
                                      <span className={`rec-status-badge ${statusClass}`}>
                                        {formatStatusLabel(rec.status)}
                                      </span>
                                    </div>
                                  </div>
                                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                    {onAddAction && (
                                      <button
                                        type="button"
                                        className="btn-rec btn-rec-secondary btn-rec-sm"
                                        onClick={() => onAddAction(rec)}
                                        title="Create corrective action for this recommendation"
                                      >
                                        + Task
                                      </button>
                                    )}
                                    {onStatusChange && rec.status !== 'DISMISSED' && (
                                      <button
                                        type="button"
                                        className="btn-rec btn-rec-secondary btn-rec-sm"
                                        onClick={() => onStatusChange(rec.recommendation_id, 'DISMISSED')}
                                        title="Dismiss this recommendation"
                                      >
                                        Dismiss
                                      </button>
                                    )}
                                    {onStatusChange && rec.status !== 'IMPLEMENTED' && (
                                      <button
                                        type="button"
                                        className="btn-rec btn-rec-secondary btn-rec-sm"
                                        onClick={() => onStatusChange(rec.recommendation_id, 'IMPLEMENTED')}
                                        title="Mark recommendation as implemented"
                                      >
                                        Mark Implemented
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      className="btn-rec btn-rec-primary btn-rec-sm"
                                      onClick={() => onOpenRecommendation && onOpenRecommendation(rec.recommendation_id)}
                                    >
                                      Open in drawer &rarr;
                                    </button>
                                  </div>
                                </div>

                                {/* Full Investigation Narrative */}
                                <div className="rec-panel-narrative-section">
                                  <h5 className="rec-panel-section-title">Investigation narrative</h5>
                                  {rec.description ? (
                                    <div
                                      className="rec-markdown-narrative"
                                      dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(rec.description) }}
                                    />
                                  ) : (
                                    <p className="rec-empty-narrative">No investigation narrative recorded for this recommendation.</p>
                                  )}
                                </div>

                                {/* Metadata Footer Bar: Created Date, Plant, Finding Link */}
                                <div className="rec-panel-meta-footer">
                                  <div className="rec-meta-footer-item">
                                    <span className="meta-footer-key">Created:</span>
                                    <span className="meta-footer-val">
                                      {formatDateClean(rec.created_at)} {formatTimeClean(rec.created_at)}
                                    </span>
                                  </div>
                                  {rec.plant_id && (
                                    <div className="rec-meta-footer-item">
                                      <span className="meta-footer-key">Plant:</span>
                                      <span className="meta-footer-val">{rec.plant_id}</span>
                                    </div>
                                  )}
                                  {rec.finding_id && (
                                    <div className="rec-meta-footer-item">
                                      <span className="meta-footer-key">Source finding:</span>
                                      <button
                                        type="button"
                                        className="btn-link-clean"
                                        onClick={() => onFindingClick && onFindingClick(rec.finding_id)}
                                      >
                                        {rec.finding_id} &rarr;
                                      </button>
                                    </div>
                                  )}
                                  {rec.implemented_at && (
                                    <div className="rec-meta-footer-item">
                                      <span className="meta-footer-key">Implemented:</span>
                                      <span className="meta-footer-val">{formatDateTime(rec.implemented_at)}</span>
                                    </div>
                                  )}
                                  {rec.dismissed_at && (
                                    <div className="rec-meta-footer-item">
                                      <span className="meta-footer-key">Dismissed:</span>
                                      <span className="meta-footer-val">{formatDateTime(rec.dismissed_at)}</span>
                                    </div>
                                  )}
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

            {/* Pagination Row matching Corrective Actions Tracker */}
            <footer className="recommendations-pagination rec-directory-pagination">
              <span className="pagination-range-text">
                {totalCount > 0
                  ? `Showing ${startRecord}–${endRecord} of ${totalCount} recommendations`
                  : 'Showing 0 recommendations'}
              </span>
              <div className="recommendations-page-buttons">
                <button
                  type="button"
                  className="btn-rec btn-rec-secondary btn-rec-sm"
                  onClick={() => setOffset((o) => Math.max(0, o - limit))}
                  disabled={offset === 0}
                  aria-label="Previous page"
                >
                  Previous
                </button>
                <span className="pagination-page-indicator" style={{ fontSize: '0.75rem', padding: '0 0.5rem' }}>
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  className="btn-rec btn-rec-secondary btn-rec-sm"
                  onClick={() => setOffset((o) => o + limit)}
                  disabled={offset + limit >= totalCount}
                  aria-label="Next page"
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
