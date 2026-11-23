import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { findingsApi } from '../services/findingsApi';
import { recommendationsApi } from '../services/recommendationsApi';
import { anomalyApi } from '../services/anomalyApi';
import { formatDateTime, formatNumber, formatFindingTitle } from '../utils/formatters';

// Provenance components
import {
  EvidenceProvenanceCard,
  LineageStatusBadge,
  ProvenanceDrillDownView,
} from './findings/ProvenanceExplorer';

// Shared Recommendation & Action Modals / Components
import ActionModal from './recommendations/ActionModal';
import StatusModal from './recommendations/StatusModal';
import GenerateModal from './recommendations/GenerateModal';
import RecommendationDrawer from './recommendations/RecommendationDrawer';
import ActionsTrackerTable from './recommendations/ActionsTrackerTable';
import RecommendationsDirectoryTable from './recommendations/RecommendationsDirectoryTable';
import InterventionWorkflowModal from './recommendations/InterventionWorkflowModal';
import SavingsLedgerSection from './recommendations/SavingsLedgerSection';

// Anomaly Alert List Component
import AlertList from './anomalies/AlertList';

import './investigation-actions/investigation-actions.css';
import './findings/findings-centre.css';
import './recommendations/recommendations.css';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'];
const STATUSES = ['ACTIVE', 'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'REOPENED'];

const ANOMALY_DETECTOR_TYPES = [
  { value: 'ALL', label: 'All Surveillance Algorithms' },
  { value: 'statistical_zscore', label: 'Statistical Z-Score (Spikes & Drops)' },
  { value: 'rolling_baseline', label: 'Rolling Baseline (Spikes & Drops)' },
  { value: 'low_power_factor', label: 'Low Power Factor Surveillance' },
  { value: 'zero_production_standby', label: 'Zero-Production Standby Waste' },
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

function isActionOverdue(action) {
  if (!action?.due_date) return false;
  if (action.status === 'COMPLETED' || action.status === 'CANCELLED') return false;
  try {
    const due = new Date(action.due_date);
    return due < new Date();
  } catch {
    return false;
  }
}

function formatCitationsInText(text, citations, onCitationClick) {
  if (!text) return '';
  const regex = /\[([a-zA-Z_]+):([^\]]+)\]/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    const [fullMatch, type, id] = match;
    const matchIndex = match.index;

    if (matchIndex > lastIndex) {
      parts.push(text.substring(lastIndex, matchIndex));
    }

    const citationObj = (citations || []).find((c) => c.id === id || c.id === `${type}:${id}`);

    parts.push(
      <button
        key={`${type}-${id}-${matchIndex}`}
        type="button"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.2rem',
          padding: '0.15rem 0.45rem',
          margin: '0 0.2rem',
          borderRadius: '4px',
          background: 'rgba(79, 70, 229, 0.1)',
          color: '#4338ca',
          fontSize: '0.78rem',
          fontWeight: 600,
          border: '1px solid rgba(79, 70, 229, 0.25)',
          cursor: 'pointer',
          verticalAlign: 'baseline',
        }}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onCitationClick?.(type, id, citationObj);
        }}
        title={`Click to view record: ${citationObj?.label || `${type}:${id}`}`}
      >
        <span style={{ fontSize: '0.7rem' }}>📎</span>
        {id}
      </button>
    );

    lastIndex = matchIndex + fullMatch.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts;
}

export default function InvestigationActionsCentre() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL query parameters for deep linking
  const urlTab = searchParams.get('tab');
  const urlFindingId = searchParams.get('finding_id') || searchParams.get('id');
  const urlRecId = searchParams.get('recommendation_id');

  // Top Navigation Tabs: 'workspace' | 'recommendations' | 'actions' | 'ledger' | 'surveillance'
  const [activeTab, setActiveTab] = useState(() => {
    if (urlTab === 'recommendations') return 'recommendations';
    if (urlTab === 'actions') return 'actions';
    if (urlTab === 'ledger' || urlTab === 'savings_ledger') return 'ledger';
    if (urlTab === 'surveillance' || urlTab === 'anomalies') return 'surveillance';
    return 'workspace';
  });

  // Global Authoritative KPIs
  const [kpis, setKpis] = useState({
    activeFindings: 0,
    criticalHigh: 0,
    awaitingInvestigation: 0,
    openRecommendations: 0,
    openActions: 0,
    overdueActions: 0,
    loading: true,
  });

  // Recommendations Directory refresh trigger & matching records counter
  const [recsRefreshTrigger, setRecsRefreshTrigger] = useState(0);
  const [recsTotalCount, setRecsTotalCount] = useState(0);

  // Global Banner Notification
  const [banner, setBanner] = useState(null);

  // Findings Queue Filter & Pagination State
  const [plantFilter, setPlantFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('ACTIVE');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);

  // Findings Queue Data State
  const [findingsData, setFindingsData] = useState({ items: [], total: 0 });
  const [loadingFindings, setLoadingFindings] = useState(true);
  const [findingsError, setFindingsError] = useState(null);
  const [syncingAnomalies, setSyncingAnomalies] = useState(false);

  // Selected Finding Investigation Workspace State
  const [selectedFindingId, setSelectedFindingId] = useState(urlFindingId || null);
  const [findingDetail, setFindingDetail] = useState(null);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [detailSubTab, setDetailSubTab] = useState('evidence'); // 'evidence' | 'occurrences' | 'audit' | 'recs' | 'ai_investigation'
  const [expandedOccurrences, setExpandedOccurrences] = useState({});

  // Linked Recommendations & Actions for the Selected Finding
  const [findingRecs, setFindingRecs] = useState([]);
  const [recActionsMap, setRecActionsMap] = useState({});
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [generatingRec, setGeneratingRec] = useState(false);

  // AI Investigation State
  const [aiInvestigation, setAiInvestigation] = useState(null);
  const [investigatingAi, setInvestigatingAi] = useState(false);
  const [aiInvestigationError, setAiInvestigationError] = useState(null);
  const [activeCitationToast, setActiveCitationToast] = useState(null);
  const [workflowAction, setWorkflowAction] = useState(null);

  // Modals & Drawers State
  // 1. Finding Lifecycle Action Modal (Acknowledge, Start Investigation, Add Notes, Resolve, Reopen)
  const [lifecycleModal, setLifecycleModal] = useState({
    open: false,
    action: null, // 'ACKNOWLEDGE' | 'INVESTIGATE' | 'ADD_NOTE' | 'RESOLVE' | 'REOPEN'
    finding: null,
    commentOrNote: '',
    callerAttribution: '',
    loading: false,
    error: null,
  });

  // 2. Recommendation Modals
  const [drawerRecId, setDrawerRecId] = useState(urlRecId || null);
  const [statusModal, setStatusModal] = useState({
    open: false,
    rec: null,
    targetStatus: 'DISMISSED',
    loading: false,
    error: null,
  });
  const [generateModal, setGenerateModal] = useState({
    open: false,
    prefillFindingId: '',
    loading: false,
    error: null,
  });

  // 3. Action Modal (Create or Edit)
  const [actionModal, setActionModal] = useState({
    open: false,
    mode: 'create', // 'create' | 'edit'
    recId: '',
    action: null,
    parentRec: null,
    loading: false,
    error: null,
  });

  // 4. Live Anomaly Surveillance State
  const [anomalySuiteData, setAnomalySuiteData] = useState(null);
  const [loadingSurveillance, setLoadingSurveillance] = useState(false);
  const [surveillanceError, setSurveillanceError] = useState(null);
  const [surveillanceSeverityFilter, setSurveillanceSeverityFilter] = useState('ALL');
  const [surveillanceCategoryFilter, setSurveillanceCategoryFilter] = useState('ALL');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Sync URL query params with active tab and selected finding
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    let changed = false;

    if (activeTab !== 'workspace') {
      if (params.get('tab') !== activeTab) {
        params.set('tab', activeTab);
        changed = true;
      }
    } else {
      if (params.has('tab')) {
        params.delete('tab');
        changed = true;
      }
    }

    if (selectedFindingId) {
      if (params.get('finding_id') !== selectedFindingId) {
        params.set('finding_id', selectedFindingId);
        changed = true;
      }
    } else {
      if (params.has('finding_id') || params.has('id')) {
        params.delete('finding_id');
        params.delete('id');
        changed = true;
      }
    }

    if (changed) {
      setSearchParams(params, { replace: true });
    }
  }, [activeTab, selectedFindingId, searchParams, setSearchParams]);

  // Load Authoritative Top-Level KPIs from existing backend APIs without estimation
  const loadAuthoritativeKpis = useCallback(async (currentPlantId) => {
    try {
      const baseParam = currentPlantId ? { plant_id: currentPlantId } : {};

      const [
        activeRes,
        critRes,
        highRes,
        newRes,
        ackRes,
        openRecRes,
        inProgRecRes,
        openActRes,
        inProgActRes,
      ] = await Promise.all([
        findingsApi.listFindings({ ...baseParam, status: 'ACTIVE', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'ACTIVE', severity: 'CRITICAL', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'ACTIVE', severity: 'HIGH', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'NEW', limit: 1 }),
        findingsApi.listFindings({ ...baseParam, status: 'ACKNOWLEDGED', limit: 1 }),
        recommendationsApi.listRecommendations({ ...baseParam, status: 'OPEN', limit: 1 }),
        recommendationsApi.listRecommendations({ ...baseParam, status: 'IN_PROGRESS', limit: 1 }),
        recommendationsApi.listActions({ status: 'OPEN', limit: 100 }),
        recommendationsApi.listActions({ status: 'IN_PROGRESS', limit: 100 }),
      ]);

      const activeCount = activeRes.total || 0;
      const criticalHighCount = (critRes.total || 0) + (highRes.total || 0);
      const awaitingInvestigationCount = (newRes.total || 0) + (ackRes.total || 0);
      const openRecsCount = (openRecRes.total || 0) + (inProgRecRes.total || 0);

      const openActionsList = (openActRes.items || []).concat(inProgActRes.items || []);
      const totalOpenActions = (openActRes.total || 0) + (inProgActRes.total || 0);
      const overdueCount = openActionsList.filter(isActionOverdue).length;

      setKpis({
        activeFindings: activeCount,
        criticalHigh: criticalHighCount,
        awaitingInvestigation: awaitingInvestigationCount,
        openRecommendations: openRecsCount,
        openActions: totalOpenActions,
        overdueActions: overdueCount,
        loading: false,
      });
    } catch (err) {
      console.warn('Unable to load authoritative operational KPIs:', err);
      setKpis((prev) => ({ ...prev, loading: false }));
    }
  }, []);

  // Load Paginated Findings Queue from server
  const loadFindings = useCallback(async () => {
    setLoadingFindings(true);
    setFindingsError(null);
    try {
      const params = { limit, offset };
      if (plantFilter) params.plant_id = plantFilter;
      if (statusFilter && statusFilter !== 'ALL') params.status = statusFilter;
      if (severityFilter && severityFilter !== 'ALL') params.severity = severityFilter;
      if (typeFilter && typeFilter !== 'ALL') params.anomaly_type = typeFilter;
      if (debouncedSearch && debouncedSearch.trim()) params.search = debouncedSearch.trim();

      const result = await findingsApi.listFindings(params);
      setFindingsData(result || { items: [], total: 0 });
    } catch (err) {
      console.error('Failed to load operational findings:', err);
      setFindingsError(err.message || 'Unable to load findings list.');
    } finally {
      setLoadingFindings(false);
    }
  }, [plantFilter, statusFilter, severityFilter, typeFilter, debouncedSearch, limit, offset]);

  // Load Selected Finding Detail and its Linked Recommendations & Actions
  const loadFindingDetailAndRecs = useCallback(async (findingId) => {
    if (!findingId) {
      setFindingDetail(null);
      setFindingRecs([]);
      setRecActionsMap({});
      return;
    }
    setLoadingDetail(true);
    setLoadingRecs(true);
    setDetailError(null);
    try {
      const [detail, recsRes] = await Promise.all([
        findingsApi.getFindingDetail(findingId),
        recommendationsApi.listRecommendations({ finding_id: findingId, limit: 50 }),
      ]);
      setFindingDetail(detail);

      const recs = recsRes.items || [];
      setFindingRecs(recs);

      // Load linked actions for each recommendation
      if (recs.length > 0) {
        const actionPromises = recs.map((r) =>
          recommendationsApi.listActions({ recommendation_id: r.recommendation_id, limit: 50 })
        );
        const actionResults = await Promise.all(actionPromises);
        const actionsByRec = {};
        recs.forEach((r, idx) => {
          actionsByRec[r.recommendation_id] = actionResults[idx].items || [];
        });
        setRecActionsMap(actionsByRec);
      } else {
        setRecActionsMap({});
      }
    } catch (err) {
      console.error(`Failed to load details for finding ${findingId}:`, err);
      setDetailError(err.message || 'Unable to load finding details.');
    } finally {
      setLoadingDetail(false);
      setLoadingRecs(false);
    }
  }, []);

  // Initial and reactive data loads
  useEffect(() => {
    loadAuthoritativeKpis(plantFilter);
  }, [loadAuthoritativeKpis, plantFilter]);

  useEffect(() => {
    loadFindings();
  }, [loadFindings]);

  useEffect(() => {
    setAiInvestigation(null);
    setAiInvestigationError(null);
    setActiveCitationToast(null);
    setSelectedOccurrenceId(null);
    if (selectedFindingId) {
      loadFindingDetailAndRecs(selectedFindingId);
    } else {
      setFindingDetail(null);
      setFindingRecs([]);
      setRecActionsMap({});
    }
  }, [selectedFindingId, loadFindingDetailAndRecs]);

  // Load Live Anomaly Surveillance Data when that tab is selected
  const loadSurveillanceData = useCallback(async () => {
    setLoadingSurveillance(true);
    setSurveillanceError(null);
    try {
      const params = {};
      if (plantFilter) params.plant_id = plantFilter;
      const res = await anomalyApi.getAllAnomalies(params);
      setAnomalySuiteData(res);
    } catch (err) {
      console.error('Failed to load anomaly surveillance signals:', err);
      setSurveillanceError(err.message || 'Failed to execute anomaly surveillance suite.');
    } finally {
      setLoadingSurveillance(false);
    }
  }, [plantFilter]);

  useEffect(() => {
    if (activeTab === 'surveillance' && !anomalySuiteData) {
      loadSurveillanceData();
    }
  }, [activeTab, anomalySuiteData, loadSurveillanceData]);

  // Synchronize Anomaly Signals into Persistent Findings
  const handleSyncAnomalies = async () => {
    if (syncingAnomalies) return;
    setSyncingAnomalies(true);
    setBanner({ type: 'info', message: 'Surveillance suite running: evaluating signals and synchronizing findings...' });
    try {
      const syncResult = await findingsApi.syncFindings({
        plant_id: plantFilter || undefined,
        caller_attribution: 'InvestigationActionsCentre-UI',
      });
      setBanner({
        type: 'success',
        message: `Surveillance Synchronization Complete! Evaluated: ${syncResult.total_anomalies_evaluated}, New Findings: ${syncResult.new_findings_created}, Updated: ${syncResult.existing_findings_updated}, Reopened: ${syncResult.findings_reopened}, Occurrences Logged: ${syncResult.occurrences_recorded}.`,
      });
      await loadFindings();
      await loadAuthoritativeKpis(plantFilter);
      if (selectedFindingId) {
        await loadFindingDetailAndRecs(selectedFindingId);
      }
    } catch (err) {
      console.error('Surveillance sync failure:', err);
      const isConflict = err.status === 409 || (err.message && err.message.includes('already in progress'));
      setBanner({
        type: isConflict ? 'warning' : 'error',
        message: isConflict
          ? 'Synchronization Guard: Another surveillance run is currently executing. Please wait a moment.'
          : `Surveillance sync failed: ${err.message}`,
      });
    } finally {
      setSyncingAnomalies(false);
    }
  };

  // Generate Recommendations from Selected Finding
  const handleGenerateRecommendationsForFinding = async (findingId) => {
    if (!findingId || generatingRec) return;
    setGeneratingRec(true);
    setBanner({ type: 'info', message: `Synthesizing deterministic recommendations for finding ${findingId}...` });
    try {
      const res = await recommendationsApi.generateFromFinding(findingId, {
        caller_attribution: 'InvestigationActionsCentre-UI',
      });
      setBanner({
        type: 'success',
        message: res.message || `Generated ${res.generated_count || 0} actionable recommendation(s).`,
      });
      await loadFindingDetailAndRecs(findingId);
      await loadAuthoritativeKpis(plantFilter);
      setRecsRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setBanner({
        type: 'error',
        message: err.message || 'Failed to generate recommendations from finding.',
      });
    } finally {
      setGeneratingRec(false);
    }
  };

  const handleInvestigateWithAi = async () => {
    if (!selectedFindingId) return;
    setInvestigatingAi(true);
    setAiInvestigationError(null);
    try {
      const occId = selectedOccurrenceId || (findingDetail?.occurrences?.[0]?.occurrence_id) || null;
      const url = `/api/findings/${encodeURIComponent(selectedFindingId)}/investigate-ai${occId ? `?occurrence_id=${encodeURIComponent(occId)}` : ''}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Investigation failed with HTTP ${res.status}`);
      }
      const data = await res.json();
      setAiInvestigation(data);
      setDetailSubTab('ai_investigation');
    } catch (err) {
      console.error('AI investigation failed:', err);
      setAiInvestigationError(err.message || 'AI Investigation service temporarily unavailable.');
    } finally {
      setInvestigatingAi(false);
    }
  };

  const handlePlanEnergySavingTrial = async () => {
    try {
      let targetAction = null;
      if (findingRecs && findingRecs.length > 0) {
        for (const rec of findingRecs) {
          const acts = recActionsMap[rec.recommendation_id] || [];
          if (acts.length > 0) {
            targetAction = acts[0];
            break;
          }
        }
      }

      if (!targetAction) {
        const res = await recommendationsApi.generateFromFinding(selectedFindingId, {
          caller_attribution: 'Finding-AI-Investigation-UI',
        });
        const recList = res.recommendations || [];
        if (recList.length > 0) {
          const recId = recList[0].recommendation_id;
          const acts = await recommendationsApi.listActions({ recommendation_id: recId, limit: 10 });
          targetAction = (acts.items || acts)[0];
        }
      }

      if (targetAction) {
        setWorkflowAction(targetAction);
      } else {
        alert('Could not initialize corrective action for this trial. Please check recommendation settings.');
      }
    } catch (err) {
      console.error('Failed to initiate trial plan:', err);
      alert('Failed to initialize trial plan: ' + err.message);
    }
  };

  // Execute Finding Lifecycle Actions
  const openLifecycleModal = (action, finding) => {
    setLifecycleModal({
      open: true,
      action,
      finding,
      commentOrNote: '',
      callerAttribution: '',
      loading: false,
      error: null,
    });
  };

  const closeLifecycleModal = () => {
    setLifecycleModal((prev) => ({ ...prev, open: false, error: null }));
  };

  const handleExecuteLifecycleAction = async () => {
    const { action, finding, commentOrNote, callerAttribution } = lifecycleModal;
    if (!finding) return;

    if ((action === 'RESOLVE' || action === 'REOPEN' || action === 'ADD_NOTE') && !commentOrNote.trim()) {
      setLifecycleModal((prev) => ({
        ...prev,
        error: action === 'RESOLVE'
          ? 'Resolution notes are required to resolve this finding.'
          : action === 'REOPEN'
            ? 'An engineering justification reason is required to reopen this finding.'
            : 'Diagnostic notes cannot be blank.',
      }));
      return;
    }

    setLifecycleModal((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const caller = callerAttribution.trim() || 'InvestigationCentre-UI';
      const fId = finding.finding_id;

      if (action === 'ACKNOWLEDGE') {
        await findingsApi.acknowledgeFinding(fId, {
          comment: commentOrNote.trim() || undefined,
          caller_attribution: caller,
        });
      } else if (action === 'INVESTIGATE') {
        await findingsApi.startInvestigation(fId, {
          investigation_notes: commentOrNote.trim() || undefined,
          caller_attribution: caller,
        });
      } else if (action === 'ADD_NOTE') {
        await findingsApi.addInvestigationNotes(fId, {
          notes: commentOrNote.trim(),
          caller_attribution: caller,
        });
      } else if (action === 'RESOLVE') {
        await findingsApi.resolveFinding(fId, {
          resolution_notes: commentOrNote.trim(),
          caller_attribution: caller,
        });
      } else if (action === 'REOPEN') {
        await findingsApi.reopenFinding(fId, {
          reason: commentOrNote.trim(),
          caller_attribution: caller,
        });
      }

      setBanner({
        type: 'success',
        message: `Finding ${fId} successfully updated via ${action}.`,
      });

      closeLifecycleModal();
      await loadFindings();
      await loadAuthoritativeKpis(plantFilter);
      if (selectedFindingId === fId) {
        await loadFindingDetailAndRecs(fId);
      }
    } catch (err) {
      console.error(`Lifecycle action ${action} failed:`, err);
      setLifecycleModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message || `Failed to execute ${action}.`,
      }));
    }
  };

  // Corrective Action Modal Submit
  const handleActionModalSubmit = async (formData) => {
    setActionModal((prev) => ({ ...prev, loading: true, error: null }));
    try {
      if (actionModal.mode === 'create') {
        await recommendationsApi.createAction(actionModal.recId, {
          title: formData.title,
          description: formData.description,
          owner: formData.owner || undefined,
          due_date: formData.due_date || undefined,
          caller_attribution: formData.caller_attribution || 'InvestigationActionsCentre-UI',
        });
        setBanner({ type: 'success', message: 'Corrective action successfully created and assigned.' });
      } else {
        await recommendationsApi.updateAction(actionModal.action.action_id, {
          title: formData.title,
          description: formData.description,
          status: formData.status,
          owner: formData.owner,
          clear_owner: formData.clear_owner,
          due_date: formData.due_date,
          clear_due_date: formData.clear_due_date,
          resolution_notes: formData.resolution_notes,
          caller_attribution: formData.caller_attribution || 'InvestigationActionsCentre-UI',
        });
        setBanner({ type: 'success', message: `Corrective action ${actionModal.action.action_id} updated.` });
      }

      setActionModal((prev) => ({ ...prev, open: false, loading: false }));
      if (selectedFindingId) {
        await loadFindingDetailAndRecs(selectedFindingId);
      }
      await loadAuthoritativeKpis(plantFilter);
      setRecsRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setActionModal((prev) => ({ ...prev, loading: false, error: err.message }));
    }
  };

  // Quick Action Status Transition (Start, Complete, Cancel)
  const handleQuickActionStatus = async (action, newStatus) => {
    try {
      await recommendationsApi.updateAction(action.action_id, {
        status: newStatus,
        caller_attribution: 'InvestigationActionsCentre-UI',
      });
      setBanner({
        type: 'success',
        message: `Action ${action.action_id} status updated to ${newStatus}. (Note: Independent verification required before resolving finding).`,
      });
      if (selectedFindingId) {
        await loadFindingDetailAndRecs(selectedFindingId);
      }
      await loadAuthoritativeKpis(plantFilter);
      setRecsRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setBanner({ type: 'error', message: err.message || 'Failed to update action status.' });
    }
  };

  // Recommendation Status Transition Modal Submit
  const handleStatusModalSubmit = async (formData) => {
    setStatusModal((prev) => ({ ...prev, loading: true, error: null }));
    try {
      await recommendationsApi.updateRecommendationStatus(statusModal.rec.recommendation_id, {
        status: formData.status,
        reason: formData.reason,
        caller_attribution: formData.caller_attribution || 'InvestigationActionsCentre-UI',
      });
      setBanner({
        type: 'success',
        message: `Recommendation ${statusModal.rec.recommendation_id} transitioned to ${formData.status}.`,
      });
      setStatusModal((prev) => ({ ...prev, open: false, loading: false }));
      if (selectedFindingId) {
        await loadFindingDetailAndRecs(selectedFindingId);
      }
      await loadAuthoritativeKpis(plantFilter);
      setRecsRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setStatusModal((prev) => ({ ...prev, loading: false, error: err.message }));
    }
  };

  // Generate Modal Submit (from Generate button)
  const handleGenerateModalSubmit = async (formData) => {
    setGenerateModal((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await recommendationsApi.generateFromFinding(formData.finding_id, {
        caller_attribution: formData.caller_attribution || 'InvestigationActionsCentre-UI',
      });
      setBanner({
        type: 'success',
        message: res.message || `Generated ${res.generated_count || 0} recommendation(s).`,
      });
      setGenerateModal((prev) => ({ ...prev, open: false, loading: false }));
      if (selectedFindingId) {
        await loadFindingDetailAndRecs(selectedFindingId);
      }
      await loadAuthoritativeKpis(plantFilter);
      setRecsRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setGenerateModal((prev) => ({ ...prev, loading: false, error: err.message }));
    }
  };

  // Flatten Surveillance Alerts
  const surveillanceAlerts = useMemo(() => {
    if (!anomalySuiteData) return [];
    const sources = [
      ['Statistical Z-Score', anomalySuiteData?.statistical_zscore?.anomalies],
      ['Rolling Baseline', anomalySuiteData?.rolling_baseline?.anomalies],
      ['Low Power Factor', anomalySuiteData?.low_power_factor?.anomalies],
      ['Zero-Production Standby', anomalySuiteData?.zero_production_standby?.anomalies],
    ];

    return sources.flatMap(([source, anomalies]) =>
      (Array.isArray(anomalies) ? anomalies : []).map((anomaly, index) => ({
        ...anomaly,
        source,
        alertKey: `${source}-${anomaly.timestamp}-${anomaly.plant_id}-${anomaly.meter_id || anomaly.line_id || ''}-${index}`,
      }))
    );
  }, [anomalySuiteData]);

  const filteredSurveillanceAlerts = useMemo(() => {
    return surveillanceAlerts.filter((a) => {
      if (surveillanceSeverityFilter !== 'ALL' && a.severity !== surveillanceSeverityFilter) return false;
      if (surveillanceCategoryFilter !== 'ALL' && a.anomaly_type !== surveillanceCategoryFilter) return false;
      return true;
    });
  }, [surveillanceAlerts, surveillanceSeverityFilter, surveillanceCategoryFilter]);

  return (
    <div className="investigation-actions-page">
      {/* Page Header */}
      <header className="iac-header">
        <div className="iac-header-actions">
          <button
            type="button"
            className="btn-iac"
            onClick={() => {
              loadAuthoritativeKpis(plantFilter);
              loadFindings();
              setRecsRefreshTrigger((prev) => prev + 1);
              if (selectedFindingId) loadFindingDetailAndRecs(selectedFindingId);
            }}
            title="Refresh active queue and operational metrics"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
            </svg>
            Refresh
          </button>

          <button
            type="button"
            className="btn-iac btn-iac-primary"
            onClick={handleSyncAnomalies}
            disabled={syncingAnomalies}
            title="Execute surveillance algorithms and synchronize persistent findings"
          >
            {syncingAnomalies ? (
              <>
                <span className="badge-dot" style={{ background: '#fff' }}></span>
                Surveillance Running...
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
                Sync Anomaly Signals
              </>
            )}
          </button>

          <button
            type="button"
            className="btn-iac"
            onClick={() => setGenerateModal({ open: true, prefillFindingId: selectedFindingId || '', loading: false, error: null })}
            title="Generate actionable recommendations from an energy finding"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
            Generate Recommendations
          </button>
        </div>
      </header>

      {/* Global Alert Notification Banner */}
      {banner && (
        <div className={`iac-banner-alert ${banner.type}`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {banner.type === 'success' && <span>✓</span>}
            {banner.type === 'error' && <span>⚠</span>}
            {banner.type === 'info' && <span>ℹ</span>}
            {banner.type === 'warning' && <span>⚡</span>}
            <span>{banner.message}</span>
          </div>
          <button
            type="button"
            className="btn-drawer-close"
            style={{ fontSize: '0.9rem', color: 'inherit' }}
            onClick={() => setBanner(null)}
          >
            ✕
          </button>
        </div>
      )}

      {/* SECTION A: Investigation Overview (Top Authoritative Operational KPIs) */}
      <section className="iac-kpi-grid">
        {/* Active Findings */}
        <div
          className={`iac-kpi-card ${statusFilter === 'ACTIVE' && activeTab === 'workspace' ? 'active-filter' : ''}`}
          onClick={() => {
            setActiveTab('workspace');
            setStatusFilter('ACTIVE');
            setOffset(0);
          }}
          title="Click to view Active findings in queue"
        >
          <div className="iac-kpi-header">
            <span className="iac-kpi-label">Active Findings</span>
            <div className="iac-kpi-icon" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--brand-purple, #6366f1)' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
          </div>
          <div className="iac-kpi-value-row">
            <span className="iac-kpi-value">{kpis.loading ? '...' : formatNumber(kpis.activeFindings)}</span>
          </div>
          <span className="iac-kpi-sub">Unresolved operational signals</span>
        </div>

        {/* Critical & High Priority */}
        <div
          className={`iac-kpi-card ${severityFilter === 'CRITICAL' && activeTab === 'workspace' ? 'active-filter' : ''}`}
          onClick={() => {
            setActiveTab('workspace');
            setStatusFilter('ACTIVE');
            setSeverityFilter('CRITICAL');
            setOffset(0);
          }}
          title="Click to filter Critical & High findings"
        >
          <div className="iac-kpi-header">
            <span className="iac-kpi-label">Critical & High Priority</span>
            <div className="iac-kpi-icon" style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              </svg>
            </div>
          </div>
          <div className="iac-kpi-value-row">
            <span className="iac-kpi-value" style={{ color: '#ef4444' }}>
              {kpis.loading ? '...' : formatNumber(kpis.criticalHigh)}
            </span>
            <span className="iac-kpi-badge danger">High Risk</span>
          </div>
          <span className="iac-kpi-sub">Significant baseline deviations & PF breaches</span>
        </div>

        {/* Awaiting Investigation */}
        <div
          className={`iac-kpi-card ${statusFilter === 'NEW' && activeTab === 'workspace' ? 'active-filter' : ''}`}
          onClick={() => {
            setActiveTab('workspace');
            setStatusFilter('NEW');
            setOffset(0);
          }}
          title="Click to view New & Acknowledged findings"
        >
          <div className="iac-kpi-header">
            <span className="iac-kpi-label">Awaiting Investigation</span>
            <div className="iac-kpi-icon" style={{ background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
          </div>
          <div className="iac-kpi-value-row">
            <span className="iac-kpi-value" style={{ color: '#f59e0b' }}>
              {kpis.loading ? '...' : formatNumber(kpis.awaitingInvestigation)}
            </span>
            <span className="iac-kpi-badge warning">Pending</span>
          </div>
          <span className="iac-kpi-sub">Pending root-cause diagnostics</span>
        </div>

        {/* Open Recommendations */}
        <div
          className={`iac-kpi-card ${activeTab === 'recommendations' ? 'active-filter' : ''}`}
          onClick={() => setActiveTab('recommendations')}
          title="Click to view Open Recommendations Directory"
        >
          <div className="iac-kpi-header">
            <span className="iac-kpi-label">Open Recommendations</span>
            <div className="iac-kpi-icon" style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
            </div>
          </div>
          <div className="iac-kpi-value-row">
            <span className="iac-kpi-value" style={{ color: '#3b82f6' }}>
              {kpis.loading ? '...' : formatNumber(kpis.openRecommendations)}
            </span>
          </div>
          <span className="iac-kpi-sub">Actionable energy optimization measures</span>
        </div>

        {/* Open & Overdue Corrective Actions */}
        <div
          className={`iac-kpi-card ${activeTab === 'actions' ? 'active-filter' : ''}`}
          onClick={() => setActiveTab('actions')}
          title="Click to view Corrective Actions Tracker"
        >
          <div className="iac-kpi-header">
            <span className="iac-kpi-label">Corrective Actions</span>
            <div className="iac-kpi-icon" style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
          </div>
          <div className="iac-kpi-value-row">
            <span className="iac-kpi-value">{kpis.loading ? '...' : formatNumber(kpis.openActions)}</span>
            {kpis.overdueActions > 0 && (
              <span className="iac-kpi-badge danger">
                {kpis.overdueActions} Overdue
              </span>
            )}
          </div>
          <span className="iac-kpi-sub">Assigned plant engineering tasks</span>
        </div>
      </section>

      {/* Top Navigation Tabs */}
      <nav className="iac-tabs-bar">
        <button
          type="button"
          className={`iac-tab-btn ${activeTab === 'workspace' ? 'active' : ''}`}
          onClick={() => setActiveTab('workspace')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect width="7" height="9" x="3" y="3" rx="1" />
            <rect width="7" height="5" x="14" y="3" rx="1" />
            <rect width="7" height="9" x="14" y="12" rx="1" />
            <rect width="7" height="5" x="3" y="16" rx="1" />
          </svg>
          Findings &amp; Investigation Workspace
          <span className="iac-tab-count">{findingsData.total}</span>
        </button>

        <button
          type="button"
          className={`iac-tab-btn ${activeTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          Recommendations Directory
          <span className="iac-tab-count">{kpis.openRecommendations}</span>
        </button>

        <button
          type="button"
          className={`iac-tab-btn ${activeTab === 'actions' ? 'active' : ''}`}
          onClick={() => setActiveTab('actions')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
            <path d="M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1Z" />
            <path d="m9 14 2 2 4-4" />
          </svg>
          Corrective Actions Tracker
          <span className="iac-tab-count">{kpis.openActions}</span>
        </button>

        <button
          type="button"
          className={`iac-tab-btn ${activeTab === 'ledger' ? 'active' : ''}`}
          onClick={() => setActiveTab('ledger')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="1" x2="12" y2="23" />
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          </svg>
          Verified Savings Ledger
        </button>

        <button
          type="button"
          className={`iac-tab-btn ${activeTab === 'surveillance' ? 'active' : ''}`}
          onClick={() => setActiveTab('surveillance')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
          </svg>
          Live Anomaly Surveillance
          {anomalySuiteData && <span className="iac-tab-count">{surveillanceAlerts.length}</span>}
        </button>
      </nav>

      {/* ========================================================================= */}
      {/* TAB 1: FINDINGS & INVESTIGATION WORKSPACE (Master-Detail View)            */}
      {/* ========================================================================= */}
      {activeTab === 'workspace' && (
        <div className={`iac-workspace-layout ${selectedFindingId ? 'has-selected' : ''}`}>
          {/* SECTION B: FINDINGS QUEUE */}
          <div className="iac-panel">
            {/* Filter Toolbar */}
            <div className="iac-filter-toolbar">
              <div className="iac-search-box">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <input
                  type="text"
                  placeholder="Search findings by title, meter, line, or ID..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
                {searchTerm && (
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                    onClick={() => setSearchTerm('')}
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Status Filter */}
              <select
                className="iac-filter-select"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="ACTIVE">Status: ACTIVE (Unresolved)</option>
                <option value="ALL">Status: ALL Statuses</option>
                <option value="NEW">Status: NEW</option>
                <option value="ACKNOWLEDGED">Status: ACKNOWLEDGED</option>
                <option value="INVESTIGATING">Status: INVESTIGATING</option>
                <option value="RESOLVED">Status: RESOLVED</option>
                <option value="REOPENED">Status: REOPENED</option>
              </select>

              {/* Severity Filter */}
              <select
                className="iac-filter-select"
                value={severityFilter}
                onChange={(e) => {
                  setSeverityFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="ALL">Severity: ALL</option>
                {SEVERITIES.map((sev) => (
                  <option key={sev} value={sev}>Severity: {sev}</option>
                ))}
              </select>

              {/* Detector Type Filter */}
              <select
                className="iac-filter-select"
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value);
                  setOffset(0);
                }}
              >
                {ANOMALY_DETECTOR_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>

              {/* Plant Filter */}
              <select
                className="iac-filter-select"
                value={plantFilter}
                onChange={(e) => {
                  setPlantFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">Plant: ALL Plants</option>
                <option value="IN-TN-01">Plant: IN-TN-01 (Chennai)</option>
              </select>
            </div>

            {/* Findings Queue Table */}
            <div className="iac-table-wrapper">
              {loadingFindings ? (
                <div className="iac-empty-state">
                  <div className="badge-dot" style={{ width: '14px', height: '14px' }}></div>
                  <span>Loading authoritative findings queue...</span>
                </div>
              ) : findingsError ? (
                <div className="iac-empty-state">
                  <span style={{ color: '#ef4444' }}>Error: {findingsError}</span>
                  <button type="button" className="btn-iac" onClick={loadFindings}>
                    Retry
                  </button>
                </div>
              ) : findingsData.items.length === 0 ? (
                <div className="iac-empty-state">
                  <span className="iac-empty-icon">✓</span>
                  <strong>No findings matching filter criteria</strong>
                  <span style={{ fontSize: '0.8rem' }}>All operational telemetry within selected parameters is verified or resolved.</span>
                </div>
              ) : (
                <table className="iac-table">
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Finding Title &amp; Details</th>
                      <th>Asset Scope</th>
                      <th>Occurrences</th>
                      <th>Status</th>
                      <th>Last Detected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findingsData.items.map((f) => {
                      const isSelected = selectedFindingId === f.finding_id;
                      const sevClass = `badge-sev-${(f.severity || 'medium').toLowerCase()}`;
                      const stClass = `badge-st-${(f.status || 'new').toLowerCase()}`;

                      return (
                        <tr
                          key={f.finding_id}
                          className={isSelected ? 'selected-row' : ''}
                          onClick={() => {
                            if (isSelected) {
                              setSelectedFindingId(null);
                            } else {
                              setSelectedFindingId(f.finding_id);
                            }
                          }}
                        >
                          <td>
                            <span className={`badge-iac ${sevClass}`}>
                              {f.severity}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                {formatFindingTitle(f.title || f.anomaly_type)}
                              </span>
                              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                ID: {f.finding_id}
                              </span>
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                              <span>{f.meter_id || f.line_id || f.plant_id || 'Plant-wide'}</span>
                              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{f.plant_id}</span>
                            </div>
                          </td>
                          <td>
                            <span style={{ fontWeight: 600 }}>{f.occurrence_count || 1}</span>
                          </td>
                          <td>
                            <span className={`badge-iac ${stClass}`}>
                              {f.status}
                            </span>
                          </td>
                          <td>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              {formatDateTime(f.last_detected_at)}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* Pagination Controls */}
            <div className="iac-pagination">
              <span>
                Showing {findingsData.items.length > 0 ? offset + 1 : 0} to{' '}
                {Math.min(offset + limit, findingsData.total)} of {findingsData.total} findings
              </span>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  className="btn-iac"
                  disabled={offset === 0}
                  onClick={() => setOffset((prev) => Math.max(0, prev - limit))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="btn-iac"
                  disabled={offset + limit >= findingsData.total}
                  onClick={() => setOffset((prev) => prev + limit)}
                >
                  Next
                </button>
              </div>
            </div>
          </div>

          {/* SECTION C & D & E: FINDING INVESTIGATION DETAIL WORKSPACE */}
          {selectedFindingId && (
            <div className="iac-detail-workspace">
              {loadingDetail ? (
                <div className="iac-empty-state" style={{ minHeight: '400px' }}>
                  <div className="badge-dot" style={{ width: '14px', height: '14px' }}></div>
                  <span>Loading investigation evidence, provenance, and linked actions...</span>
                </div>
              ) : detailError ? (
                <div className="iac-empty-state" style={{ minHeight: '400px' }}>
                  <span style={{ color: '#ef4444' }}>Error: {detailError}</span>
                  <button type="button" className="btn-iac" onClick={() => loadFindingDetailAndRecs(selectedFindingId)}>
                    Retry
                  </button>
                </div>
              ) : findingDetail ? (
                <>
                  {/* Investigation Header */}
                  <header className="iac-finding-header">
                    <div className="iac-finding-top-row">
                      <div className="iac-finding-headline-group">
                        <div className="iac-finding-badges-wrap">
                          <span className={`badge-iac badge-sev-${(findingDetail.severity || 'medium').toLowerCase()}`}>
                            {findingDetail.severity}
                          </span>
                          <span className={`badge-iac badge-st-${(findingDetail.status || 'new').toLowerCase()}`}>
                            {findingDetail.status}
                          </span>
                        </div>
                        <h2 className="iac-finding-title">
                          {formatFindingTitle(findingDetail.title || findingDetail.anomaly_type)}
                        </h2>
                      </div>

                      <button
                        type="button"
                        className="iac-close-btn"
                        onClick={() => setSelectedFindingId(null)}
                        aria-label="Close finding"
                        title="Close finding"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </div>

                    {/* Compact Natural-Wrapping Metadata Row */}
                    <div className="iac-finding-meta-row">
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">ID:</span>
                        <code className="iac-finding-id-code">{findingDetail.finding_id}</code>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">Plant:</span>
                        <strong>{findingDetail.plant_id}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">Asset:</span>
                        <strong>{findingDetail.meter_id || findingDetail.line_id || 'Plant-wide'}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">First detected:</span>
                        <strong>{formatTs(findingDetail.first_detected_at)}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">Occurrences:</span>
                        <strong>{findingDetail.occurrence_count || 1}</strong>
                      </span>
                    </div>

                    {/* Operational Description (Omitted when empty) */}
                    {Boolean(findingDetail.description && findingDetail.description.trim()) && (
                      <p className="iac-finding-narrative">
                        {findingDetail.description}
                      </p>
                    )}
                  </header>

                  {/* Investigation Lifecycle Actions Toolbar (Consistent 40px buttons, 8px gaps) */}
                  <div className="iac-lifecycle-toolbar">
                    {/* Primary Purple Action: Investigate with AI */}
                    <button
                      type="button"
                      className="btn-iac btn-action-40 btn-action-ai"
                      onClick={handleInvestigateWithAi}
                      disabled={investigatingAi}
                      title="Run autonomous root-cause investigation with citations and trial recommendations"
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                      <span>{investigatingAi ? 'Investigating...' : 'Investigate with AI'}</span>
                    </button>

                    {/* Secondary Actions */}
                    {(findingDetail.status === 'NEW' || findingDetail.status === 'REOPENED') && (
                      <button
                        type="button"
                        className="btn-iac btn-action-40 btn-action-secondary"
                        onClick={() => openLifecycleModal('ACKNOWLEDGE', findingDetail)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        <span>Acknowledge</span>
                      </button>
                    )}

                    {(findingDetail.status === 'NEW' || findingDetail.status === 'ACKNOWLEDGED' || findingDetail.status === 'REOPENED') && (
                      <button
                        type="button"
                        className="btn-iac btn-action-40 btn-action-secondary"
                        onClick={() => openLifecycleModal('INVESTIGATE', findingDetail)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8" />
                          <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                        <span>Start Investigation</span>
                      </button>
                    )}

                    <button
                      type="button"
                      className="btn-iac btn-action-40 btn-action-secondary"
                      onClick={() => openLifecycleModal('ADD_NOTE', findingDetail)}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                      </svg>
                      <span>Add Notes</span>
                    </button>

                    <button
                      type="button"
                      className="btn-iac btn-action-40 btn-action-secondary"
                      onClick={() => handleGenerateRecommendationsForFinding(findingDetail.finding_id)}
                      disabled={generatingRec}
                      title="Deterministically generate operational recommendations from this finding"
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <span>{generatingRec ? 'Synthesizing...' : 'Generate Recommendations'}</span>
                    </button>

                    {(findingDetail.status === 'INVESTIGATING' || findingDetail.status === 'ACKNOWLEDGED') && (
                      <button
                        type="button"
                        className="btn-iac btn-action-40 btn-action-secondary btn-action-resolve"
                        onClick={() => openLifecycleModal('RESOLVE', findingDetail)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                          <polyline points="22 4 12 14.01 9 11.01" />
                        </svg>
                        <span>Resolve Finding</span>
                      </button>
                    )}

                    {findingDetail.status === 'RESOLVED' && (
                      <button
                        type="button"
                        className="btn-iac btn-action-40 btn-action-secondary btn-action-reopen"
                        onClick={() => openLifecycleModal('REOPEN', findingDetail)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                        </svg>
                        <span>Reopen Finding</span>
                      </button>
                    )}
                  </div>

                  {/* Investigation Tabs Navigation (Separate Row below Actions) */}
                  <nav className="iac-consolidated-tab-bar" aria-label="Finding investigation views">
                    <button
                      type="button"
                      className={`iac-tab-item ${detailSubTab === 'ai_investigation' ? 'active' : ''}`}
                      onClick={() => {
                        setDetailSubTab('ai_investigation');
                        if (!aiInvestigation && !investigatingAi) {
                          handleInvestigateWithAi();
                        }
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                      <span>AI Investigation</span>
                      {aiInvestigation && <span className="iac-tab-dot" />}
                      {detailSubTab === 'ai_investigation' && <span className="iac-tab-underline" />}
                    </button>

                    <button
                      type="button"
                      className={`iac-tab-item ${detailSubTab === 'evidence' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('evidence')}
                    >
                      <span>Evidence &amp; Measurements</span>
                      {detailSubTab === 'evidence' && <span className="iac-tab-underline" />}
                    </button>

                    <button
                      type="button"
                      className={`iac-tab-item ${detailSubTab === 'provenance' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('provenance')}
                    >
                      <span>Source Provenance</span>
                      {detailSubTab === 'provenance' && <span className="iac-tab-underline" />}
                    </button>

                    <button
                      type="button"
                      className={`iac-tab-item ${detailSubTab === 'occurrences' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('occurrences')}
                    >
                      <span>Occurrences</span>
                      <span className="iac-tab-count-pill">{findingDetail.occurrences?.length || 0}</span>
                      {detailSubTab === 'occurrences' && <span className="iac-tab-underline" />}
                    </button>

                    <button
                      type="button"
                      className={`iac-tab-item ${detailSubTab === 'audit' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('audit')}
                    >
                      <span>Notes &amp; Audit Trail</span>
                      <span className="iac-tab-count-pill">{findingDetail.audit_trail?.length || 0}</span>
                      {detailSubTab === 'audit' && <span className="iac-tab-underline" />}
                    </button>

                    <button
                      type="button"
                      className={`iac-tab-item ${detailSubTab === 'recs' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('recs')}
                    >
                      <span>Recommendations &amp; Actions</span>
                      <span className="iac-tab-count-pill">{findingRecs.length}</span>
                      {detailSubTab === 'recs' && <span className="iac-tab-underline" />}
                    </button>
                  </nav>

                  {/* Investigation Sub-tab Body */}
                  <div className="iac-detail-body">
                    {/* SUB-TAB 1: EVIDENCE & MEASUREMENTS */}
                    {detailSubTab === 'evidence' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                        {/* Original Anomaly Measurements Grid */}
                        <div>
                          <h4 style={{ margin: '0 0 0.65rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                            Telemetry Measurements &amp; Anomaly Signals
                          </h4>
                          <div className="iac-measurements-grid">
                            <div className="iac-measure-card">
                              <span className="iac-measure-label">Actual Value</span>
                              <span className="iac-measure-value">
                                {findingDetail.actual_value !== null && findingDetail.actual_value !== undefined
                                  ? `${formatVal(findingDetail.actual_value)} ${findingDetail.unit || ''}`
                                  : <span className="iac-measure-unavailable">Unavailable</span>}
                              </span>
                              <span className="iac-measure-sub">Observed telemetry reading</span>
                            </div>

                            <div className="iac-measure-card">
                              <span className="iac-measure-label">Baseline Expected</span>
                              <span className="iac-measure-value">
                                {findingDetail.baseline_value !== null && findingDetail.baseline_value !== undefined
                                  ? `${formatVal(findingDetail.baseline_value)} ${findingDetail.unit || ''}`
                                  : <span className="iac-measure-unavailable">Unavailable</span>}
                              </span>
                              <span className="iac-measure-sub">Prior baseline model</span>
                            </div>

                            <div className="iac-measure-card">
                              <span className="iac-measure-label">Deviation</span>
                              <span
                                className="iac-measure-value"
                                style={{
                                  color: findingDetail.deviation_pct > 0 ? '#ef4444' : 'var(--text-primary)',
                                }}
                              >
                                {findingDetail.deviation_pct !== null && findingDetail.deviation_pct !== undefined
                                  ? `${formatVal(findingDetail.deviation_pct)}%`
                                  : <span className="iac-measure-unavailable">Unavailable</span>}
                              </span>
                              <span className="iac-measure-sub">Deviation from baseline</span>
                            </div>

                            <div className="iac-measure-card">
                              <span className="iac-measure-label">Z-Score Deviation</span>
                              <span className="iac-measure-value">
                                {findingDetail.z_score !== null && findingDetail.z_score !== undefined
                                  ? formatVal(findingDetail.z_score, 2)
                                  : <span className="iac-measure-unavailable">Unavailable</span>}
                              </span>
                              <span className="iac-measure-sub">Sample standard deviations</span>
                            </div>
                          </div>
                        </div>

                        {/* Evidence Limitations Banner */}
                        <div className="iac-limitation-box">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="16" x2="12" y2="12" />
                            <line x1="12" y1="8" x2="12.01" y2="8" />
                          </svg>
                          <div>
                            <strong>Evidence Integrity &amp; Surveillance Constraints:</strong>
                            <div style={{ marginTop: '0.2rem' }}>
                              Detector Code: <code>{findingDetail.anomaly_type}</code> &bull; Detector Name: <code>{findingDetail.detector_name || findingDetail.anomaly_type}</code> (Algorithm v{findingDetail.detector_version || '1.0'}).
                              {findingDetail.baseline_value === null &&
                                ' Baseline historical values are not recorded or not required for this threshold detector (e.g. power factor compliance check).'}
                            </div>
                          </div>
                        </div>

                        {/* Source Data & Upload Provenance Card */}
                        {findingDetail.occurrences && findingDetail.occurrences.length > 0 && (
                          <div>
                            <h4 style={{ margin: '0 0 0.65rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                              Source Telemetry Provenance (Latest Occurrence)
                            </h4>
                            <EvidenceProvenanceCard
                              occurrence={findingDetail.occurrences[0]}
                              finding={findingDetail}
                              isPrimary={true}
                              title="Primary Event Provenance"
                              onOpenProvenanceTab={() => setDetailSubTab('provenance')}
                            />
                          </div>
                        )}
                      </div>
                    )}

                    {/* SUB-TAB: SOURCE PROVENANCE DRILL-DOWN */}
                    {detailSubTab === 'provenance' && (
                      <ProvenanceDrillDownView
                        findingId={findingDetail.finding_id}
                        initialOccurrenceId={findingDetail.occurrences?.[0]?.occurrence_id}
                        occurrences={findingDetail.occurrences || []}
                      />
                    )}

                    {/* SUB-TAB 2: OCCURRENCE HISTORY */}
                    {detailSubTab === 'occurrences' && (
                      <div className="iac-timeline">
                        {(!findingDetail.occurrences || findingDetail.occurrences.length === 0) ? (
                          <div className="iac-empty-state">
                            <span>Zero occurrences recorded in database.</span>
                          </div>
                        ) : (
                          findingDetail.occurrences.map((occ, idx) => {
                            const isExpanded = expandedOccurrences[occ.occurrence_id];
                            return (
                              <div key={occ.occurrence_id || idx} className="iac-timeline-item">
                                <div className="iac-timeline-header">
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                                      Occurrence #{findingDetail.occurrences.length - idx}
                                    </span>
                                    <LineageStatusBadge occurrence={occ} />
                                  </div>
                                  <span>{formatDateTime(occ.detected_at)}</span>
                                </div>

                                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                  Observed: <strong>{formatVal(occ.actual_value)}</strong> &bull; Expected:{' '}
                                  <strong>{formatVal(occ.baseline_value)}</strong> &bull; Deviation:{' '}
                                  <strong>{formatVal(occ.deviation_pct)}%</strong> &bull; Z-Score:{' '}
                                  <strong>{formatVal(occ.z_score)}</strong>
                                </div>

                                <div style={{ marginTop: '0.35rem' }}>
                                  <button
                                    type="button"
                                    className="btn-iac"
                                    style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem' }}
                                    onClick={() =>
                                      setExpandedOccurrences((prev) => ({
                                        ...prev,
                                        [occ.occurrence_id]: !prev[occ.occurrence_id],
                                      }))
                                    }
                                  >
                                    {isExpanded ? 'Hide Lineage' : 'View Upload Provenance'}
                                  </button>
                                </div>

                                {isExpanded && (
                                  <div style={{ marginTop: '0.65rem' }}>
                                    <ProvenanceDrillDownView
                                      findingId={findingDetail.finding_id}
                                      initialOccurrenceId={occ.occurrence_id}
                                      occurrences={findingDetail.occurrences || []}
                                    />
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}

                    {/* SUB-TAB 3: NOTES & AUDIT TRAIL */}
                    {detailSubTab === 'audit' && (
                      <div className="iac-timeline">
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
                          <button
                            type="button"
                            className="btn-iac"
                            onClick={() => openLifecycleModal('ADD_NOTE', findingDetail)}
                          >
                            + Append Diagnostic Note
                          </button>
                        </div>

                        {(!findingDetail.audit_trail || findingDetail.audit_trail.length === 0) ? (
                          <div className="iac-empty-state">
                            <span>No audit events or operator notes recorded yet.</span>
                          </div>
                        ) : (
                          findingDetail.audit_trail.map((log, idx) => (
                            <div key={log.id || log.audit_id || idx} className="iac-timeline-item">
                              <div className="iac-timeline-header">
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                  <span style={{ fontWeight: 700, color: 'var(--brand-purple, #6366f1)' }}>
                                    {log.action}
                                  </span>
                                  {log.from_status && log.to_status && (
                                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                      ({log.from_status} &rarr; {log.to_status})
                                    </span>
                                  )}
                                </div>
                                <span>{formatDateTime(log.performed_at)}</span>
                              </div>

                              {log.notes && (
                                <p style={{ margin: '0.3rem 0 0 0', fontSize: '0.82rem', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                                  {log.notes}
                                </p>
                              )}

                              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                                Attribution: <code>{log.actor_attribution || log.actor_id || 'System'}</code>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    )}

                    {/* SUB-TAB 4: ASSOCIATED RECOMMENDATIONS & ACTIONS */}
                    {detailSubTab === 'recs' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                          <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                            Operational recommendations and corrective tasks synthesized for this finding:
                          </span>
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                              type="button"
                              className="btn-iac btn-iac-primary"
                              onClick={() => handleGenerateRecommendationsForFinding(findingDetail.finding_id)}
                              disabled={generatingRec}
                            >
                              ⚡ Generate Recommendations
                            </button>
                            <button
                              type="button"
                              className="btn-iac"
                              onClick={() => {
                                setDrawerRecId(null);
                                setActiveTab('recommendations');
                              }}
                            >
                              Open Directory
                            </button>
                          </div>
                        </div>

                        {loadingRecs ? (
                          <div className="iac-empty-state">
                            <div className="badge-dot" style={{ width: '12px', height: '12px' }}></div>
                            <span>Loading recommendations and actions...</span>
                          </div>
                        ) : findingRecs.length === 0 ? (
                          <div className="iac-empty-state">
                            <span className="iac-empty-icon">💡</span>
                            <strong>No recommendations generated yet for this finding</strong>
                            <p style={{ margin: 0, fontSize: '0.82rem' }}>
                              Click &ldquo;Generate Recommendations&rdquo; to deterministically synthesize corrective engineering advice from the observed anomaly measurements.
                            </p>
                            <button
                              type="button"
                              className="btn-iac btn-iac-primary"
                              onClick={() => handleGenerateRecommendationsForFinding(findingDetail.finding_id)}
                              disabled={generatingRec}
                              style={{ marginTop: '0.5rem' }}
                            >
                              ⚡ Synthesize Recommendations Now
                            </button>
                          </div>
                        ) : (
                          findingRecs.map((rec) => {
                            const actions = recActionsMap[rec.recommendation_id] || [];
                            const recStClass = `badge-st-${(rec.status || 'open').toLowerCase()}`;
                            const recSevClass = `badge-sev-${(rec.priority || 'medium').toLowerCase()}`;

                            return (
                              <div key={rec.recommendation_id} className="iac-rec-card">
                                <div className="iac-rec-header">
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                                    <span className={`badge-iac ${recSevClass}`}>{rec.priority}</span>
                                    <span className={`badge-iac ${recStClass}`}>{rec.status}</span>
                                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                      {rec.recommendation_id}
                                    </span>
                                  </div>

                                  <div style={{ display: 'flex', gap: '0.4rem' }}>
                                    <button
                                      type="button"
                                      className="btn-iac"
                                      style={{ fontSize: '0.72rem', padding: '0.2rem 0.55rem' }}
                                      onClick={() => setStatusModal({ open: true, rec, targetStatus: rec.status === 'OPEN' ? 'IN_PROGRESS' : 'DISMISSED', loading: false, error: null })}
                                    >
                                      Update Status
                                    </button>
                                    <button
                                      type="button"
                                      className="btn-iac btn-iac-primary"
                                      style={{ fontSize: '0.72rem', padding: '0.2rem 0.55rem' }}
                                      onClick={() =>
                                        setActionModal({
                                          open: true,
                                          mode: 'create',
                                          recId: rec.recommendation_id,
                                          action: null,
                                          parentRec: rec,
                                          loading: false,
                                          error: null,
                                        })
                                      }
                                    >
                                      + Add Corrective Action
                                    </button>
                                  </div>
                                </div>

                                <div>
                                  <h4 style={{ margin: '0 0 0.25rem 0', fontSize: '0.92rem', color: 'var(--text-primary)' }}>
                                    {rec.title}
                                  </h4>
                                  <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                                    {rec.description}
                                  </p>
                                </div>

                                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                  Category: <code>{rec.category}</code> &bull; Created: {formatDateTime(rec.created_at)}
                                </div>

                                {/* Linked Corrective Actions List */}
                                <div className="iac-rec-actions-list">
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                                      Corrective Actions ({actions.length}):
                                    </span>
                                  </div>

                                  {actions.length === 0 ? (
                                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                                      No actions assigned yet. Click &ldquo;+ Add Corrective Action&rdquo; to assign this task.
                                    </span>
                                  ) : (
                                    actions.map((act) => {
                                      const overdue = isActionOverdue(act);
                                      const actStClass = `badge-st-${(act.status || 'open').toLowerCase()}`;

                                      return (
                                        <div key={act.action_id} className="iac-action-row">
                                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                                              <span style={{ fontWeight: 600, fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                                                {act.title}
                                              </span>
                                              <span className={`badge-iac ${actStClass}`}>{act.status}</span>
                                              {overdue && <span className="iac-overdue-tag">OVERDUE</span>}
                                            </div>
                                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                              Owner: <strong>{act.owner || 'Unassigned'}</strong> &bull; Due:{' '}
                                              <strong>{act.due_date ? act.due_date : 'No deadline'}</strong>
                                            </span>
                                          </div>

                                          <div style={{ display: 'flex', gap: '0.35rem' }}>
                                            {act.status === 'OPEN' && (
                                              <button
                                                type="button"
                                                className="btn-iac"
                                                style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem' }}
                                                onClick={() => handleQuickActionStatus(act, 'IN_PROGRESS')}
                                              >
                                                Start
                                              </button>
                                            )}
                                            {act.status === 'IN_PROGRESS' && (
                                              <button
                                                type="button"
                                                className="btn-iac btn-iac-success"
                                                style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem' }}
                                                onClick={() => handleQuickActionStatus(act, 'COMPLETED')}
                                                title="Mark action as completed (does not auto-resolve finding)"
                                              >
                                                Complete
                                              </button>
                                            )}
                                            <button
                                              type="button"
                                              className="btn-iac"
                                              style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem' }}
                                              onClick={() =>
                                                setActionModal({
                                                  open: true,
                                                  mode: 'edit',
                                                  recId: rec.recommendation_id,
                                                  action: act,
                                                  parentRec: rec,
                                                  loading: false,
                                                  error: null,
                                                })
                                              }
                                            >
                                              Edit
                                            </button>
                                          </div>
                                        </div>
                                      );
                                    })
                                  )}
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}

                    {/* SUB-TAB: AI INVESTIGATION */}
                    {detailSubTab === 'ai_investigation' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                        {/* Header Banner */}
                        <div
                          className="iac-ai-agent-banner"
                          style={{
                            padding: '1.25rem',
                            background: 'linear-gradient(135deg, rgba(79, 70, 229, 0.08) 0%, rgba(124, 58, 237, 0.08) 100%)',
                            border: '1px solid rgba(79, 70, 229, 0.25)',
                            borderRadius: '8px',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '1rem',
                            width: '100%',
                            boxSizing: 'border-box',
                          }}
                        >
                          <div style={{ flex: 1, minWidth: '260px' }}>
                            <div className="iac-ai-heading-row" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem', flexWrap: 'wrap' }}>
                              <span style={{ fontWeight: 700, fontSize: '1.05rem', color: '#312e81' }}>
                                ⚡ Industrial Energy Intelligence Agent
                              </span>
                              {aiInvestigation?.inference_source === 'DOMO_AI_MODEL' && (
                                <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '0.2rem 0.5rem', background: '#ecfdf5', color: '#065f46', borderRadius: '4px', border: '1px solid #a7f3d0', whiteSpace: 'nowrap' }}>
                                  Live AI Model · Domo AI
                                </span>
                              )}
                              {aiInvestigation?.inference_source === 'RULE_BASED_FALLBACK' && (
                                <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '0.2rem 0.5rem', background: '#fef3c7', color: '#92400e', borderRadius: '4px', border: '1px solid #fde68a', whiteSpace: 'nowrap' }}>
                                  Rule-Based Fallback · Provider Offline
                                </span>
                              )}
                              {aiInvestigation?.is_regression_case_nov4 && (
                                <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '0.2rem 0.5rem', background: '#dbeafe', color: '#1e40af', borderRadius: '4px', border: '1px solid #bfdbfe', whiteSpace: 'nowrap' }}>
                                  Verified Control Case · FAL-L2 Stoppage Baseline
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                              Autonomous root-cause analysis, operational comparison &amp; trial planning with deterministic citations
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            <button
                              type="button"
                              className="btn-iac btn-action-40 btn-action-secondary"
                              onClick={handleInvestigateWithAi}
                              disabled={investigatingAi}
                            >
                              {investigatingAi ? 'Re-analyzing...' : '↺ Refresh Analysis'}
                            </button>
                            <button
                              type="button"
                              className="btn-iac btn-action-40 btn-action-trial"
                              onClick={handlePlanEnergySavingTrial}
                            >
                              Plan an Energy-Saving Trial →
                            </button>
                          </div>
                        </div>

                        {/* Citation Toast Notification if clicked */}
                        {activeCitationToast && (
                          <div style={{ padding: '0.75rem 1rem', background: '#eff6ff', border: '1px solid #93c5fd', borderRadius: '6px', fontSize: '0.82rem', color: '#1e3a8a', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <strong>CITED RECORD [{activeCitationToast.type}]: </strong>
                              <code>{activeCitationToast.id}</code> — {activeCitationToast.label || 'Authoritative telemetry reading'}
                            </div>
                            <button
                              type="button"
                              style={{ background: 'none', border: 'none', color: '#1e3a8a', cursor: 'pointer', fontWeight: 'bold' }}
                              onClick={() => setActiveCitationToast(null)}
                            >
                              ✕
                            </button>
                          </div>
                        )}

                        {/* Citations List Pill Bar */}
                        {aiInvestigation?.citations && aiInvestigation.citations.length > 0 && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', padding: '0.6rem 0.85rem', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '0.78rem' }}>
                            <span style={{ fontWeight: 600, color: 'var(--text-muted)' }}>Citations:</span>
                            {aiInvestigation.citations.map((c, i) => (
                              <button
                                key={i}
                                type="button"
                                style={{
                                  padding: '0.2rem 0.5rem',
                                  borderRadius: '4px',
                                  background: '#ffffff',
                                  border: '1px solid var(--border-color)',
                                  color: '#4338ca',
                                  fontSize: '0.74rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                                onClick={() => setActiveCitationToast(c)}
                              >
                                📎 {c.id} ({c.type})
                              </button>
                            ))}
                          </div>
                        )}

                        {/* Loading State */}
                        {investigatingAi && (
                          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⚡</div>
                            <strong>Analyzing operational context, telemetry intervals, and stoppage patterns...</strong>
                          </div>
                        )}

                        {/* Error State */}
                        {aiInvestigationError && (
                          <div className="iac-alert-banner error" style={{ padding: '1rem', borderRadius: '6px' }}>
                            <strong>Investigation Error: </strong> {aiInvestigationError}
                          </div>
                        )}

                        {/* The 4 Sections */}
                        {aiInvestigation && !investigatingAi && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            {/* Section 1 */}
                            <div className="iac-card" style={{ padding: '1.25rem', borderLeft: '4px solid #3b82f6', background: 'var(--bg-primary)' }}>
                              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.96rem', fontWeight: 700, color: '#1e3a8a' }}>
                                1. What we observed
                              </h4>
                              <p style={{ margin: 0, fontSize: '0.86rem', lineHeight: 1.6, color: 'var(--text-primary)' }}>
                                {formatCitationsInText(aiInvestigation.what_we_observed, aiInvestigation.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}
                              </p>
                            </div>

                            {/* Section 2 */}
                            <div className="iac-card" style={{ padding: '1.25rem', borderLeft: '4px solid #8b5cf6', background: 'var(--bg-primary)' }}>
                              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.96rem', fontWeight: 700, color: '#5b21b6' }}>
                                2. How it compares
                              </h4>
                              <p style={{ margin: 0, fontSize: '0.86rem', lineHeight: 1.6, color: 'var(--text-primary)' }}>
                                {formatCitationsInText(aiInvestigation.how_it_compares, aiInvestigation.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}
                              </p>
                            </div>

                            {/* Section 3 */}
                            <div className="iac-card" style={{ padding: '1.25rem', borderLeft: '4px solid #f59e0b', background: 'var(--bg-primary)' }}>
                              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.96rem', fontWeight: 700, color: '#92400e' }}>
                                3. What we still need to know
                              </h4>
                              <p style={{ margin: 0, fontSize: '0.86rem', lineHeight: 1.6, color: 'var(--text-primary)' }}>
                                {formatCitationsInText(aiInvestigation.what_we_still_need_to_know, aiInvestigation.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}
                              </p>
                            </div>

                            {/* Section 4 */}
                            <div className="iac-card" style={{ padding: '1.25rem', borderLeft: '4px solid #10b981', background: 'var(--bg-primary)' }}>
                              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.96rem', fontWeight: 700, color: '#065f46' }}>
                                4. What to check next
                              </h4>
                              <p style={{ margin: '0 0 1rem 0', fontSize: '0.86rem', lineHeight: 1.6, color: 'var(--text-primary)' }}>
                                {formatCitationsInText(aiInvestigation.what_to_check_next, aiInvestigation.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}
                              </p>

                              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color-light)' }}>
                                <button
                                  type="button"
                                  className="btn-iac btn-iac-primary"
                                  style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)', color: '#fff', border: 'none', fontWeight: 600 }}
                                  onClick={handlePlanEnergySavingTrial}
                                >
                                  Plan an Energy-Saving Trial →
                                </button>
                                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                  Drafts dual-boundary stoppage trial with output, quality and restart guardrails preconfigured.
                                </span>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: RECOMMENDATIONS DIRECTORY                                          */}
      {/* ========================================================================= */}
      {activeTab === 'recommendations' && (
        <div className="iac-panel">
          <div className="iac-filter-toolbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Plant Recommendations Directory</span>
              <span className="iac-tab-count" style={{ fontSize: '0.75rem' }}>
                {recsTotalCount} Total
              </span>
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn-iac btn-iac-primary"
                onClick={() => setGenerateModal({ open: true, prefillFindingId: selectedFindingId || '', loading: false, error: null })}
              >
                + Synthesize from Finding
              </button>
            </div>
          </div>

          <div style={{ padding: '0.65rem 1rem' }}>
            <RecommendationsDirectoryTable
              selectedFindingId={selectedFindingId}
              onClearFindingFilter={() => setSelectedFindingId(null)}
              plantScope={plantFilter}
              initialStatus="OPEN"
              refreshTrigger={recsRefreshTrigger}
              onOpenRecommendation={(recId) => setDrawerRecId(recId)}
              onStatusChange={(recId, newStatus) => {
                setStatusModal({
                  open: true,
                  rec: { recommendation_id: recId },
                  targetStatus: newStatus,
                  loading: false,
                  error: null,
                });
              }}
              onAddAction={(rec) => {
                setActionModal({
                  open: true,
                  mode: 'create',
                  recId: rec.recommendation_id,
                  action: null,
                  parentRec: rec,
                  loading: false,
                  error: null,
                });
              }}
              onFindingClick={(findingId) => {
                setSelectedFindingId(findingId);
                setActiveTab('workspace');
              }}
              onSynthesize={() =>
                setGenerateModal({
                  open: true,
                  prefillFindingId: selectedFindingId || '',
                  loading: false,
                  error: null,
                })
              }
              onTotalCountChange={(count) => setRecsTotalCount(count)}
            />
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: CORRECTIVE ACTIONS TRACKER                                         */}
      {/* ========================================================================= */}
      {activeTab === 'actions' && (
        <div className="iac-panel">
          <div className="iac-filter-toolbar">
            <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Plant-Wide Corrective Actions Tracker</span>
          </div>
          <div style={{ padding: '1.25rem' }}>
            <ActionsTrackerTable
              onEditAction={(act) =>
                setActionModal({
                  open: true,
                  mode: 'edit',
                  recId: act.recommendation_id,
                  action: act,
                  parentRec: null,
                  loading: false,
                  error: null,
                })
              }
              onOpenRecommendation={(recId) => {
                setDrawerRecId(recId);
              }}
              onOpenWorkflowModal={(act) => setWorkflowAction(act)}
              refreshTrigger={kpis.openActions}
            />
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: FACTORY VERIFIED SAVINGS LEDGER                                    */}
      {/* ========================================================================= */}
      {activeTab === 'ledger' && (
        <div className="iac-panel">
          <div className="iac-filter-toolbar">
            <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Factory Verified Savings Ledger (M&amp;V Governance)</span>
          </div>
          <div style={{ padding: '1.25rem' }}>
            <SavingsLedgerSection
              onInspectAction={(actionId) => {
                recommendationsApi.getAction(actionId).then((act) => setWorkflowAction(act)).catch(console.error);
              }}
            />
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: LIVE ANOMALY SURVEILLANCE                                          */}
      {/* ========================================================================= */}
      {activeTab === 'surveillance' && (
        <div className="iac-panel">
          <div className="iac-filter-toolbar">
            <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>
              Multi-Algorithm Surveillance Suite Signals
            </span>

            <select
              className="iac-filter-select"
              value={surveillanceSeverityFilter}
              onChange={(e) => setSurveillanceSeverityFilter(e.target.value)}
            >
              <option value="ALL">Severity: ALL</option>
              {SEVERITIES.map((sev) => (
                <option key={sev} value={sev}>Severity: {sev}</option>
              ))}
            </select>

            <select
              className="iac-filter-select"
              value={surveillanceCategoryFilter}
              onChange={(e) => setSurveillanceCategoryFilter(e.target.value)}
            >
              <option value="ALL">Category: ALL</option>
              <option value="CONSUMPTION_SPIKE">Consumption Spike</option>
              <option value="CONSUMPTION_DROP">Consumption Drop</option>
              <option value="LOW_POWER_FACTOR">Low Power Factor</option>
              <option value="ZERO_PRODUCTION_STANDBY">Zero-Production Standby</option>
            </select>

            <button
              type="button"
              className="btn-iac btn-iac-primary"
              style={{ marginLeft: 'auto' }}
              onClick={handleSyncAnomalies}
              disabled={syncingAnomalies}
            >
              {syncingAnomalies ? 'Syncing...' : 'Sync Detected Signals into Findings'}
            </button>
          </div>

          <div style={{ padding: '1.25rem' }}>
            {loadingSurveillance ? (
              <div className="iac-empty-state">
                <div className="badge-dot" style={{ width: '12px', height: '12px' }}></div>
                <span>Executing multi-algorithm anomaly surveillance detectors...</span>
              </div>
            ) : surveillanceError ? (
              <div className="iac-empty-state">
                <span style={{ color: '#ef4444' }}>Error: {surveillanceError}</span>
                <button type="button" className="btn-iac" onClick={loadSurveillanceData}>
                  Retry Detection
                </button>
              </div>
            ) : (
              <AlertList alerts={filteredSurveillanceAlerts} />
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODALS & DIALOGS                                                          */}
      {/* ========================================================================= */}

      {/* Finding Lifecycle Action Modal */}
      {lifecycleModal.open && (
        <div className="findings-modal-overlay" onClick={closeLifecycleModal}>
          <div className="findings-modal" onClick={(e) => e.stopPropagation()}>
            <header className="findings-modal-header">
              <h3>
                {lifecycleModal.action === 'ACKNOWLEDGE' && 'Acknowledge Operational Finding'}
                {lifecycleModal.action === 'INVESTIGATE' && 'Initiate Finding Investigation'}
                {lifecycleModal.action === 'ADD_NOTE' && 'Add Investigation Diagnostic Note'}
                {lifecycleModal.action === 'RESOLVE' && 'Confirm Finding Resolution'}
                {lifecycleModal.action === 'REOPEN' && 'Confirm Finding Reopening'}
              </h3>
              <button
                type="button"
                className="btn-drawer-close"
                onClick={closeLifecycleModal}
                disabled={lifecycleModal.loading}
              >
                ✕
              </button>
            </header>

            <div className="findings-modal-body">
              {lifecycleModal.error && (
                <div className="findings-banner-alert error">
                  {lifecycleModal.error}
                </div>
              )}

              <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {lifecycleModal.action === 'ACKNOWLEDGE' &&
                  `Transition finding ${lifecycleModal.finding?.finding_id} from ${lifecycleModal.finding?.status} to ACKNOWLEDGED.`}
                {lifecycleModal.action === 'INVESTIGATE' &&
                  `Transition finding ${lifecycleModal.finding?.finding_id} to INVESTIGATING status to track root-cause diagnostics.`}
                {lifecycleModal.action === 'ADD_NOTE' &&
                  `Append a diagnostic progress note to finding ${lifecycleModal.finding?.finding_id}. Status will remain ${lifecycleModal.finding?.status}.`}
                {lifecycleModal.action === 'RESOLVE' &&
                  `Confirm resolution of finding ${lifecycleModal.finding?.finding_id}. Mandatory resolution notes are required to document the corrective action.`}
                {lifecycleModal.action === 'REOPEN' &&
                  `Reopen finding ${lifecycleModal.finding?.finding_id}. A documented engineering justification reason is required.`}
              </p>

              <div>
                <label className="findings-form-label">
                  {lifecycleModal.action === 'RESOLVE'
                    ? 'Resolution Notes (Mandatory)'
                    : lifecycleModal.action === 'REOPEN'
                      ? 'Engineering Reopening Justification (Mandatory)'
                      : 'Notes / Comments'}
                </label>
                <textarea
                  className="findings-form-textarea"
                  rows={4}
                  placeholder="Enter diagnostic details, findings, or notes..."
                  value={lifecycleModal.commentOrNote}
                  onChange={(e) =>
                    setLifecycleModal((prev) => ({ ...prev, commentOrNote: e.target.value }))
                  }
                  disabled={lifecycleModal.loading}
                />
              </div>

              <div>
                <label className="findings-form-label">Actor / Caller Attribution</label>
                <input
                  type="text"
                  className="findings-form-input"
                  placeholder="e.g., Electrical Engineer, Plant Supervisor"
                  value={lifecycleModal.callerAttribution}
                  onChange={(e) =>
                    setLifecycleModal((prev) => ({ ...prev, callerAttribution: e.target.value }))
                  }
                  disabled={lifecycleModal.loading}
                />
              </div>
            </div>

            <footer className="findings-modal-footer">
              <button
                type="button"
                className="btn-findings"
                onClick={closeLifecycleModal}
                disabled={lifecycleModal.loading}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`btn-findings ${lifecycleModal.action === 'RESOLVE'
                  ? 'btn-findings-success'
                  : lifecycleModal.action === 'REOPEN'
                    ? 'btn-findings-danger'
                    : 'btn-findings-primary'
                  }`}
                onClick={handleExecuteLifecycleAction}
                disabled={lifecycleModal.loading}
              >
                {lifecycleModal.loading ? 'Updating...' : 'Confirm Action'}
              </button>
            </footer>
          </div>
        </div>
      )}

      {/* Corrective Action Modal (Create & Edit) */}
      <ActionModal
        isOpen={actionModal.open}
        mode={actionModal.mode}
        recId={actionModal.recId}
        action={actionModal.action}
        parentRec={actionModal.parentRec}
        onClose={() => setActionModal((prev) => ({ ...prev, open: false }))}
        onSubmit={handleActionModalSubmit}
        loading={actionModal.loading}
        error={actionModal.error}
      />

      {/* Recommendation Status Transition Modal */}
      <StatusModal
        isOpen={statusModal.open}
        rec={statusModal.rec}
        targetStatus={statusModal.targetStatus}
        onClose={() => setStatusModal((prev) => ({ ...prev, open: false }))}
        onSubmit={handleStatusModalSubmit}
        loading={statusModal.loading}
        error={statusModal.error}
      />

      {/* Recommendation Generation Modal */}
      <GenerateModal
        isOpen={generateModal.open}
        prefillFindingId={generateModal.prefillFindingId}
        onClose={() => setGenerateModal((prev) => ({ ...prev, open: false }))}
        onSubmit={handleGenerateModalSubmit}
        loading={generateModal.loading}
        error={generateModal.error}
      />

      {/* Recommendation Slide-Out Drawer (Deep Linking) */}
      {drawerRecId && (
        <RecommendationDrawer
          recommendationId={drawerRecId}
          isOpen={Boolean(drawerRecId)}
          onClose={() => setDrawerRecId(null)}
          onStatusTransition={(rec, status) => {
            setStatusModal({ open: true, rec, targetStatus: status, loading: false, error: null });
          }}
          onAddAction={(rec) => {
            setActionModal({
              open: true,
              mode: 'create',
              recId: rec.recommendation_id,
              action: null,
              parentRec: rec,
              loading: false,
              error: null,
            });
          }}
          onEditAction={(act, rec) => {
            setActionModal({
              open: true,
              mode: 'edit',
              recId: act.recommendation_id,
              action: act,
              parentRec: rec,
              loading: false,
              error: null,
            });
          }}
          onRecommendationUpdated={() => {
            loadAuthoritativeKpis(plantFilter);
            setRecsRefreshTrigger((prev) => prev + 1);
            if (selectedFindingId) loadFindingDetailAndRecs(selectedFindingId);
          }}
        />
      )}

      {/* Operator Workflow Modal for Energy-Saving Trials */}
      {workflowAction && (
        <InterventionWorkflowModal
          action={workflowAction}
          isOpen={Boolean(workflowAction)}
          onClose={() => setWorkflowAction(null)}
          onActionUpdated={() => {
            if (selectedFindingId) loadFindingDetailAndRecs(selectedFindingId);
          }}
        />
      )}
    </div>
  );
}

