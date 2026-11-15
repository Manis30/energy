import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { findingsApi } from '../services/findingsApi';
import { recommendationsApi } from '../services/recommendationsApi';
import { formatDateTime } from '../utils/formatters';
import {
  EvidenceProvenanceCard,
  LineageStatusBadge,
  getLineageStatus,
} from './findings/ProvenanceExplorer';
import './findings/findings-centre.css';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'];
const STATUSES = ['ACTIVE', 'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'REOPENED'];

// Detector family filters matching backend DETECTOR_FAMILY_MAP
const ANOMALY_TYPES = [
  { value: 'statistical_zscore', label: 'Statistical Z-Score (Spikes & Drops)' },
  { value: 'rolling_baseline', label: 'Rolling Baseline (Spikes & Drops)' },
  { value: 'low_power_factor', label: 'Low Power Factor' },
  { value: 'zero_production_standby', label: 'Zero-Production Standby' },
];

function formatVal(value, decimals = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) {
    return 'Unavailable';
  }
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatTs(value) {
  if (!value) return 'Timestamp unavailable';
  return formatDateTime(value);
}

export default function FindingsCentre() {
  // Filters & Pagination State
  const [plantId, setPlantId] = useState('');
  const [statusFilter, setStatusFilter] = useState('ACTIVE');
  const [severityFilter, setSeverityFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  // Data & KPI State
  const [findingsData, setFindingsData] = useState({ items: [], total: 0 });
  const [kpiCounts, setKpiCounts] = useState({
    active: 0,
    new: 0,
    investigating: 0,
    resolved: 0,
    criticalHigh: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bannerNotice, setBannerNotice] = useState(null);

  // Syncing State
  const [syncing, setSyncing] = useState(false);

  // Drawer & Detail State
  const [selectedFindingId, setSelectedFindingId] = useState(null);
  const [findingDetail, setFindingDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [activeHistoryTab, setActiveHistoryTab] = useState('occurrences'); // 'occurrences' | 'audit'
  const [expandedOccurrences, setExpandedOccurrences] = useState({});

  // URL Query Params integration for deep-linking from Recommendations or external views
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlFindingId = searchParams.get('finding_id') || searchParams.get('id');

  // Recommendation Generation State from Finding
  const [generatingRec, setGeneratingRec] = useState(false);
  const [recGenerationNotice, setRecGenerationNotice] = useState(null);

  const handleGenerateRecommendationFromFinding = async (findingId) => {
    if (!findingId || generatingRec) return;
    setGeneratingRec(true);
    setRecGenerationNotice(null);
    try {
      const res = await recommendationsApi.generateFromFinding(findingId);
      setRecGenerationNotice({
        type: 'success',
        message: res.message || `Generated ${res.generated_count || 0} recommendation(s) for finding ${findingId}.`,
        recommendations: res.recommendations || [],
      });
    } catch (err) {
      setRecGenerationNotice({
        type: 'error',
        message: err.message || 'Failed to generate recommendations from finding.',
      });
    } finally {
      setGeneratingRec(false);
    }
  };

  useEffect(() => {
    if (urlFindingId && urlFindingId !== selectedFindingId) {
      setSelectedFindingId(urlFindingId);
    }
  }, [urlFindingId, selectedFindingId]);

  const handleCloseDrawer = useCallback(() => {
    setSelectedFindingId(null);
    setExpandedOccurrences({});
    if (searchParams.get('finding_id') || searchParams.get('id')) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete('finding_id');
        next.delete('id');
        return next;
      }, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const toggleOccurrenceLineage = (occId) => {
    setExpandedOccurrences((prev) => ({
      ...prev,
      [occId]: !prev[occId],
    }));
  };

  // Action Modal State
  const [actionModal, setActionModal] = useState({
    open: false,
    action: null, // 'ACKNOWLEDGE' | 'INVESTIGATE' | 'RESOLVE' | 'REOPEN' | 'ADD_NOTE'
    finding: null,
    commentOrNote: '',
    callerAttribution: '',
    loading: false,
    error: null,
  });

  // Short debounce for search term (300ms) to prevent query spam and reset offset
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Load KPI counts from actual API without fabrication - critical/high scoped to ACTIVE findings
  const loadKpiMetrics = useCallback(async (currentPlantId) => {
    try {
      const baseParam = currentPlantId ? { plant_id: currentPlantId } : {};
      const [activeRes, newRes, invRes, resRes, critRes, highRes] = await Promise.all([
        findingsApi.listFindings({ ...baseParam, status: 'ACTIVE', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'NEW', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'INVESTIGATING', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'RESOLVED', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'ACTIVE', severity: 'CRITICAL', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'ACTIVE', severity: 'HIGH', limit: 1 }),
      ]);

      setKpiCounts({
        active: activeRes.total || 0,
        new: newRes.total || 0,
        investigating: invRes.total || 0,
        resolved: resRes.total || 0,
        criticalHigh: (critRes.total || 0) + (highRes.total || 0),
      });
    } catch (kpiErr) {
      console.warn('Unable to load KPI summary metrics:', kpiErr);
    }
  }, []);

  // Load Paginated Findings using server-side search and filters
  const loadFindings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        limit,
        offset,
      };
      if (plantId) params.plant_id = plantId;
      if (statusFilter && statusFilter !== 'ALL') params.status = statusFilter;
      if (severityFilter && severityFilter !== 'ALL') params.severity = severityFilter;
      if (typeFilter && typeFilter !== 'ALL') params.anomaly_type = typeFilter;
      if (debouncedSearch && debouncedSearch.trim()) params.search = debouncedSearch.trim();

      const result = await findingsApi.listFindings(params);
      setFindingsData(result || { items: [], total: 0 });
    } catch (err) {
      console.error('Failed to load operational findings:', err);
      setError(err.message || 'Unable to connect to Findings API.');
    } finally {
      setLoading(false);
    }
  }, [plantId, statusFilter, severityFilter, typeFilter, debouncedSearch, limit, offset]);

  // Initial and reactive load on filter changes
  useEffect(() => {
    loadFindings();
  }, [loadFindings]);

  // KPI metrics reload when plant filter changes
  useEffect(() => {
    loadKpiMetrics(plantId);
  }, [loadKpiMetrics, plantId]);

  // Load specific finding detail when selected
  const fetchFindingDetail = useCallback(async (fId) => {
    if (!fId) {
      setFindingDetail(null);
      return;
    }
    setLoadingDetail(true);
    try {
      const detail = await findingsApi.getFindingDetail(fId);
      setFindingDetail(detail);
    } catch (err) {
      console.error(`Failed to load details for finding ${fId}:`, err);
      setBannerNotice({
        type: 'error',
        message: `Failed to load detail for ${fId}: ${err.message}`,
      });
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (selectedFindingId) {
      fetchFindingDetail(selectedFindingId);
    } else {
      setFindingDetail(null);
    }
  }, [selectedFindingId, fetchFindingDetail]);

  // Trigger telemetry anomaly sync with concurrency guard feedback
  const handleSyncTelemetry = async () => {
    if (syncing) return;
    setSyncing(true);
    setBannerNotice({ type: 'info', message: 'Running anomaly detectors and synchronizing operational findings...' });
    try {
      const syncResult = await findingsApi.syncFindings({
        plant_id: plantId || undefined,
        caller_attribution: 'FindingsCentre-UI',
      });
      setBannerNotice({
        type: 'success',
        message: `Telemetry Synchronized! Evaluated: ${syncResult.total_anomalies_evaluated}, Created: ${syncResult.new_findings_created}, Updated: ${syncResult.existing_findings_updated}, Reopened: ${syncResult.findings_reopened}, Evidence Recorded: ${syncResult.occurrences_recorded}, Conflicts Preserved: ${syncResult.conflicts_preserved || 0}.`,
      });
      await loadFindings();
      await loadKpiMetrics(plantId);
      if (selectedFindingId) {
        await fetchFindingDetail(selectedFindingId);
      }
    } catch (err) {
      console.error('Sync failure:', err);
      const isConflict = err.status === 409 || (err.message && err.message.includes('already in progress'));
      setBannerNotice({
        type: isConflict ? 'info' : 'error',
        message: isConflict
          ? 'Synchronization Guard Notice: A telemetry findings synchronization is already actively running. Please wait for the current run to finish.'
          : `Sync failed: ${err.message}`,
      });
    } finally {
      setSyncing(false);
    }
  };

  // Server-side filtered findings items
  const displayedItems = findingsData.items;

  // Modal open helpers
  const openActionModal = (action, finding) => {
    setActionModal({
      open: true,
      action,
      finding,
      commentOrNote: '',
      callerAttribution: '',
      loading: false,
      error: null,
    });
  };

  const closeActionModal = () => {
    setActionModal({
      open: false,
      action: null,
      finding: null,
      commentOrNote: '',
      callerAttribution: '',
      loading: false,
      error: null,
    });
  };

  // Execute lifecycle transition
  const handleExecuteAction = async () => {
    const { action, finding, commentOrNote, callerAttribution } = actionModal;
    if (!finding) return;

    if ((action === 'RESOLVE' || action === 'REOPEN' || action === 'ADD_NOTE') && !commentOrNote.trim()) {
      setActionModal((prev) => ({
        ...prev,
        error: action === 'RESOLVE'
          ? 'Resolution notes are required to resolve this finding.'
          : action === 'REOPEN'
          ? 'A documented justification reason is required to reopen this finding.'
          : 'Investigation notes cannot be empty.',
      }));
      return;
    }

    setActionModal((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const attribution = callerAttribution.trim() || undefined;
      let updated = null;

      if (action === 'ACKNOWLEDGE') {
        updated = await findingsApi.acknowledgeFinding(finding.finding_id, {
          comment: commentOrNote.trim() || undefined,
          caller_attribution: attribution,
        });
      } else if (action === 'INVESTIGATE') {
        updated = await findingsApi.startInvestigation(finding.finding_id, {
          investigation_notes: commentOrNote.trim() || undefined,
          caller_attribution: attribution,
        });
      } else if (action === 'ADD_NOTE') {
        updated = await findingsApi.addInvestigationNotes(finding.finding_id, {
          notes: commentOrNote.trim(),
          caller_attribution: attribution,
        });
      } else if (action === 'RESOLVE') {
        updated = await findingsApi.resolveFinding(finding.finding_id, {
          resolution_notes: commentOrNote.trim(),
          caller_attribution: attribution,
        });
      } else if (action === 'REOPEN') {
        updated = await findingsApi.reopenFinding(finding.finding_id, {
          reason: commentOrNote.trim(),
          caller_attribution: attribution,
        });
      }

      // Successful update confirmed by API
      setBannerNotice({
        type: 'success',
        message: `Finding ${finding.finding_id} successfully updated to status ${updated?.status || action}.`,
      });

      closeActionModal();
      await loadFindings();
      await loadKpiMetrics(plantId);
      if (selectedFindingId === finding.finding_id) {
        await fetchFindingDetail(finding.finding_id);
      }
    } catch (err) {
      console.error(`Action ${action} failed:`, err);
      setActionModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message || 'Operation rejected by backend lifecycle rules.',
      }));
    }
  };

  // Pagination navigation
  const totalPages = Math.ceil((findingsData.total || 0) / limit) || 1;
  const currentPage = Math.floor(offset / limit) + 1;

  const handlePrevPage = () => {
    if (offset > 0) setOffset(Math.max(0, offset - limit));
  };

  const handleNextPage = () => {
    if (offset + limit < (findingsData.total || 0)) setOffset(offset + limit);
  };

  const hasActiveFilters = Boolean(
    debouncedSearch || (statusFilter !== 'ALL' && statusFilter !== 'ACTIVE') || severityFilter || typeFilter || plantId
  );

  return (
    <div className="findings-centre-page">
      {/* Header Banner */}
      <header className="findings-header">
        <div className="findings-heading">
          <span className="findings-eyebrow">Operational Intelligence</span>
          <h1>Operational Findings Centre</h1>
          <p>
            Persisted, deduplicated energy & power quality findings with deterministic lifecycle tracking and audit history.
          </p>
        </div>
        <div className="findings-header-actions">
          <button
            type="button"
            className="btn-findings btn-findings-primary"
            onClick={handleSyncTelemetry}
            disabled={syncing}
            title={syncing ? 'Synchronization currently in progress' : 'Run anomaly telemetry synchronization'}
          >
            {syncing ? '⏳ Syncing Telemetry (Guard Active)...' : '⚡ Sync Anomaly Telemetry'}
          </button>
          <button
            type="button"
            className="btn-findings"
            onClick={() => {
              loadFindings();
              loadKpiMetrics(plantId);
            }}
            disabled={loading}
          >
            ↻ Refresh List
          </button>
        </div>
      </header>

      {/* Banner Notice */}
      {bannerNotice && (
        <div className={`findings-banner-alert ${bannerNotice.type}`}>
          <span>{bannerNotice.message}</span>
          <button
            type="button"
            className="btn-drawer-close"
            onClick={() => setBannerNotice(null)}
            aria-label="Dismiss alert"
          >
            ✕
          </button>
        </div>
      )}

      {/* Top KPI Cards (Live Database Metrics) */}
      <section className="findings-kpi-grid">
        <div className="findings-kpi-card kpi-active">
          <span className="findings-kpi-label">Active Findings</span>
          <span className="findings-kpi-value">{kpiCounts.active.toLocaleString()}</span>
          <span className="findings-kpi-meta">Open operational anomalies requiring action</span>
        </div>
        <div className="findings-kpi-card kpi-new">
          <span className="findings-kpi-label">New Detections</span>
          <span className="findings-kpi-value">{kpiCounts.new.toLocaleString()}</span>
          <span className="findings-kpi-meta">Awaiting engineering acknowledgment</span>
        </div>
        <div className="findings-kpi-card kpi-investigating">
          <span className="findings-kpi-label">Under Investigation</span>
          <span className="findings-kpi-value">{kpiCounts.investigating.toLocaleString()}</span>
          <span className="findings-kpi-meta">Active root-cause diagnostic workflow</span>
        </div>
        <div className="findings-kpi-card kpi-resolved">
          <span className="findings-kpi-label">Resolved</span>
          <span className="findings-kpi-value">{kpiCounts.resolved.toLocaleString()}</span>
          <span className="findings-kpi-meta">Verified root-cause resolutions</span>
        </div>
        <div className="findings-kpi-card kpi-critical">
          <span className="findings-kpi-label">Critical / High Severity (Active)</span>
          <span className="findings-kpi-value">{kpiCounts.criticalHigh.toLocaleString()}</span>
          <span className="findings-kpi-meta">Active operational or cost risk</span>
        </div>
      </section>

      {/* Filter and Search Toolbar */}
      <section className="findings-toolbar">
        <div className="findings-filters-row">
          <div className="findings-filter-item search-grow">
            <label htmlFor="findings-search">Database Search</label>
            <input
              id="findings-search"
              type="text"
              placeholder="Search across Finding ID, Plant, Meter, Line, or Anomaly Type..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="findings-filter-item">
            <label htmlFor="findings-plant-filter">Plant</label>
            <select
              id="findings-plant-filter"
              value={plantId}
              onChange={(e) => {
                setPlantId(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All Plants</option>
              <option value="IN-TN-01">IN-TN-01 (Chennai)</option>
            </select>
          </div>

          <div className="findings-filter-item">
            <label htmlFor="findings-status-filter">Status</label>
            <select
              id="findings-status-filter"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setOffset(0);
              }}
            >
              <option value="ALL">All Statuses</option>
              {STATUSES.map((st) => (
                <option key={st} value={st}>
                  {st === 'ACTIVE' ? 'Active (Excludes Resolved)' : st}
                </option>
              ))}
            </select>
          </div>

          <div className="findings-filter-item">
            <label htmlFor="findings-severity-filter">Severity</label>
            <select
              id="findings-severity-filter"
              value={severityFilter}
              onChange={(e) => {
                setSeverityFilter(e.target.value);
                setOffset(0);
              }}
            >
              <option value="ALL">All Severities</option>
              {SEVERITIES.map((sev) => (
                <option key={sev} value={sev}>{sev}</option>
              ))}
            </select>
          </div>

          <div className="findings-filter-item">
            <label htmlFor="findings-type-filter">Anomaly Category</label>
            <select
              id="findings-type-filter"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setOffset(0);
              }}
            >
              <option value="ALL">All Categories</option>
              {ANOMALY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className="findings-filter-item" style={{ minWidth: '90px' }}>
            <label htmlFor="findings-limit-filter">Rows</label>
            <select
              id="findings-limit-filter"
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>
      </section>

      {/* Findings Table List */}
      <section className="findings-table-wrapper">
        {loading ? (
          <div className="findings-state-box">
            <div className="findings-eyebrow">Loading Data</div>
            <h3>Retrieving operational findings...</h3>
            <p>Executing server-side query against persistent findings repository.</p>
          </div>
        ) : error ? (
          <div className="findings-state-box">
            <div className="findings-eyebrow" style={{ color: '#ef4444' }}>Service Notice</div>
            <h3>Unable to load findings</h3>
            <p>{error}</p>
            <button
              type="button"
              className="btn-findings btn-findings-primary"
              onClick={loadFindings}
            >
              Retry
            </button>
          </div>
        ) : displayedItems.length === 0 ? (
          <div className="findings-state-box">
            <div className="findings-eyebrow">No Findings Found</div>
            <h3>
              {debouncedSearch
                ? `No findings matching "${debouncedSearch}"`
                : hasActiveFilters
                ? 'No findings match active filter criteria'
                : 'No operational findings recorded'}
            </h3>
            <p>
              {debouncedSearch
                ? 'Try checking for typos or resetting your search query.'
                : hasActiveFilters
                ? 'Try clearing or broadening your status, severity, or plant filters to inspect other records.'
                : 'No persistent operational findings have been synchronized yet. Click "Sync Anomaly Telemetry" to evaluate telemetry records.'}
            </p>
            {hasActiveFilters && (
              <button
                type="button"
                className="btn-findings"
                style={{ marginTop: '0.5rem' }}
                onClick={() => {
                  setSearchTerm('');
                  setDebouncedSearch('');
                  setStatusFilter('ACTIVE');
                  setSeverityFilter('');
                  setTypeFilter('');
                  setPlantId('');
                  setOffset(0);
                }}
              >
                Clear Search & Filters
              </button>
            )}
          </div>
        ) : (
          <table className="findings-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Severity</th>
                <th>Finding ID</th>
                <th>Category</th>
                <th>Plant & Scope</th>
                <th>Occurrences</th>
                <th>Measured Value</th>
                <th>Baseline</th>
                <th>Last Detected</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {displayedItems.map((f) => (
                <tr
                  key={f.finding_id}
                  className={selectedFindingId === f.finding_id ? 'selected' : ''}
                  onClick={() => setSelectedFindingId(f.finding_id)}
                >
                  <td>
                    <span className={`badge-status ${f.status.toLowerCase()}`}>
                      {f.status}
                    </span>
                  </td>
                  <td>
                    <span className={`badge-severity ${f.severity.toLowerCase()}`}>
                      {f.severity}
                    </span>
                  </td>
                  <td>
                    <strong style={{ fontFamily: 'monospace' }}>{f.finding_id}</strong>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                      <span>{(f.anomaly_type || '').replace(/_/g, ' ')}</span>
                      {f.latest_lineage_status && (
                        <LineageStatusBadge status={f.latest_lineage_status} isCompact />
                      )}
                    </div>
                  </td>
                  <td>
                    <span>{f.plant_id}</span>
                    {f.meter_id && <span style={{ color: 'var(--text-muted)' }}> · {f.meter_id}</span>}
                    {f.line_id && <span style={{ color: 'var(--text-muted)' }}> · {f.line_id}</span>}
                  </td>
                  <td>
                    <span className="badge-recurrence">
                      {f.occurrence_count} {f.occurrence_count > 1 ? 'hits' : 'hit'}
                    </span>
                  </td>
                  <td>
                    <strong>{formatVal(f.current_actual_value, 2)}</strong>
                  </td>
                  <td>
                    {f.current_baseline_value !== null && f.current_baseline_value !== undefined
                      ? formatVal(f.current_baseline_value, 2)
                      : <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Unavailable</span>}
                  </td>
                  <td>
                    <span style={{ fontSize: '0.78rem' }}>{formatTs(f.last_detected_at)}</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      type="button"
                      className="btn-findings"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedFindingId(f.finding_id);
                      }}
                    >
                      View Detail →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination Bar */}
        {!loading && findingsData.total > 0 && (
          <div className="findings-pagination">
            <span>
              Showing {Math.min(offset + 1, findingsData.total)} to{' '}
              {Math.min(offset + limit, findingsData.total)} of {findingsData.total} findings
              {debouncedSearch && ` (matching "${debouncedSearch}")`}
            </span>
            <div className="findings-page-buttons">
              <button
                type="button"
                className="btn-findings"
                onClick={handlePrevPage}
                disabled={offset === 0}
              >
                ← Previous
              </button>
              <span>
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                className="btn-findings"
                onClick={handleNextPage}
                disabled={offset + limit >= findingsData.total}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Finding Detail Slide-Out Drawer */}
      {selectedFindingId && (
        <div className="findings-drawer-backdrop" onClick={handleCloseDrawer}>
          <aside
            className="findings-drawer"
            onClick={(e) => e.stopPropagation()}
            aria-label="Finding Details"
          >
            {/* Drawer Header */}
            <header className="findings-drawer-header">
              <div className="findings-drawer-title-group">
                <span className="findings-eyebrow">Operational Finding Details</span>
                <span className="findings-drawer-id">{selectedFindingId}</span>
                {findingDetail && (
                  <div className="findings-drawer-badges">
                    <span className={`badge-status ${findingDetail.status.toLowerCase()}`}>
                      {findingDetail.status}
                    </span>
                    <span className={`badge-severity ${findingDetail.severity.toLowerCase()}`}>
                      {findingDetail.severity}
                    </span>
                    <span className="badge-recurrence">
                      {findingDetail.occurrence_count} {findingDetail.occurrence_count > 1 ? 'Recurrences' : 'Occurrence'}
                    </span>
                    {findingDetail.status === 'REOPENED' && (
                      <span className="badge-status reopened">
                        Reopened Recurring Issue
                      </span>
                    )}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="btn-drawer-close"
                onClick={handleCloseDrawer}
                aria-label="Close details"
              >
                ✕
              </button>
            </header>

            {/* Drawer Body */}
            {loadingDetail ? (
              <div className="findings-state-box" style={{ margin: 'auto' }}>
                <div className="findings-eyebrow">Loading Detail</div>
                <h3>Fetching finding records and audit trail...</h3>
              </div>
            ) : !findingDetail ? (
              <div className="findings-state-box" style={{ margin: 'auto' }}>
                <h3>Finding record unavailable</h3>
              </div>
            ) : (
              <div className="findings-drawer-body">
                {/* Identity & Scope Card */}
                <div className="findings-detail-card">
                  <h4>Identity & Operational Scope</h4>
                  <div className="findings-detail-grid">
                    <div className="findings-detail-field">
                      <label>Plant ID</label>
                      <span>{findingDetail.plant_id}</span>
                    </div>
                    <div className="findings-detail-field">
                      <label>Meter ID</label>
                      <span>{findingDetail.meter_id || 'N/A (Plant-wide / Process)'}</span>
                    </div>
                    <div className="findings-detail-field">
                      <label>Line ID</label>
                      <span>{findingDetail.line_id || 'N/A (Metered Asset)'}</span>
                    </div>
                    <div className="findings-detail-field">
                      <label>Anomaly Type</label>
                      <span>{findingDetail.anomaly_type.replace(/_/g, ' ')}</span>
                    </div>
                  </div>
                </div>

                {/* Evidence & Telemetry Card */}
                <div className="findings-detail-card">
                  <h4>Current Telemetry Evidence</h4>
                  <div className="findings-detail-grid">
                    <div className="findings-detail-field">
                      <label>Current Measured Value</label>
                      <span style={{ fontSize: '1.1rem', color: 'var(--brand-purple, #6366f1)' }}>
                        {formatVal(findingDetail.current_actual_value, 4)}
                      </span>
                    </div>
                    <div className="findings-detail-field">
                      <label>Baseline Reference</label>
                      <span>
                        {findingDetail.current_baseline_value !== null && findingDetail.current_baseline_value !== undefined
                          ? formatVal(findingDetail.current_baseline_value, 4)
                          : 'Explicitly Unavailable / Rolling'}
                      </span>
                    </div>
                    <div className="findings-detail-field">
                      <label>Deviation / Z-Score</label>
                      <span>{formatVal(findingDetail.current_deviation_score, 2)}</span>
                    </div>
                    <div className="findings-detail-field">
                      <label>First Detected</label>
                      <span style={{ fontSize: '0.78rem' }}>{formatTs(findingDetail.first_detected_at)}</span>
                    </div>
                    <div className="findings-detail-field">
                      <label>Last Detected</label>
                      <span style={{ fontSize: '0.78rem' }}>{formatTs(findingDetail.last_detected_at)}</span>
                    </div>
                  </div>
                  {findingDetail.current_explanation && (
                    <div className="findings-evidence-explanation">
                      <strong>Detector Diagnosis: </strong>
                      {findingDetail.current_explanation}
                    </div>
                  )}
                </div>

                {/* Evidence & Data Provenance Explorer Section */}
                {findingDetail.occurrences && findingDetail.occurrences.length > 0 ? (
                  <EvidenceProvenanceCard
                    occurrence={findingDetail.occurrences[0]}
                    finding={findingDetail}
                    isPrimary
                    title="Latest Evidence & Data Provenance"
                  />
                ) : (
                  <div className="findings-detail-card">
                    <h4>Evidence & Data Provenance</h4>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      No detection occurrences are recorded for this finding.
                    </div>
                  </div>
                )}

                {/* Investigation Notes Card */}
                <div className="findings-detail-card">
                  <h4>
                    <span>Investigation Progress Notes</span>
                    {['NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'REOPENED'].includes(findingDetail.status) && (
                      <button
                        type="button"
                        className="btn-findings"
                        style={{ padding: '0.2rem 0.6rem', fontSize: '0.72rem' }}
                        onClick={() => openActionModal('ADD_NOTE', findingDetail)}
                      >
                        + Add Diagnostic Note
                      </button>
                    )}
                  </h4>
                  {findingDetail.investigation_notes ? (
                    <div className="findings-notes-display">
                      {findingDetail.investigation_notes}
                    </div>
                  ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic' }}>
                      No investigation notes have been recorded yet.
                    </div>
                  )}
                </div>

                {/* Resolution Notes (if resolved) */}
                {findingDetail.status === 'RESOLVED' && (
                  <div className="findings-detail-card" style={{ borderColor: 'rgba(16, 185, 129, 0.4)' }}>
                    <h4 style={{ color: '#10b981' }}>Resolution Notes</h4>
                    <div className="findings-notes-display">
                      {findingDetail.resolution_notes || 'Resolved without detailed remarks.'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      Resolved at: {formatTs(findingDetail.resolved_at)}
                    </div>
                  </div>
                )}

                {/* Reopen Reason (if reopened) */}
                {findingDetail.status === 'REOPENED' && (
                  <div className="findings-detail-card" style={{ borderColor: 'rgba(168, 85, 247, 0.4)' }}>
                    <h4 style={{ color: '#a855f7' }}>Reopen Justification</h4>
                    <div className="findings-notes-display">
                      {findingDetail.reopen_reason || 'Reopened due to recurring detection telemetry.'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      Reopened at: {formatTs(findingDetail.reopened_at)}
                    </div>
                  </div>
                )}

                {/* History Section: Occurrences and Audit Trail */}
                <div className="findings-detail-card">
                  <div className="findings-history-tabs">
                    <button
                      type="button"
                      className={`findings-tab-btn ${activeHistoryTab === 'occurrences' ? 'active' : ''}`}
                      onClick={() => setActiveHistoryTab('occurrences')}
                    >
                      Occurrence Telemetry ({findingDetail.occurrences?.length || 0})
                    </button>
                    <button
                      type="button"
                      className={`findings-tab-btn ${activeHistoryTab === 'audit' ? 'active' : ''}`}
                      onClick={() => setActiveHistoryTab('audit')}
                    >
                      Audit Trail ({findingDetail.audit_trail?.length || 0})
                    </button>
                  </div>

                  {activeHistoryTab === 'occurrences' ? (
                    <div style={{ overflowX: 'auto' }}>
                      <table className="findings-subtable">
                        <thead>
                          <tr>
                            <th>Occurrence TS</th>
                            <th>Measured</th>
                            <th>Baseline</th>
                            <th>Deviation</th>
                            <th>Severity</th>
                            <th>Lineage Status</th>
                            <th>Data Provenance</th>
                            <th>Explanation</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(findingDetail.occurrences || []).map((occ) => {
                            const occStatus = getLineageStatus(occ);
                            const isExpanded = Boolean(expandedOccurrences[occ.occurrence_id]);
                            return (
                              <React.Fragment key={occ.occurrence_id}>
                                <tr>
                                  <td style={{ whiteSpace: 'nowrap' }}>{formatTs(occ.occurrence_ts)}</td>
                                  <td><strong>{formatVal(occ.actual_value, 2)}</strong></td>
                                  <td>{occ.baseline_value ? formatVal(occ.baseline_value, 2) : '—'}</td>
                                  <td>{formatVal(occ.deviation_score, 2)}</td>
                                  <td>
                                    <span className={`badge-severity ${occ.severity.toLowerCase()}`}>
                                      {occ.severity}
                                    </span>
                                  </td>
                                  <td>
                                    <LineageStatusBadge
                                      status={occStatus}
                                      streamCount={occ.source_records?.length}
                                      isCompact
                                    />
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      className={`btn-toggle-provenance ${isExpanded ? 'active' : ''}`}
                                      onClick={() => toggleOccurrenceLineage(occ.occurrence_id)}
                                      title="Inspect source record IDs, tables, and upload batch provenance"
                                    >
                                      {isExpanded ? '▲ Hide Lineage' : '▼ Inspect Lineage'}
                                    </button>
                                  </td>
                                  <td style={{ maxWidth: '240px', fontSize: '0.72rem' }}>
                                    {occ.explanation || '—'}
                                  </td>
                                </tr>
                                {isExpanded && (
                                  <tr className="provenance-expanded-row">
                                    <td colSpan={8} style={{ padding: '0.75rem 1rem', background: 'var(--bg-hover)' }}>
                                      <EvidenceProvenanceCard
                                        occurrence={occ}
                                        finding={findingDetail}
                                        title={`Historical Occurrence Provenance (${formatTs(occ.occurrence_ts)})`}
                                      />
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table className="findings-subtable">
                        <thead>
                          <tr>
                            <th>Timestamp</th>
                            <th>Action</th>
                            <th>State Transition</th>
                            <th>Comment / Notes</th>
                            <th>Attribution</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(findingDetail.audit_trail || []).map((entry) => (
                            <tr key={entry.id}>
                              <td style={{ whiteSpace: 'nowrap' }}>{formatTs(entry.performed_at)}</td>
                              <td><strong>{entry.action}</strong></td>
                              <td>
                                {entry.from_status
                                  ? `${entry.from_status} → ${entry.to_status}`
                                  : entry.to_status}
                              </td>
                              <td style={{ maxWidth: '240px', fontSize: '0.75rem' }}>
                                {entry.comment || '—'}
                              </td>
                              <td>
                                <span
                                  className={`badge-actor ${
                                    entry.actor_type === 'SYSTEM_AUTOMATION' ? 'system' : 'unverified'
                                  }`}
                                  title="Unverified client attribution; not an authenticated identity"
                                >
                                  {entry.actor_attribution || entry.actor_type || 'System'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Operational Recommendations Workflow Card */}
            {findingDetail && (
              <div className="findings-drawer-section findings-recommendations-section">
                <div className="findings-rec-header">
                  <div className="findings-rec-title-wrap">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                    </svg>
                    <h4>Operational Recommendations &amp; Actions</h4>
                  </div>
                  <div className="findings-rec-actions">
                    <button
                      type="button"
                      className="btn-findings btn-findings-sm"
                      onClick={() => handleGenerateRecommendationFromFinding(findingDetail.finding_id)}
                      disabled={generatingRec}
                      title="Deterministically generate evidence-grounded recommendations for this finding"
                    >
                      {generatingRec ? 'Generating…' : '+ Generate Recommendation'}
                    </button>
                    <button
                      type="button"
                      className="btn-findings btn-findings-primary btn-findings-sm"
                      onClick={() => {
                        handleCloseDrawer();
                        navigate(`/recommendations?finding_id=${encodeURIComponent(findingDetail.finding_id)}`);
                      }}
                      title="View all operational recommendations linked to this finding"
                    >
                      View Recommendations &rarr;
                    </button>
                  </div>
                </div>

                <p className="findings-rec-desc">
                  Convert this operational finding into deterministic engineering recommendations with assigned owners, due dates, and immutable audit history.
                </p>

                {recGenerationNotice && (
                  <div className={`recommendations-banner-alert ${recGenerationNotice.type}`} style={{ marginTop: '0.6rem', marginBottom: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1 }}>
                      <span>{recGenerationNotice.message}</span>
                      {recGenerationNotice.type === 'success' && (
                        <button
                          type="button"
                          className="btn-findings-link-compact"
                          style={{ alignSelf: 'flex-start', color: 'inherit', fontWeight: 600 }}
                          onClick={() => {
                            handleCloseDrawer();
                            navigate(`/recommendations?finding_id=${encodeURIComponent(findingDetail.finding_id)}`);
                          }}
                        >
                          Open in Recommendations &amp; Actions &rarr;
                        </button>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn-drawer-close"
                      onClick={() => setRecGenerationNotice(null)}
                      style={{ fontSize: '1rem' }}
                    >
                      ×
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Drawer Action Bar — Strictly follows State Machine rules */}
            {findingDetail && (
              <footer className="findings-drawer-actions">
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Current Status: <strong>{findingDetail.status}</strong>
                </span>

                <div className="findings-action-buttons">
                  {/* NEW state transitions */}
                  {findingDetail.status === 'NEW' && (
                    <>
                      <button
                        type="button"
                        className="btn-findings btn-findings-primary"
                        onClick={() => openActionModal('ACKNOWLEDGE', findingDetail)}
                      >
                        ✓ Acknowledge
                      </button>
                      <button
                        type="button"
                        className="btn-findings"
                        onClick={() => openActionModal('INVESTIGATE', findingDetail)}
                      >
                        🔍 Start Investigation
                      </button>
                    </>
                  )}

                  {/* ACKNOWLEDGED state transitions */}
                  {findingDetail.status === 'ACKNOWLEDGED' && (
                    <>
                      <button
                        type="button"
                        className="btn-findings btn-findings-primary"
                        onClick={() => openActionModal('INVESTIGATE', findingDetail)}
                      >
                        🔍 Start Investigation
                      </button>
                      <button
                        type="button"
                        className="btn-findings btn-findings-success"
                        onClick={() => openActionModal('RESOLVE', findingDetail)}
                      >
                        ✓ Resolve Finding
                      </button>
                    </>
                  )}

                  {/* INVESTIGATING state transitions */}
                  {findingDetail.status === 'INVESTIGATING' && (
                    <>
                      <button
                        type="button"
                        className="btn-findings"
                        onClick={() => openActionModal('ADD_NOTE', findingDetail)}
                      >
                        📝 Add Notes
                      </button>
                      <button
                        type="button"
                        className="btn-findings btn-findings-success"
                        onClick={() => openActionModal('RESOLVE', findingDetail)}
                      >
                        ✓ Resolve Finding
                      </button>
                    </>
                  )}

                  {/* RESOLVED state transitions */}
                  {findingDetail.status === 'RESOLVED' && (
                    <button
                      type="button"
                      className="btn-findings btn-findings-danger"
                      onClick={() => openActionModal('REOPEN', findingDetail)}
                    >
                      ↺ Reopen Finding
                    </button>
                  )}

                  {/* REOPENED state transitions */}
                  {findingDetail.status === 'REOPENED' && (
                    <>
                      <button
                        type="button"
                        className="btn-findings btn-findings-primary"
                        onClick={() => openActionModal('ACKNOWLEDGE', findingDetail)}
                      >
                        ✓ Acknowledge
                      </button>
                      <button
                        type="button"
                        className="btn-findings"
                        onClick={() => openActionModal('INVESTIGATE', findingDetail)}
                      >
                        🔍 Start Investigation
                      </button>
                      <button
                        type="button"
                        className="btn-findings btn-findings-success"
                        onClick={() => openActionModal('RESOLVE', findingDetail)}
                      >
                        ✓ Resolve Finding
                      </button>
                    </>
                  )}
                </div>
              </footer>
            )}
          </aside>
        </div>
      )}

      {/* Confirmation & Input Modal for Lifecycle Actions */}
      {actionModal.open && (
        <div className="findings-modal-overlay" onClick={closeActionModal}>
          <div className="findings-modal" onClick={(e) => e.stopPropagation()}>
            <header className="findings-modal-header">
              <h3>
                {actionModal.action === 'ACKNOWLEDGE' && 'Acknowledge Operational Finding'}
                {actionModal.action === 'INVESTIGATE' && 'Initiate Finding Investigation'}
                {actionModal.action === 'ADD_NOTE' && 'Add Investigation Diagnostic Note'}
                {actionModal.action === 'RESOLVE' && 'Confirm Finding Resolution'}
                {actionModal.action === 'REOPEN' && 'Confirm Finding Reopening'}
              </h3>
              <button
                type="button"
                className="btn-drawer-close"
                onClick={closeActionModal}
                disabled={actionModal.loading}
              >
                ✕
              </button>
            </header>

            <div className="findings-modal-body">
              {actionModal.error && (
                <div className="findings-banner-alert error">
                  {actionModal.error}
                </div>
              )}

              <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {actionModal.action === 'ACKNOWLEDGE' &&
                  `Transition finding ${actionModal.finding?.finding_id} from ${actionModal.finding?.status} to ACKNOWLEDGED.`}
                {actionModal.action === 'INVESTIGATE' &&
                  `Transition finding ${actionModal.finding?.finding_id} to INVESTIGATING status to track root-cause diagnostics.`}
                {actionModal.action === 'ADD_NOTE' &&
                  `Append a diagnostic progress note to finding ${actionModal.finding?.finding_id}. Status will remain ${actionModal.finding?.status}.`}
                {actionModal.action === 'RESOLVE' &&
                  `Confirm resolution of finding ${actionModal.finding?.finding_id}. Mandatory resolution notes are required to document the corrective action.`}
                {actionModal.action === 'REOPEN' &&
                  `Reopen finding ${actionModal.finding?.finding_id}. A documented engineering justification reason is required.`}
              </p>

              <div>
                <label
                  htmlFor="action-comments"
                  style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.35rem' }}
                >
                  {actionModal.action === 'RESOLVE' && 'Corrective Action Resolution Notes *'}
                  {actionModal.action === 'REOPEN' && 'Reopening Justification Reason *'}
                  {actionModal.action === 'ADD_NOTE' && 'Diagnostic Progress Note *'}
                  {actionModal.action === 'ACKNOWLEDGE' && 'Optional Acknowledgment Comment'}
                  {actionModal.action === 'INVESTIGATE' && 'Initial Investigation Hypothesis / Notes'}
                </label>
                <textarea
                  id="action-comments"
                  rows={4}
                  placeholder={
                    actionModal.action === 'RESOLVE'
                      ? 'Describe root cause identified and physical/operational remedy implemented...'
                      : actionModal.action === 'REOPEN'
                      ? 'Document why this previously resolved finding is being reopened...'
                      : 'Enter engineering diagnostic remarks...'
                  }
                  value={actionModal.commentOrNote}
                  onChange={(e) =>
                    setActionModal((prev) => ({ ...prev, commentOrNote: e.target.value, error: null }))
                  }
                  disabled={actionModal.loading}
                />
              </div>

              <div>
                <label
                  htmlFor="action-attribution"
                  style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.35rem' }}
                >
                  Caller Attribution Label (Optional)
                </label>
                <input
                  id="action-attribution"
                  type="text"
                  placeholder="e.g. Operator-ShiftA, Eng-Line1"
                  value={actionModal.callerAttribution}
                  onChange={(e) =>
                    setActionModal((prev) => ({ ...prev, callerAttribution: e.target.value }))
                  }
                  disabled={actionModal.loading}
                />
                <span className="findings-modal-disclaimer">
                  Unverified attribution label recorded in audit log. Not an authenticated identity.
                </span>
              </div>
            </div>

            <footer className="findings-modal-footer">
              <button
                type="button"
                className="btn-findings"
                onClick={closeActionModal}
                disabled={actionModal.loading}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`btn-findings ${
                  actionModal.action === 'RESOLVE'
                    ? 'btn-findings-success'
                    : actionModal.action === 'REOPEN'
                    ? 'btn-findings-danger'
                    : 'btn-findings-primary'
                }`}
                onClick={handleExecuteAction}
                disabled={actionModal.loading}
              >
                {actionModal.loading ? 'Submitting...' : 'Confirm Action'}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
