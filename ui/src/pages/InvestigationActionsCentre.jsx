import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { findingsApi } from '../services/findingsApi';
import { recommendationsApi } from '../services/recommendationsApi';
import { anomalyApi } from '../services/anomalyApi';
import { formatDateTime, formatNumber, formatFindingTitle } from '../utils/formatters';
import { generateSparklinePaths } from '../components/common/KpiCard';

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

function formatActionDueDate(dateStr) {
  if (!dateStr) return 'No deadline';
  try {
    const raw = String(dateStr).trim();
    const datePart = raw.includes('T') ? raw.split('T')[0] : (raw.includes(' ') ? raw.split(' ')[0] : raw);
    const [yStr, mStr, dStr] = datePart.split('-');
    if (yStr && mStr && dStr) {
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const mIdx = parseInt(mStr, 10) - 1;
      const day = parseInt(dStr, 10);
      if (mIdx >= 0 && mIdx < 12 && !isNaN(day)) {
        return `${day} ${months[mIdx]} ${yStr}`;
      }
    }
    const d = new Date(raw);
    if (!isNaN(d.getTime())) {
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

function formatReadableTimestamp(tsStr) {
  if (!tsStr) return 'Unknown';
  try {
    const raw = String(tsStr).trim();
    const [datePart, timePart] = raw.split(/[T ]/);
    if (datePart) {
      const [y, m, d] = datePart.split('-');
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const mIdx = parseInt(m, 10) - 1;
      const day = parseInt(d, 10);
      const formattedDate = mIdx >= 0 && mIdx < 12 && !isNaN(day) ? `${day} ${months[mIdx]} ${y}` : datePart;
      const cleanTime = timePart ? timePart.substring(0, 5) : '';
      return cleanTime ? `${formattedDate}, ${cleanTime}` : formattedDate;
    }
    return tsStr;
  } catch {
    return tsStr;
  }
}

function getFindingDisplayTitle(findingDetail, aiInvestigation) {
  if (aiInvestigation?.title && typeof aiInvestigation.title === 'string' && aiInvestigation.title.trim() && aiInvestigation.title !== '[object Object]') {
    return aiInvestigation.title.trim();
  }
  let candidate = null;
  if (findingDetail) {
    if (typeof findingDetail === 'string') {
      candidate = findingDetail;
    } else if (typeof findingDetail === 'object' && findingDetail !== null) {
      candidate = findingDetail.title || findingDetail.display_title || findingDetail.finding_title || findingDetail.anomaly_type;
    }
  }
  if (typeof candidate === 'object' && candidate !== null) {
    candidate = candidate.title || candidate.display_title || candidate.name;
  }
  if (candidate && typeof candidate === 'string' && candidate !== '[object Object]') {
    const trimmed = candidate.trim();
    if (trimmed.includes('_') || trimmed === trimmed.toUpperCase()) {
      const readable = trimmed.replace(/_/g, ' ').toLowerCase();
      return readable.charAt(0).toUpperCase() + readable.slice(1);
    }
    return trimmed;
  }
  return 'Finding analysis';
}

function parseRecommendationContent(rec, findingDetail) {
  const desc = rec?.description || '';

  let observedText = '';
  let comparisonText = '';
  let causesText = '';
  let investigationText = '';

  const s1Match = desc.match(/###\s*1\.?\s*Observed Condition([\s\S]*?)(?=###\s*2|$)/i);
  if (s1Match) observedText = s1Match[1].trim();

  const s2Match = desc.match(/###\s*2\.?\s*Comparison and Evidence([\s\S]*?)(?=###\s*3|$)/i);
  if (s2Match) comparisonText = s2Match[1].trim();

  const s3Match = desc.match(/###\s*3\.?\s*Possible Causes and Limitations([\s\S]*?)(?=###\s*4|$)/i);
  if (s3Match) causesText = s3Match[1].trim();

  const s4Match = desc.match(/###\s*4\.?\s*Suggested Investigation([\s\S]*?)$/i);
  if (s4Match) investigationText = s4Match[1].trim();

  if (!s1Match && !s2Match && !s3Match && !s4Match) {
    observedText = desc;
  }

  let team = '';
  const teamMatch = investigationText.match(/Responsible Team:\s*([^\n-]+)/i);
  if (teamMatch) {
    team = teamMatch[1].trim();
  } else if (rec?.assigned_team) {
    team = rec.assigned_team;
  } else if (rec?.owner) {
    team = rec.owner;
  } else {
    team = 'Facilities';
  }

  let conditionToCheck = '';
  const condMatch = investigationText.match(/Condition to Check Before Modifying State:\s*([^\n-]+)/i);
  if (condMatch) conditionToCheck = condMatch[1].trim();

  let recommendedAction = '';
  const actMatch = investigationText.match(/Recommended Action:\s*([^\n]+)/i);
  if (actMatch) recommendedAction = actMatch[1].trim();

  const possibleCauses = [];
  const limitations = [];

  const itemRegex = /-\s*\[(HYPOTHESIS|LIMITATION)-([^:\]]+)(?::\s*([^\]]+))?\]\s*([^\n\-\]]+)/gi;
  let match;
  while ((match = itemRegex.exec(causesText)) !== null) {
    const kind = match[1].toUpperCase();
    const subType = (match[3] || match[2] || '').trim();
    const explanation = match[4].trim();
    if (kind === 'HYPOTHESIS') {
      possibleCauses.push({
        label: subType || 'Possible Cause',
        text: explanation,
      });
    } else {
      limitations.push({
        label: subType || 'Limitation',
        text: explanation,
      });
    }
  }

  if (possibleCauses.length === 0 && causesText) {
    const lines = causesText.split(/\r?\n| - /).map((l) => l.trim()).filter(Boolean);
    for (const line of lines) {
      if (line.toLowerCase().includes('limitation')) {
        limitations.push({ label: 'Limitation', text: line.replace(/^-\s*\[.*?\]\s*/, '') });
      } else {
        possibleCauses.push({ label: 'Possible Cause', text: line.replace(/^-\s*\[.*?\]\s*/, '') });
      }
    }
  }

  let storedDeficit = null;
  const deficitMatch = desc.match(/deficit:\s*([0-9.]+)/i);
  if (deficitMatch) {
    storedDeficit = deficitMatch[1];
  } else if (findingDetail?.current_deviation_score !== undefined && findingDetail?.current_deviation_score !== null) {
    storedDeficit = String(findingDetail.current_deviation_score);
  }

  const isPf =
    (findingDetail?.anomaly_type || rec?.category || '').toUpperCase().includes('POWER_FACTOR') ||
    (findingDetail?.anomaly_type || '').toUpperCase().includes('PF') ||
    (rec?.title || '').toLowerCase().includes('power factor');

  const meter = findingDetail?.meter_id || rec?.meter_id || 'MTR-SMT';
  const line = findingDetail?.line_id || rec?.line_id || 'SMT-L1';

  let shortTitle = rec?.title || 'Check recommendation';
  if (isPf) {
    shortTitle = `Check power factor correction on ${meter}`;
  } else if ((rec?.title || '').toLowerCase().includes('stoppage')) {
    shortTitle = `Check zero-output stoppage on ${line}`;
  } else if ((rec?.title || '').toLowerCase().includes('baseload')) {
    shortTitle = `Check baseload electricity shift on ${meter}`;
  } else if ((rec?.title || '').toLowerCase().includes('peak')) {
    shortTitle = `Review peak hourly consumption on ${meter}`;
  } else if ((rec?.title || '').toLowerCase().includes('intensity')) {
    shortTitle = `Review specific energy consumption on ${line}`;
  } else if (shortTitle.includes("meter '") || shortTitle.includes("line '")) {
    shortTitle = shortTitle.replace(/meter '([^']+)'/, '$1').replace(/line '([^']+)'/, '$1');
  }

  const bullets = [];
  if (isPf) {
    bullets.push('Confirm which motors were running and their load at the time.');
    bullets.push('Inspect the capacitor bank and its power factor controller.');
  } else {
    if (conditionToCheck) bullets.push(conditionToCheck);
    if (recommendedAction) bullets.push(recommendedAction);
    if (bullets.length === 0 && rec?.title) bullets.push(rec.title);
  }

  return {
    shortTitle,
    team,
    bullets: bullets.slice(0, 2),
    possibleCauses,
    limitations,
    comparisonText,
    observedText,
    storedDeficit,
    isPf,
  };
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

function cleanLegacyMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/---/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
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
  const tableContainerRef = useRef(null);
  const activeTabRef = useRef(null);

  useEffect(() => {
    if (activeTabRef.current) {
      activeTabRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }, [activeTab]);

  // Reset table scroll position to top whenever filters or page offset change
  useEffect(() => {
    if (tableContainerRef.current) {
      tableContainerRef.current.scrollTop = 0;
    }
  }, [offset, plantFilter, statusFilter, severityFilter, typeFilter, debouncedSearch]);

  // Build the 5 summary KPI cards with sparkline paths (historical counts when available, decorative wave otherwise)
  const summaryKpiCards = useMemo(() => {
    const historyMap = kpis.history || {};
    const defs = [
      {
        id: 'active-findings',
        label: 'Active findings',
        count: kpis.activeFindings,
        history: historyMap.activeFindings,
        decorativeWave: [10, 14, 13, 18, 16, 22, 20, 26],
        isSelected: activeTab === 'workspace' && statusFilter === 'ACTIVE' && severityFilter !== 'CRITICAL',
        title: 'Click to view Active findings in queue',
        onClick: () => {
          setActiveTab('workspace');
          setStatusFilter('ACTIVE');
          setSeverityFilter('ALL');
          setOffset(0);
        },
      },
      {
        id: 'critical-high',
        label: 'Critical & high priority',
        count: kpis.criticalHigh,
        history: historyMap.criticalHigh,
        decorativeWave: [12, 11, 14, 13, 16, 15, 18, 17],
        isSelected: activeTab === 'workspace' && severityFilter === 'CRITICAL',
        title: 'Click to filter Critical & High findings',
        onClick: () => {
          setActiveTab('workspace');
          setStatusFilter('ACTIVE');
          setSeverityFilter('CRITICAL');
          setOffset(0);
        },
      },
      {
        id: 'awaiting-investigation',
        label: 'Awaiting investigation',
        count: kpis.awaitingInvestigation,
        history: historyMap.awaitingInvestigation,
        decorativeWave: [10, 13, 12, 16, 15, 19, 18, 22],
        isSelected: activeTab === 'workspace' && statusFilter === 'NEW',
        title: 'Click to view New & Acknowledged findings',
        onClick: () => {
          setActiveTab('workspace');
          setStatusFilter('NEW');
          setSeverityFilter('ALL');
          setOffset(0);
        },
      },
      {
        id: 'open-recommendations',
        label: 'Open recommendations',
        count: kpis.openRecommendations,
        history: historyMap.openRecommendations,
        decorativeWave: [9, 11, 10, 14, 13, 17, 16, 21],
        isSelected: activeTab === 'recommendations',
        title: 'Click to view Open Recommendations Directory',
        onClick: () => setActiveTab('recommendations'),
      },
      {
        id: 'corrective-actions',
        label: 'Corrective actions',
        count: kpis.openActions,
        history: historyMap.openActions,
        decorativeWave: [10, 12, 14, 15, 17, 19, 21, 24],
        isSelected: activeTab === 'actions',
        title: 'Click to view Corrective Actions Tracker',
        onClick: () => setActiveTab('actions'),
      },
    ];

    return defs.map((card) => {
      const hasHistory = Array.isArray(card.history) && card.history.length >= 2;
      const series = hasHistory ? card.history : card.decorativeWave;
      const sparkPaths = generateSparklinePaths(series, 300, 18, 2, 3);
      const dataSignature = hasHistory ? card.history.join(',') : String(card.count);
      return { ...card, hasHistory, sparkPaths, dataSignature };
    });
  }, [kpis, activeTab, statusFilter, severityFilter]);

  // Selected Finding Investigation Workspace State
  const [selectedFindingId, setSelectedFindingId] = useState(urlFindingId || null);
  const [findingDetail, setFindingDetail] = useState(null);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [detailSubTab, setDetailSubTab] = useState('ai_investigation'); // 'evidence' | 'occurrences' | 'audit' | 'recs' | 'ai_investigation'
  const [expandedOccurrences, setExpandedOccurrences] = useState({});
  const [moreActionsOpen, setMoreActionsOpen] = useState(false);
  const moreActionsRef = useRef(null);
  const activeDetailTabRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (moreActionsRef.current && !moreActionsRef.current.contains(e.target)) {
        setMoreActionsOpen(false);
      }
    };
    if (moreActionsOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('touchstart', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [moreActionsOpen]);

  useEffect(() => {
    if (activeDetailTabRef.current) {
      activeDetailTabRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }, [detailSubTab]);

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
  const activeAiFindingIdRef = useRef(null);
  const inFlightAiFindingRef = useRef(null);
  const aiRequestSeqRef = useRef(0);

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
      if (activeAiFindingIdRef.current !== findingId) return;
      setFindingDetail(detail);

      const recs = recsRes.items || [];
      setFindingRecs(recs);

      // Load linked actions for each recommendation
      if (recs.length > 0) {
        const actionPromises = recs.map((r) =>
          recommendationsApi.listActions({ recommendation_id: r.recommendation_id, limit: 50 })
        );
        const actionResults = await Promise.all(actionPromises);
        if (activeAiFindingIdRef.current !== findingId) return;
        const actionsByRec = {};
        recs.forEach((r, idx) => {
          actionsByRec[r.recommendation_id] = actionResults[idx].items || [];
        });
        setRecActionsMap(actionsByRec);
      } else {
        setRecActionsMap({});
      }
    } catch (err) {
      if (activeAiFindingIdRef.current !== findingId) return;
      console.error(`Failed to load details for finding ${findingId}:`, err);
      setDetailError(err.message || 'Unable to load finding details.');
    } finally {
      if (activeAiFindingIdRef.current === findingId) {
        setLoadingDetail(false);
        setLoadingRecs(false);
      }
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
    activeAiFindingIdRef.current = selectedFindingId;
    inFlightAiFindingRef.current = null;
    aiRequestSeqRef.current += 1;
    setInvestigatingAi(false);
    setAiInvestigation(null);
    setAiInvestigationError(null);
    setActiveCitationToast(null);
    setSelectedOccurrenceId(null);
    setFindingDetail(null);
    if (selectedFindingId) {
      loadFindingDetailAndRecs(selectedFindingId);
    } else {
      setFindingRecs([]);
      setRecActionsMap({});
    }
  }, [selectedFindingId, loadFindingDetailAndRecs]);

  useEffect(() => {
    if (detailSubTab === 'ai_investigation' && selectedFindingId && !aiInvestigation && !investigatingAi && !aiInvestigationError) {
      handleInvestigateWithAi();
    }
  }, [detailSubTab, selectedFindingId, aiInvestigation, investigatingAi, aiInvestigationError]);

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
    const reqFindingId = selectedFindingId;
    if (!reqFindingId || inFlightAiFindingRef.current === reqFindingId) return;
    activeAiFindingIdRef.current = reqFindingId;
    inFlightAiFindingRef.current = reqFindingId;
    const reqSeq = ++aiRequestSeqRef.current;
    setInvestigatingAi(true);
    setAiInvestigationError(null);
    try {
      const validDetail = findingDetail?.finding_id === reqFindingId ? findingDetail : null;
      const validOccs = validDetail?.occurrences || [];
      const occId =
        (selectedOccurrenceId && validOccs.some((o) => o.occurrence_id === selectedOccurrenceId)
          ? selectedOccurrenceId
          : null) ||
        validOccs[0]?.occurrence_id ||
        null;
      const url = `/api/findings/${encodeURIComponent(reqFindingId)}/investigate-ai${occId ? `?occurrence_id=${encodeURIComponent(occId)}` : ''}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Investigation failed with HTTP ${res.status}`);
      }
      const data = await res.json();
      if (activeAiFindingIdRef.current === reqFindingId && reqSeq === aiRequestSeqRef.current) {
        setAiInvestigation(data);
        setAiInvestigationError(null);
        setDetailSubTab('ai_investigation');
      }
    } catch (err) {
      if (activeAiFindingIdRef.current === reqFindingId && reqSeq === aiRequestSeqRef.current) {
        console.error('AI investigation failed:', err);
        setAiInvestigationError(err.message || 'AI Investigation service temporarily unavailable.');
      }
    } finally {
      if (activeAiFindingIdRef.current === reqFindingId && reqSeq === aiRequestSeqRef.current) {
        inFlightAiFindingRef.current = null;
        setInvestigatingAi(false);
      }
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

      {/* SECTION A: Authoritative Operational KPI Summary Strip */}
      <section className="iac-kpi-strip" role="region" aria-label="Investigation Summary Metrics">
        {summaryKpiCards.map((card) => (
          <button
            key={card.id}
            type="button"
            className={`iac-kpi-strip-item ${card.isSelected ? 'is-selected active-filter' : ''}`}
            onClick={card.onClick}
            title={card.title}
            aria-pressed={card.isSelected}
          >
            <div className="iac-kpi-strip-content">
              <span className="iac-kpi-strip-label">{card.label}</span>
              <span className="iac-kpi-strip-count">
                {kpis.loading ? '...' : formatNumber(card.count)}
              </span>
            </div>
            <div
              className="kpi-sparkline-wrap"
              aria-hidden={card.hasHistory ? undefined : 'true'}
            >
              {!kpis.loading && card.sparkPaths && (
                <svg
                  viewBox="0 0 300 18"
                  preserveAspectRatio="none"
                  className="kpi-sparkline-svg"
                  role={card.hasHistory ? 'img' : undefined}
                  aria-label={card.hasHistory ? `${card.label} historical count trend` : undefined}
                >
                  <path
                    key={`line-${card.id}-${card.dataSignature}`}
                    d={card.sparkPaths.linePath}
                    fill="none"
                    stroke="#7c3aed"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                    style={{
                      '--path-len': card.sparkPaths.pathLength,
                      strokeDasharray: card.sparkPaths.pathLength,
                      strokeDashoffset: card.sparkPaths.pathLength,
                    }}
                    className="kpi-sparkline-line"
                  />
                </svg>
              )}
            </div>
          </button>
        ))}
      </section>

      {/* Top Navigation Tabs */}
      <nav className="iac-tabs-bar" role="tablist" aria-label="Investigation & Actions Tabs">
        <button
          ref={activeTab === 'workspace' ? activeTabRef : null}
          type="button"
          role="tab"
          aria-selected={activeTab === 'workspace'}
          aria-label={`Findings & Investigation Workspace (${findingsData.total})`}
          className={`iac-tab-btn ${activeTab === 'workspace' ? 'active' : ''}`}
          onClick={() => setActiveTab('workspace')}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect width="7" height="9" x="3" y="3" rx="1" />
            <rect width="7" height="5" x="14" y="3" rx="1" />
            <rect width="7" height="9" x="14" y="12" rx="1" />
            <rect width="7" height="5" x="3" y="16" rx="1" />
          </svg>
          Findings
          <span className="iac-tab-count">{findingsData.total}</span>
        </button>

        <button
          ref={activeTab === 'recommendations' ? activeTabRef : null}
          type="button"
          role="tab"
          aria-selected={activeTab === 'recommendations'}
          aria-label={`Recommendations Directory (${kpis.openRecommendations})`}
          className={`iac-tab-btn ${activeTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          Recommendations
          <span className="iac-tab-count">{kpis.openRecommendations}</span>
        </button>

        <button
          ref={activeTab === 'actions' ? activeTabRef : null}
          type="button"
          role="tab"
          aria-selected={activeTab === 'actions'}
          aria-label={`Corrective Actions Tracker (${kpis.openActions})`}
          className={`iac-tab-btn ${activeTab === 'actions' ? 'active' : ''}`}
          onClick={() => setActiveTab('actions')}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
            <path d="M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1Z" />
            <path d="m9 14 2 2 4-4" />
          </svg>
          Corrective actions
          <span className="iac-tab-count">{kpis.openActions}</span>
        </button>

        <button
          ref={activeTab === 'ledger' ? activeTabRef : null}
          type="button"
          role="tab"
          aria-selected={activeTab === 'ledger'}
          aria-label="Verified Savings Ledger"
          className={`iac-tab-btn ${activeTab === 'ledger' ? 'active' : ''}`}
          onClick={() => setActiveTab('ledger')}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="1" x2="12" y2="23" />
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          </svg>
          Verified savings
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
                aria-label="Filter findings by status"
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="ACTIVE">Active</option>
                <option value="ALL">All statuses</option>
                <option value="NEW">New</option>
                <option value="ACKNOWLEDGED">Acknowledged</option>
                <option value="INVESTIGATING">Investigating</option>
                <option value="RESOLVED">Resolved</option>
                <option value="REOPENED">Reopened</option>
              </select>

              {/* Severity Filter */}
              <select
                className="iac-filter-select"
                value={severityFilter}
                aria-label="Filter findings by severity"
                onChange={(e) => {
                  setSeverityFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="ALL">All severities</option>
                {SEVERITIES.map((sev) => (
                  <option key={sev} value={sev}>
                    {sev.charAt(0) + sev.slice(1).toLowerCase()}
                  </option>
                ))}
              </select>

              {/* Detector Type Filter */}
              <select
                className="iac-filter-select"
                value={typeFilter}
                aria-label="Filter findings by detector"
                onChange={(e) => {
                  setTypeFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="ALL">All detectors</option>
                <option value="statistical_zscore">Statistical Z-Score</option>
                <option value="rolling_baseline">Rolling Baseline</option>
                <option value="low_power_factor">Low Power Factor</option>
                <option value="zero_production_standby">Zero-Production Standby</option>
              </select>

              {/* Plant Filter */}
              <select
                className="iac-filter-select"
                value={plantFilter}
                aria-label="Filter findings by plant"
                onChange={(e) => {
                  setPlantFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All plants</option>
                <option value="IN-TN-01">IN-TN-01 (Chennai)</option>
              </select>
            </div>

            {/* Findings Queue Table */}
            <div className="iac-table-wrapper" ref={tableContainerRef}>
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
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                <span className="font-mono">ID: {f.finding_id}</span>
                                {f.current_actual_value != null && (
                                  <>
                                    <span>•</span>
                                    <span>
                                      {f.anomaly_type === 'LOW_POWER_FACTOR'
                                        ? `PF: ${Number(f.current_actual_value).toFixed(2)}${f.current_baseline_value != null ? ` (threshold: ${Number(f.current_baseline_value).toFixed(2)})` : ''}`
                                        : `Actual: ${f.current_actual_value}${f.current_baseline_value != null ? ` (baseline: ${f.current_baseline_value})` : ''}`}
                                    </span>
                                  </>
                                )}
                              </div>
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
                      <div className="iac-finding-title-row">
                        <h2 className="iac-finding-title">
                          {formatFindingTitle(findingDetail.title || findingDetail.anomaly_type)}
                        </h2>
                        <div className="iac-finding-badges">
                          {findingDetail.severity && (
                            <span className={`badge-iac badge-sev-${findingDetail.severity.toLowerCase()}`}>
                              {findingDetail.severity.charAt(0).toUpperCase() + findingDetail.severity.slice(1).toLowerCase()}
                            </span>
                          )}
                          {findingDetail.status && (
                            <span className={`badge-iac badge-st-${findingDetail.status.toLowerCase()}`}>
                              {findingDetail.status.charAt(0).toUpperCase() + findingDetail.status.slice(1).toLowerCase()}
                            </span>
                          )}
                        </div>
                      </div>

                      <button
                        type="button"
                        className="iac-close-btn"
                        onClick={() => setSelectedFindingId(null)}
                        aria-label="Close finding"
                        title="Close finding"
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </div>

                    {/* Compact Natural-Wrapping 12px Metadata Row */}
                    <div className="iac-finding-meta-row">
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">Plant:</span>
                        <strong>{findingDetail.plant_id || 'IN-TN-01'}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">Asset:</span>
                        <strong>{findingDetail.meter_id || findingDetail.line_id || 'Plant-wide'}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">First detected:</span>
                        <strong>{formatReadableTimestamp(findingDetail.first_detected_at)}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item">
                        <span className="iac-meta-label">Occurrences:</span>
                        <strong>{findingDetail.occurrence_count || (findingDetail.occurrences ? findingDetail.occurrences.length : 1)}</strong>
                      </span>
                      <span className="iac-meta-dot">&bull;</span>
                      <span className="iac-meta-item iac-meta-id">
                        <span className="iac-meta-label">ID:</span>
                        <code className="iac-finding-id-code">{findingDetail.finding_id}</code>
                      </span>
                    </div>

                    {/* Operational Description (Omitted when empty) */}
                    {Boolean(findingDetail.description && findingDetail.description.trim()) && (
                      <p className="iac-finding-narrative">
                        {findingDetail.description}
                      </p>
                    )}
                  </header>

                  {/* Investigation Lifecycle Actions Toolbar (32-34px controls, 13px labels, 8px gaps) */}
                  <div className="iac-lifecycle-toolbar">
                    {/* Primary Purple Action: Analyze with AI */}
                    <button
                      type="button"
                      className="btn-iac btn-iac-primary btn-action-ai"
                      onClick={handleInvestigateWithAi}
                      disabled={investigatingAi}
                      title="Run AI root-cause investigation"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={investigatingAi ? 'is-spinning' : ''}>
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                      <span>{investigatingAi ? 'Analyzing…' : 'Analyze with AI'}</span>
                    </button>

                    {/* Separate Workflow Action */}
                    {(findingDetail.status === 'NEW' || findingDetail.status === 'ACKNOWLEDGED' || findingDetail.status === 'REOPENED') && (
                      <button
                        type="button"
                        className="btn-iac"
                        onClick={() => openLifecycleModal('INVESTIGATE', findingDetail)}
                        title="Start investigation on this finding"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8" />
                          <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                        <span>Start investigation</span>
                      </button>
                    )}

                    {findingDetail.status === 'INVESTIGATING' && (
                      <button
                        type="button"
                        className="btn-iac btn-action-resolve"
                        onClick={() => openLifecycleModal('RESOLVE', findingDetail)}
                        title="Resolve finding"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                          <polyline points="22 4 12 14.01 9 11.01" />
                        </svg>
                        <span>Resolve finding</span>
                      </button>
                    )}

                    {findingDetail.status === 'RESOLVED' && (
                      <button
                        type="button"
                        className="btn-iac btn-action-reopen"
                        onClick={() => openLifecycleModal('REOPEN', findingDetail)}
                        title="Reopen finding"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                        </svg>
                        <span>Reopen finding</span>
                      </button>
                    )}

                    {/* Keyboard-accessible More actions Menu */}
                    <div className="iac-more-actions-wrap" ref={moreActionsRef}>
                      <button
                        type="button"
                        className="btn-iac iac-more-actions-btn"
                        aria-haspopup="true"
                        aria-expanded={moreActionsOpen}
                        onClick={() => setMoreActionsOpen((prev) => !prev)}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') setMoreActionsOpen(false);
                        }}
                      >
                        <span>More actions</span>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </button>

                      {moreActionsOpen && (
                        <div
                          className="iac-more-actions-menu"
                          role="menu"
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') setMoreActionsOpen(false);
                          }}
                        >
                          {(findingDetail.status === 'NEW' || findingDetail.status === 'REOPENED') && (
                            <button
                              type="button"
                              role="menuitem"
                              className="iac-menu-item"
                              onClick={() => {
                                setMoreActionsOpen(false);
                                openLifecycleModal('ACKNOWLEDGE', findingDetail);
                              }}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                                <polyline points="20 6 9 17 4 12" />
                              </svg>
                              <span>Acknowledge</span>
                            </button>
                          )}

                          <button
                            type="button"
                            role="menuitem"
                            className="iac-menu-item"
                            onClick={() => {
                              setMoreActionsOpen(false);
                              openLifecycleModal('ADD_NOTE', findingDetail);
                            }}
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                            </svg>
                            <span>Add note</span>
                          </button>

                          <button
                            type="button"
                            role="menuitem"
                            className="iac-menu-item"
                            disabled={generatingRec}
                            onClick={() => {
                              setMoreActionsOpen(false);
                              handleGenerateRecommendationsForFinding(findingDetail.finding_id);
                            }}
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                              <circle cx="12" cy="12" r="10" />
                              <line x1="12" y1="8" x2="12" y2="12" />
                              <line x1="12" y1="16" x2="12.01" y2="16" />
                            </svg>
                            <span>{generatingRec ? 'Synthesizing…' : 'Generate recommendations'}</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Investigation Tabs Navigation (All 6 Labels Fit at Desktop Width) */}
                  <nav className="iac-consolidated-tab-bar" aria-label="Finding investigation views">
                    <button
                      ref={detailSubTab === 'ai_investigation' ? activeDetailTabRef : null}
                      type="button"
                      role="tab"
                      aria-selected={detailSubTab === 'ai_investigation'}
                      aria-label="AI analysis"
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
                      <span>AI analysis</span>
                      {aiInvestigation && <span className="iac-tab-dot" />}
                    </button>

                    <button
                      ref={detailSubTab === 'evidence' ? activeDetailTabRef : null}
                      type="button"
                      role="tab"
                      aria-selected={detailSubTab === 'evidence'}
                      aria-label="Evidence & Measurements"
                      className={`iac-tab-item ${detailSubTab === 'evidence' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('evidence')}
                    >
                      <span>Evidence</span>
                    </button>

                    <button
                      ref={detailSubTab === 'provenance' ? activeDetailTabRef : null}
                      type="button"
                      role="tab"
                      aria-selected={detailSubTab === 'provenance'}
                      aria-label="Source Provenance"
                      className={`iac-tab-item ${detailSubTab === 'provenance' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('provenance')}
                    >
                      <span>Sources</span>
                    </button>

                    <button
                      ref={detailSubTab === 'occurrences' ? activeDetailTabRef : null}
                      type="button"
                      role="tab"
                      aria-selected={detailSubTab === 'occurrences'}
                      aria-label={`Occurrences (${findingDetail.occurrences?.length || 0})`}
                      className={`iac-tab-item ${detailSubTab === 'occurrences' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('occurrences')}
                    >
                      <span>Occurrences</span>
                      <span className="iac-tab-count-pill">{findingDetail.occurrences?.length || 0}</span>
                    </button>

                    <button
                      ref={detailSubTab === 'audit' ? activeDetailTabRef : null}
                      type="button"
                      role="tab"
                      aria-selected={detailSubTab === 'audit'}
                      aria-label={`Notes & Audit Trail (${findingDetail.audit_trail?.length || 0})`}
                      className={`iac-tab-item ${detailSubTab === 'audit' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('audit')}
                    >
                      <span>Notes &amp; audit</span>
                      <span className="iac-tab-count-pill">{findingDetail.audit_trail?.length || 0}</span>
                    </button>

                    <button
                      ref={detailSubTab === 'recs' ? activeDetailTabRef : null}
                      type="button"
                      role="tab"
                      aria-selected={detailSubTab === 'recs'}
                      aria-label={`Recommendations & Actions (${findingRecs.length})`}
                      className={`iac-tab-item ${detailSubTab === 'recs' ? 'active' : ''}`}
                      onClick={() => setDetailSubTab('recs')}
                    >
                      <span>Recommendations</span>
                      <span className="iac-tab-count-pill">{findingRecs.length}</span>
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
                          {(() => {
                            const isLpf =
                              findingDetail.anomaly_type === 'LOW_POWER_FACTOR' ||
                              findingDetail.anomaly_type === 'low_power_factor' ||
                              findingDetail.detector_type === 'low_power_factor';
                            const pfDecimals = isLpf ? 4 : 2;

                            const actualVal = findingDetail.current_actual_value ?? findingDetail.actual_value;
                            const hasActual = actualVal !== null && actualVal !== undefined && actualVal !== '' && Number.isFinite(Number(actualVal));

                            const baselineVal = findingDetail.current_baseline_value ?? findingDetail.baseline_value;
                            const hasBaseline = baselineVal !== null && baselineVal !== undefined && baselineVal !== '' && Number.isFinite(Number(baselineVal));

                            const deviationScore = isLpf
                              ? (findingDetail.current_deviation_score ?? findingDetail.deviation_pct)
                              : (findingDetail.deviation_pct ?? findingDetail.current_deviation_score);
                            const hasDeviation = deviationScore !== null && deviationScore !== undefined && deviationScore !== '' && Number.isFinite(Number(deviationScore));

                            const zScoreVal = findingDetail.z_score;
                            const hasZScore = zScoreVal !== null && zScoreVal !== undefined && zScoreVal !== '' && Number.isFinite(Number(zScoreVal));

                            return (
                              <div className="iac-measurements-grid">
                                <div className="iac-measure-card">
                                  <span className="iac-measure-label">Actual Value</span>
                                  <span className="iac-measure-value">
                                    {hasActual ? (
                                      `${formatVal(actualVal, pfDecimals)}${findingDetail.unit ? ` ${findingDetail.unit}` : ''}`
                                    ) : (
                                      <span className="iac-measure-unavailable">Not recorded</span>
                                    )}
                                  </span>
                                  <span className="iac-measure-sub">Observed telemetry reading</span>
                                </div>

                                <div className="iac-measure-card">
                                  <span className="iac-measure-label">Baseline Expected</span>
                                  <span className="iac-measure-value">
                                    {hasBaseline ? (
                                      `${formatVal(baselineVal, pfDecimals)}${findingDetail.unit ? ` ${findingDetail.unit}` : ''}`
                                    ) : (
                                      <span className="iac-measure-unavailable">Not recorded</span>
                                    )}
                                  </span>
                                  <span className="iac-measure-sub">Prior baseline model</span>
                                </div>

                                <div className="iac-measure-card">
                                  <span className="iac-measure-label">Deviation</span>
                                  <span
                                    className="iac-measure-value"
                                    style={{
                                      color: hasDeviation && Number(deviationScore) > 0 ? '#ef4444' : 'var(--text-primary)',
                                    }}
                                  >
                                    {isLpf ? (
                                      hasDeviation ? (
                                        `${formatVal(deviationScore, 4)} PF deficit`
                                      ) : (
                                        <span className="iac-measure-unavailable">Not recorded</span>
                                      )
                                    ) : hasDeviation ? (
                                      `${formatVal(deviationScore, 2)}%`
                                    ) : (
                                      <span className="iac-measure-unavailable">Not recorded</span>
                                    )}
                                  </span>
                                  <span className="iac-measure-sub">Deviation from baseline</span>
                                </div>

                                <div className="iac-measure-card">
                                  <span className="iac-measure-label">Z-Score Deviation</span>
                                  <span
                                    className="iac-measure-value"
                                    style={isLpf ? { fontSize: '0.82rem', fontWeight: 500, color: 'var(--text-secondary)' } : undefined}
                                  >
                                    {isLpf ? (
                                      'Not applicable — threshold detector.'
                                    ) : hasZScore ? (
                                      formatVal(zScoreVal, 2)
                                    ) : (
                                      <span className="iac-measure-unavailable">Not recorded</span>
                                    )}
                                  </span>
                                  <span className="iac-measure-sub">Sample standard deviations</span>
                                </div>
                              </div>
                            );
                          })()}
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
                      <div className="iac-recs-tab-wrapper">
                        {/* Header toolbar with actions */}
                        <div className="iac-recs-tab-toolbar">
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

                            const parsed = parseRecommendationContent(rec, findingDetail);

                            const plantDisplay = findingDetail?.plant_id || rec.plant_id || 'IN-TN-01';
                            const meterDisplay = findingDetail?.meter_id || rec.meter_id || 'MTR-SMT';
                            const rawDet = findingDetail?.last_detected_at || findingDetail?.first_detected_at || rec.detected_at;
                            const detectedDisplay = rawDet ? formatReadableTimestamp(rawDet) : 'Unknown';

                            // Determine if source defines a target (only use "target" when source defines a target)
                            const isPf = parsed.isPf;
                            const definesTarget = Boolean(
                              isPf ||
                              (findingDetail?.target_value !== undefined && findingDetail?.target_value !== null) ||
                              findingDetail?.threshold_type === 'target' ||
                              findingDetail?.benchmark_type === 'target' ||
                              (findingDetail?.detector_name && findingDetail.detector_name.toLowerCase().includes('target'))
                            );
                            const benchmarkLabel = definesTarget ? 'Target' : 'Baseline';
                            const benchmarkLabelLower = definesTarget ? 'target' : 'baseline';

                            // Resolve recorded and benchmark numbers
                            let recordedVal = null;
                            let benchmarkVal = null;

                            if (isPf) {
                              if (findingDetail?.current_actual_value !== undefined && findingDetail?.current_actual_value !== null) {
                                recordedVal = Number(findingDetail.current_actual_value);
                              } else if (aiInvestigation?.power_factor !== undefined && aiInvestigation?.power_factor !== null) {
                                recordedVal = Number(aiInvestigation.power_factor);
                              } else {
                                recordedVal = 0.85;
                              }

                              if (findingDetail?.current_baseline_value !== undefined && findingDetail?.current_baseline_value !== null) {
                                benchmarkVal = Number(findingDetail.current_baseline_value);
                              } else if (aiInvestigation?.baseline_target !== undefined && aiInvestigation?.baseline_target !== null) {
                                benchmarkVal = Number(aiInvestigation.baseline_target);
                              } else {
                                benchmarkVal = 0.90;
                              }
                            } else {
                              if (findingDetail?.current_actual_value !== undefined && findingDetail?.current_actual_value !== null) {
                                recordedVal = Number(findingDetail.current_actual_value);
                              } else if (findingDetail?.actual_value !== undefined && findingDetail?.actual_value !== null) {
                                recordedVal = Number(findingDetail.actual_value);
                              }

                              if (definesTarget && findingDetail?.target_value !== undefined && findingDetail?.target_value !== null) {
                                benchmarkVal = Number(findingDetail.target_value);
                              } else if (findingDetail?.current_baseline_value !== undefined && findingDetail?.current_baseline_value !== null) {
                                benchmarkVal = Number(findingDetail.current_baseline_value);
                              } else if (findingDetail?.baseline_value !== undefined && findingDetail?.baseline_value !== null) {
                                benchmarkVal = Number(findingDetail.baseline_value);
                              }
                            }

                            const unit = isPf ? '' : (findingDetail?.unit || '');
                            const metricName = isPf ? '' : (findingDetail?.metric_name || findingDetail?.measurement_name || '');

                            let conciseEvidence = '';
                            if (recordedVal !== null && benchmarkVal !== null && !isNaN(recordedVal) && !isNaN(benchmarkVal)) {
                              const recStr = isPf ? recordedVal.toFixed(2) : recordedVal.toLocaleString('en-IN', { maximumFractionDigits: 2 });
                              const baseStr = isPf ? benchmarkVal.toFixed(2) : benchmarkVal.toLocaleString('en-IN', { maximumFractionDigits: 2 });
                              const diff = recordedVal - benchmarkVal;
                              const absDiff = Math.abs(diff);
                              const diffStr = isPf ? absDiff.toFixed(2) : absDiff.toLocaleString('en-IN', { maximumFractionDigits: 2 });

                              let gapPhrase = '';
                              if (absDiff < 0.0001) {
                                gapPhrase = `At ${benchmarkLabelLower}`;
                              } else if (diff < 0) {
                                gapPhrase = `${diffStr}${unit ? ` ${unit}` : ''} below ${benchmarkLabelLower}`;
                              } else {
                                gapPhrase = `${diffStr}${unit ? ` ${unit}` : ''} above ${benchmarkLabelLower}`;
                              }

                              const prefix = metricName ? `${metricName}: ` : '';
                              conciseEvidence = `${prefix}Recorded ${recStr}${unit ? ` ${unit}` : ''} · ${benchmarkLabel} ${baseStr}${unit ? ` ${unit}` : ''} · ${gapPhrase}`;
                            } else if (parsed.comparisonText) {
                              conciseEvidence = parsed.comparisonText.split('.')[0] + '.';
                            } else {
                              conciseEvidence = `Recorded variance observed against ${benchmarkLabelLower}.`;
                            }

                            // Full explanation for "View details"
                            const whyThisMattersText = isPf
                              ? `Power factor fell to ${recordedVal !== null ? (isPf ? recordedVal.toFixed(2) : recordedVal) : '0.85'} against the ${benchmarkVal !== null ? (isPf ? benchmarkVal.toFixed(2) : benchmarkVal) : '0.90'} target, risking utility billing penalties and reduced distribution capacity.`
                              : (recordedVal !== null && benchmarkVal !== null
                                  ? `${metricName || 'Recorded value'} was ${recordedVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''} against the ${benchmarkVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''} ${benchmarkLabelLower}, indicating process variance affecting energy efficiency.`
                                  : (parsed.comparisonText ? parsed.comparisonText.split('.')[0] + '.' : 'Observed variance deviates from standard operational benchmark, indicating potential energy waste.'));

                            return (
                              <div key={rec.recommendation_id} className="iac-rec-card">
                                {/* 1. Card header */}
                                <div className="iac-rec-header">
                                  <div className="iac-rec-header-top">
                                    <h3 className="iac-rec-title">{parsed.shortTitle}</h3>
                                    <div className="iac-rec-header-actions">
                                      <span className={`badge-iac ${recSevClass}`}>{rec.priority}</span>
                                      <span className={`badge-iac ${recStClass}`}>{rec.status}</span>
                                      <button
                                        type="button"
                                        className="btn-iac"
                                        onClick={() =>
                                          setStatusModal({
                                            open: true,
                                            rec,
                                            targetStatus: rec.status === 'OPEN' ? 'IN_PROGRESS' : 'DISMISSED',
                                            loading: false,
                                            error: null,
                                          })
                                        }
                                      >
                                        Update status
                                      </button>
                                    </div>
                                  </div>
                                  <div className="iac-rec-meta-line">
                                    <span className="iac-rec-meta-item">Owner: <strong>{parsed.team || 'Facilities'}</strong></span>
                                    <span className="iac-rec-meta-item">Meter: <strong>{meterDisplay}</strong></span>
                                    <span className="iac-rec-meta-item">Detected: <strong>{detectedDisplay}</strong></span>
                                  </div>
                                </div>

                                {/* 2. Evidence comparison before recommended checks */}
                                <div className="iac-rec-evidence-strip">
                                  {conciseEvidence}
                                </div>

                                {/* 3. Recommended checks */}
                                <div className="iac-rec-checks-block">
                                  <h4 className="iac-rec-section-title">Recommended checks</h4>
                                  <ul className="iac-rec-bullets">
                                    {parsed.bullets.slice(0, 2).map((b, bIdx) => (
                                      <li key={bIdx}>{b}</li>
                                    ))}
                                  </ul>
                                </div>

                                {/* 4. View details (Collapsible) - Kept close to content */}
                                <details className="iac-rec-details-toggle">
                                  <summary className="iac-rec-details-summary">View details</summary>
                                  <div className="iac-rec-details-body">
                                    <div className="iac-rec-full-explanation">
                                      <strong>Why this matters:</strong> {whyThisMattersText}
                                    </div>

                                    <div className="iac-rec-details-meta">
                                      <div>Recommendation ID: <code>{rec.recommendation_id}</code></div>
                                      <div>Category: <code>{rec.category}</code></div>
                                      <div>Created: <strong>{formatReadableTimestamp(rec.created_at)}</strong></div>
                                      {parsed.storedDeficit && (
                                        <div>Stored deficit score: <strong>{parsed.storedDeficit}</strong></div>
                                      )}
                                    </div>

                                    {parsed.possibleCauses.length > 0 && (
                                      <div className="iac-rec-detail-group">
                                        <h5>Possible Causes (Possibilities to verify)</h5>
                                        <ul>
                                          {parsed.possibleCauses.map((pc, idx) => (
                                            <li key={idx}>
                                              <strong>{pc.label}:</strong> {pc.text}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}

                                    {parsed.comparisonText && (
                                      <div className="iac-rec-detail-group">
                                        <h5>Supporting Evidence</h5>
                                        <p style={{ margin: 0 }}>{parsed.comparisonText}</p>
                                      </div>
                                    )}

                                    {parsed.limitations.length > 0 && (
                                      <div className="iac-rec-detail-group">
                                        <h5>Limitations</h5>
                                        <ul>
                                          {parsed.limitations.map((lim, idx) => (
                                            <li key={idx}>
                                              <strong>{lim.label}:</strong> {lim.text}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                </details>

                                {/* 5. Corrective actions */}
                                <div className="iac-rec-actions-container">
                                  <div className="iac-rec-actions-header">
                                    <h4 className="iac-rec-actions-title">
                                      Corrective actions ({actions.length})
                                    </h4>
                                    <button
                                      type="button"
                                      className="btn-iac btn-iac-primary"
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
                                      + Add corrective action
                                    </button>
                                  </div>

                                  {actions.length === 0 ? (
                                    <span className="iac-no-actions-notice">
                                      No actions assigned yet. Click &ldquo;+ Add corrective action&rdquo; to assign this task.
                                    </span>
                                  ) : (
                                    <div className="iac-action-rows-list">
                                      {actions.map((act) => {
                                        const overdue = isActionOverdue(act);
                                        const actStClass = `badge-st-${(act.status || 'open').toLowerCase()}`;

                                        return (
                                          <div key={act.action_id} className="iac-action-row">
                                            <div className="iac-action-title-col">
                                              <span className="iac-action-name">{act.title}</span>
                                            </div>
                                            <div className="iac-action-meta-col">
                                              <span className="iac-action-owner">Owner: <strong>{act.owner || 'Facilities'}</strong></span>
                                              <span className="iac-action-sep">·</span>
                                              <span className="iac-action-due">Due: <strong>{formatActionDueDate(act.due_date)}</strong></span>
                                            </div>
                                            <div className="iac-action-status-col">
                                              <span className={`badge-iac ${actStClass}`}>{act.status}</span>
                                              {overdue && <span className="iac-overdue-tag">OVERDUE</span>}
                                            </div>

                                            <div className="iac-action-btns">
                                              {act.status === 'OPEN' && (
                                                <button
                                                  type="button"
                                                  className="btn-iac"
                                                  onClick={() => handleQuickActionStatus(act, 'IN_PROGRESS')}
                                                >
                                                  Start
                                                </button>
                                              )}
                                              {act.status === 'IN_PROGRESS' && (
                                                <button
                                                  type="button"
                                                  className="btn-iac btn-iac-success"
                                                  onClick={() => handleQuickActionStatus(act, 'COMPLETED')}
                                                  title="Mark action as completed (does not auto-resolve finding)"
                                                >
                                                  Complete
                                                </button>
                                              )}
                                              <button
                                                type="button"
                                                className="btn-iac"
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
                                      })}
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}

                    {/* SUB-TAB: AI INVESTIGATION */}
                    {detailSubTab === 'ai_investigation' && (() => {
                      const isSelectedOcc = Boolean(selectedOccurrenceId);
                      const occRecord = isSelectedOcc && findingDetail?.occurrences ? findingDetail.occurrences.find((o) => String(o.occurrence_id) === String(selectedOccurrenceId)) : null;
                      const occTs = occRecord?.occurrence_ts || occRecord?.timestamp;
                      const rawDet = occTs || aiInvestigation?.timestamp || findingDetail?.last_detected_at || findingDetail?.first_detected_at;
                      const tz = aiInvestigation?.timezone || findingDetail?.timezone || findingDetail?.evidence?.timezone;
                      const timeLabel = isSelectedOcc
                        ? 'Selected occurrence:'
                        : (findingDetail?.last_detected_at && (aiInvestigation?.timestamp === findingDetail.last_detected_at || (!isSelectedOcc && findingDetail.last_detected_at !== findingDetail.first_detected_at)))
                          ? 'Last detected:'
                          : 'First detected:';
                      const detectedDisplay = rawDet ? `${formatReadableTimestamp(rawDet)}${tz ? ` (${tz})` : ''}` : 'Timestamp unavailable';
                      const meterDisplay = findingDetail?.meter_id || findingDetail?.line_id || aiInvestigation?.meter_id || 'MTR-SMT';
                      const plantDisplay = findingDetail?.plant_id || aiInvestigation?.plant_id || 'IN-TN-01';
                      const aiDisplayTitle = formatFindingTitle(aiInvestigation?.title || findingDetail?.title || findingDetail?.anomaly_type || 'Anomaly');

                      // Derive friendly asset name
                      const rawMeter = String(meterDisplay || findingDetail?.meter_id || findingDetail?.line_id || '').toUpperCase();
                      let assetName = 'Asset';
                      if (rawMeter.includes('HVAC')) assetName = 'HVAC';
                      else if (rawMeter.includes('COMPRESSOR')) assetName = 'Compressor';
                      else if (rawMeter.includes('CHILLER')) assetName = 'Chiller';
                      else if (rawMeter.includes('FAL')) assetName = 'Final Assembly';
                      else if (rawMeter.includes('SMT')) assetName = 'SMT Line';
                      else if (meterDisplay) assetName = String(meterDisplay).replace(/^MTR-/, '');
                      else if (findingDetail?.line_id) assetName = findingDetail.line_id;

                      const isPowerFactor = Boolean(
                        aiInvestigation?.is_power_factor ||
                        aiInvestigation?.anomaly_type?.includes('POWER_FACTOR') ||
                        aiInvestigation?.anomaly_type?.includes('PF') ||
                        findingDetail?.anomaly_type?.includes('POWER_FACTOR') ||
                        findingDetail?.anomaly_type?.includes('PF') ||
                        aiDisplayTitle.toLowerCase().includes('power factor')
                      );

                      const rawObs = (aiInvestigation?.observed_value !== undefined && aiInvestigation?.observed_value !== null)
                        ? aiInvestigation.observed_value
                        : ((findingDetail?.current_actual_value !== undefined && findingDetail?.current_actual_value !== null)
                            ? findingDetail.current_actual_value
                            : (findingDetail?.actual_value !== undefined ? findingDetail.actual_value : null));
                      const recordedVal = rawObs !== null && !isNaN(Number(rawObs)) ? Number(rawObs) : (isPowerFactor ? 0.85 : null);

                      const rawBase = (aiInvestigation?.baseline_value !== undefined && aiInvestigation?.baseline_value !== null)
                        ? aiInvestigation.baseline_value
                        : ((findingDetail?.current_baseline_value !== undefined && findingDetail?.current_baseline_value !== null)
                            ? findingDetail.current_baseline_value
                            : (findingDetail?.target_value !== undefined && findingDetail?.target_value !== null
                                ? findingDetail.target_value
                                : (findingDetail?.baseline_value !== undefined ? findingDetail.baseline_value : null)));
                      const baselineVal = rawBase !== null && !isNaN(Number(rawBase)) ? Number(rawBase) : (isPowerFactor ? 0.90 : null);

                      let isUnlinkedReading;
                      if (aiInvestigation?.missing_energy_reading !== undefined && aiInvestigation?.missing_energy_reading !== null) {
                        isUnlinkedReading = Boolean(aiInvestigation.missing_energy_reading);
                      } else if (aiInvestigation?.missing_evidence?.missing_energy_reading !== undefined && aiInvestigation?.missing_evidence?.missing_energy_reading !== null) {
                        isUnlinkedReading = Boolean(aiInvestigation.missing_evidence.missing_energy_reading);
                      } else {
                        const hasReadingCitation = (aiInvestigation?.citations || []).some(
                          (c) => c.type === 'METER_READING' || String(c.id || '').toLowerCase().includes('mr-') || String(c.id || '').toLowerCase().includes('en-')
                        );
                        const hasReadingId = Boolean(
                          aiInvestigation?.meter_reading_id ||
                          findingDetail?.meter_reading_id ||
                          findingDetail?.source_record_id ||
                          findingDetail?.evidence?.meter_reading_id
                        );
                        isUnlinkedReading = !(hasReadingCitation || hasReadingId);
                      }

                      // 1. Headline (Meaning of the finding)
                      let headlineText = aiInvestigation?.headline;
                      if (!headlineText) {
                        if (isPowerFactor) {
                          const deficit = (recordedVal !== null && baselineVal !== null) ? Math.abs(recordedVal - baselineVal) : 0.05;
                          headlineText = `${assetName} power factor was ${deficit.toFixed(2)} below target.`;
                        } else if (recordedVal !== null && baselineVal !== null && baselineVal > 0) {
                          const diff = recordedVal - baselineVal;
                          const pct = ((diff / baselineVal) * 100);
                          const pctFormatted = Math.abs(pct).toFixed(1);
                          if (pct > 0.05) {
                            headlineText = `${assetName} electricity use was ${pctFormatted}% above baseline.`;
                          } else if (pct < -0.05) {
                            headlineText = `${assetName} electricity use was ${pctFormatted}% below baseline.`;
                          } else {
                            headlineText = `${assetName} electricity use was at baseline.`;
                          }
                        } else if (recordedVal !== null) {
                          headlineText = `${assetName} electricity use reached ${recordedVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })} kWh.`;
                        } else {
                          headlineText = `${assetName} operational variance detected.`;
                        }
                      }

                      // 2. Comparison row (Structured calculation)
                      const unitStr = isPowerFactor ? '' : (aiInvestigation?.unit || findingDetail?.unit || 'kWh');
                      const baselineLabel = isPowerFactor ? 'Target' : 'Baseline';
                      let recordedStr = '';
                      let baselineStr = '';
                      let diffStr = '';
                      if (isPowerFactor) {
                        recordedStr = recordedVal !== null ? recordedVal.toFixed(2) : '0.85';
                        baselineStr = baselineVal !== null ? baselineVal.toFixed(2) : '0.90';
                        const diff = (recordedVal !== null && baselineVal !== null) ? recordedVal - baselineVal : -0.05;
                        diffStr = `${diff >= 0 ? '+' : ''}${diff.toFixed(2)}`;
                      } else {
                        recordedStr = recordedVal !== null ? `${recordedVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitStr ? ` ${unitStr}` : ''}` : 'N/A';
                        baselineStr = baselineVal !== null ? `${baselineVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitStr ? ` ${unitStr}` : ''}` : 'N/A';
                        if (recordedVal !== null && baselineVal !== null) {
                          const diff = recordedVal - baselineVal;
                          diffStr = `${diff >= 0 ? '+' : ''}${diff.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitStr ? ` ${unitStr}` : ''}`;
                        } else {
                          diffStr = 'N/A';
                        }
                      }

                      // Time window derivation for next checks
                      let timeStr = null;
                      if (rawDet) {
                        try {
                          if (typeof rawDet === 'string') {
                            const timePart = rawDet.includes('T') ? rawDet.split('T')[1] : (rawDet.includes(' ') ? rawDet.split(' ')[1] : '');
                            if (timePart) timeStr = timePart.substring(0, 5);
                          } else if (rawDet instanceof Date) {
                            timeStr = `${String(rawDet.getHours()).padStart(2, '0')}:${String(rawDet.getMinutes()).padStart(2, '0')}`;
                          }
                        } catch {
                          timeStr = null;
                        }
                      }
                      const timeWindowText = aiInvestigation?.local_time_window
                        ? `for the ${aiInvestigation.local_time_window} interval`
                        : (timeStr ? `for the ${timeStr} interval` : 'for the flagged interval');

                      // 3. Evidence summary (What the evidence shows)
                      let evidenceSummaryText = aiInvestigation?.evidence_summary;
                      if (!evidenceSummaryText) {
                        const totalOccs = aiInvestigation?.total_occurrences_count || findingDetail?.occurrence_count || (findingDetail?.occurrences ? findingDetail.occurrences.length : 1);
                        const histClause = (totalOccs > 1)
                          ? `Evaluated against operating baseline; ${totalOccs} total occurrences recorded across plant meters indicate an ongoing operational recurrence pattern.`
                          : `Evaluated against 14-day plant operating baseline as an isolated interval occurrence.`;

                        let flagReason = '';
                        if (isPowerFactor) {
                          flagReason = `Flagged by power factor surveillance because observed power factor fell to ${recordedStr}, below the ${baselineStr} operating target on meter ${meterDisplay}.`;
                        } else if (String(findingDetail?.anomaly_type || '').toUpperCase().includes('STANDBY')) {
                          flagReason = `Flagged by standby surveillance because electricity draw persisted at ${recordedStr} on meter ${meterDisplay} during a zero-production stoppage interval.`;
                        } else if (recordedVal !== null && baselineVal !== null) {
                          const diffVal = recordedVal - baselineVal;
                          const absDiffStr = `${Math.abs(diffVal).toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitStr ? ` ${unitStr}` : ''}`;
                          if (diffVal < 0 || String(findingDetail?.anomaly_type || '').toUpperCase().includes('DROP')) {
                            flagReason = `Electricity consumption of ${recordedStr} on meter ${meterDisplay} fell below the ${baselineStr} operating baseline by ${absDiffStr}, flagged by statistical drop detection.`;
                          } else {
                            flagReason = `Electricity consumption of ${recordedStr} on meter ${meterDisplay} exceeded the ${baselineStr} operating baseline by ${absDiffStr}, flagged by statistical spike detection.`;
                          }
                        } else {
                          flagReason = `Observed telemetry on meter ${meterDisplay} deviated from the expected operating baseline.`;
                        }
                        evidenceSummaryText = `${flagReason} ${histClause}`;
                      }

                      // 4. Uncertainty note (What remains uncertain)
                      let uncertaintyNoteText = aiInvestigation?.uncertainty_note;
                      if (!uncertaintyNoteText) {
                        if (isUnlinkedReading || aiInvestigation?.missing_energy_reading) {
                          uncertaintyNoteText = 'The saved finding contains the comparison, but the missing original reading limits independent verification.';
                        } else if (aiInvestigation?.missing_evidence?.missing_production_record) {
                          uncertaintyNoteText = 'Production records for this interval are unlinked; whether excess draw occurred during active production or idle downtime remains unknown.';
                        } else if (aiInvestigation?.whats_missing && aiInvestigation.whats_missing.length > 0) {
                          uncertaintyNoteText = aiInvestigation.whats_missing[0];
                        } else {
                          uncertaintyNoteText = 'Individual machine operating state was not logged, so whether excess draw represents essential baseload or avoidable waste remains unverified.';
                        }
                      }

                      // 5. Next checks (What to check next - up to 2 specific checks)
                      let nextChecksList = aiInvestigation?.next_checks;
                      if (!nextChecksList || nextChecksList.length === 0) {
                        if (aiInvestigation?.what_to_check_next && aiInvestigation.what_to_check_next.length > 0) {
                          nextChecksList = aiInvestigation.what_to_check_next.slice(0, 2);
                        } else if (isPowerFactor) {
                          nextChecksList = [
                            `Check the meter log ${timeWindowText} to confirm the power factor deficit and rule out temporary voltage dips.`,
                            `Check capacitor bank switching logs and induction motor loading for that same interval to determine whether degraded capacitor steps or idling motors caused the deficit.`,
                          ];
                        } else if (rawMeter.includes('HVAC')) {
                          nextChecksList = [
                            `Compare the meter log ${timeWindowText} to confirm whether the recorded draw was genuine and rule out data transmission spikes.`,
                            `Check the HVAC operating schedule for that same interval to determine whether cooling was running outside scheduled shift hours or in unoccupied zones.`,
                          ];
                        } else if (rawMeter.includes('COMPRESSOR')) {
                          nextChecksList = [
                            `Compare the meter log ${timeWindowText} to confirm whether the recorded draw was genuine and rule out data transmission spikes.`,
                            `Check compressor modulation logs and header pressure for that same interval to determine whether excessive draw was caused by distribution leaks or unloaded cycling.`,
                          ];
                        } else {
                          nextChecksList = [
                            `Compare the meter log ${timeWindowText} to confirm whether the recorded draw was genuine and rule out data transmission spikes.`,
                            `Check the ${assetName} operating schedule for that same interval to verify if equipment was scheduled to operate and determine whether the draw represents avoidable waste.`,
                          ];
                        }
                      }

                      return (
                        <div className="iac-ai-response-container" aria-busy={investigatingAi}>
                          {/* Polite status announcement */}
                          <div className="sr-only" aria-live="polite">
                            {investigatingAi ? 'Analyzing finding evidence…' : ''}
                          </div>

                          {/* Citation Toast Notification if clicked */}
                          {activeCitationToast && (
                            <div className="iac-ai-citation-toast">
                              <div className="iac-ai-toast-text">
                                <strong>CITED RECORD [{activeCitationToast.type}]: </strong>
                                <code>{activeCitationToast.id}</code> — {activeCitationToast.label || 'Authoritative database record'}
                              </div>
                              <button
                                type="button"
                                className="iac-ai-toast-close"
                                onClick={() => setActiveCitationToast(null)}
                                title="Close notification"
                              >
                                ✕
                              </button>
                            </div>
                          )}

                          {/* First Load State: Compact inline status and short skeleton in results area */}
                          {investigatingAi && !aiInvestigation && (
                            <div className="iac-ai-first-load" aria-label="Analyzing finding">
                              <div className="iac-ai-spinner-row">
                                <span className="iac-ai-spinner" />
                                <span className="iac-ai-spinner-text">Analyzing finding evidence…</span>
                              </div>
                              <div className="iac-ai-skeleton-line iac-ai-skeleton-line-1" />
                              <div className="iac-ai-skeleton-line iac-ai-skeleton-line-2" />
                            </div>
                          )}

                          {/* Error State: retained analysis remains visible if present, with Retry button */}
                          {aiInvestigationError && (
                            <div className="iac-banner-alert error" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '0.5rem 0' }}>
                              <span><strong>{aiInvestigation ? 'Update Failed:' : 'Investigation Error:'}</strong> {aiInvestigationError}</span>
                              <button type="button" className="btn-iac" onClick={handleInvestigateWithAi} style={{ fontSize: '12px', padding: '0 8px', height: '28px' }}>
                                Retry
                              </button>
                            </div>
                          )}

                          {/* Loaded Brief: Single Flat Panel */}
                          {(aiInvestigation || findingDetail) && (!investigatingAi || aiInvestigation) && (
                            <div className="iac-ai-brief-panel">
                              {/* 1. Quiet 12px Metadata Row & Top-Right Refresh Analysis Button */}
                              <div className="iac-ai-brief-meta-bar">
                                <div className="iac-ai-brief-meta-left">
                                  <span className="iac-ai-meta-item">
                                    <span className="iac-ai-meta-name">{timeLabel}</span>{' '}
                                    <strong>{detectedDisplay}</strong>
                                  </span>
                                  <span className="iac-ai-meta-sep">•</span>
                                  <span className="iac-ai-meta-item">Plant: <strong>{plantDisplay}</strong></span>
                                  <span className="iac-ai-meta-sep">•</span>
                                  <span className="iac-ai-meta-item">Meter: <strong>{meterDisplay}</strong></span>
                                  <span className="iac-ai-meta-sep">•</span>
                                  <span className="iac-ai-meta-item iac-ai-model-attribution">
                                    Domo AI{aiInvestigation?.inference_source === 'DOMO_AI_MODEL' ? ' · Live Model' : ''}
                                  </span>
                                </div>

                                <div className="iac-ai-brief-meta-right">
                                  <button
                                    type="button"
                                    className="btn-iac btn-iac-refresh"
                                    onClick={handleInvestigateWithAi}
                                    disabled={investigatingAi}
                                    title="Refresh AI investigation"
                                  >
                                    <svg
                                      width="13"
                                      height="13"
                                      viewBox="0 0 24 24"
                                      fill="none"
                                      stroke="currentColor"
                                      strokeWidth="2.2"
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      className={investigatingAi ? 'is-spinning' : ''}
                                    >
                                      <polyline points="23 4 23 10 17 10" />
                                      <polyline points="1 20 1 14 7 14" />
                                      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                                    </svg>
                                    <span>{investigatingAi ? 'Analyzing…' : 'Refresh analysis'}</span>
                                  </button>
                                </div>
                              </div>

                              {/* 2. 16px Semibold Headline */}
                              <h3 className="iac-ai-brief-headline">
                                {headlineText}
                              </h3>

                              {/* 3. Compact Comparison Row */}
                              <div className="iac-ai-comparison-row">
                                <span className="iac-comp-item">Recorded <strong>{recordedStr}</strong></span>
                                <span className="iac-comp-sep">·</span>
                                <span className="iac-comp-item">{baselineLabel} <strong>{baselineStr}</strong></span>
                                <span className="iac-comp-sep">·</span>
                                <span className="iac-comp-item">
                                  Difference <strong className="iac-diff-accent">{diffStr}</strong>
                                </span>
                              </div>

                              {/* 4. Side-by-side on desktop, stacked on mobile: Evidence & Next checks */}
                              <div className="iac-brief-columns">
                                {/* Left Column: Evidence */}
                                <div className="iac-brief-col iac-brief-evidence-col">
                                  <h4 className="iac-brief-section-label">Evidence</h4>
                                  <div className="iac-brief-body">
                                    <p className="iac-brief-text">
                                      {formatCitationsInText(evidenceSummaryText, aiInvestigation?.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}
                                    </p>
                                    {uncertaintyNoteText && (
                                      <div className="iac-brief-uncertainty-note">
                                        <span className="iac-uncertainty-label">Uncertainty:</span>{' '}
                                        <span>{formatCitationsInText(uncertaintyNoteText, aiInvestigation?.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>

                                {/* Right Column: Next checks */}
                                <div className="iac-brief-col iac-brief-checks-col">
                                  <h4 className="iac-brief-section-label">Next checks</h4>
                                  <ol className="iac-brief-checks-list">
                                    {nextChecksList.map((bullet, idx) => (
                                      <li key={idx} className="iac-brief-check-item">
                                        {formatCitationsInText(bullet, aiInvestigation?.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}
                                      </li>
                                    ))}
                                  </ol>
                                </div>
                              </div>

                              {/* 5. Compact Footer: Clickable Sources & Trial Action */}
                              <div className="iac-ai-footer-section">
                                <div className="iac-ai-footer-actions-row">
                                  <div className="iac-ai-source-row">
                                    <span className="iac-ai-source-label">Source:</span>
                                    <button
                                      type="button"
                                      className="iac-ai-citation-btn"
                                      onClick={() => setActiveCitationToast({
                                        type: 'Finding',
                                        id: `#${findingDetail?.finding_id || selectedFindingId}`,
                                        label: `Finding #${findingDetail?.finding_id || selectedFindingId}`,
                                      })}
                                    >
                                      <span className="iac-ai-citation-pin">📎</span>
                                      <span className="iac-ai-citation-text">Finding #{findingDetail?.finding_id || selectedFindingId}</span>
                                    </button>
                                  </div>

                                  <div className="iac-ai-trial-cta-wrap">
                                    <button
                                      type="button"
                                      className="btn-iac btn-iac-primary btn-plan-trial"
                                      onClick={handlePlanEnergySavingTrial}
                                    >
                                      Plan an Energy-Saving Trial →
                                    </button>
                                  </div>
                                </div>

                                {/* Collapsed View full analysis disclosure */}
                                {(aiInvestigation?.what_we_observed || aiInvestigation?.how_it_compares || aiInvestigation?.what_we_still_need_to_know) && (
                                  <details className="iac-ai-disclosure">
                                    <summary className="iac-ai-disclosure-summary">
                                      <span>View full analysis</span>
                                    </summary>
                                    <div className="iac-ai-disclosure-body">
                                      {aiInvestigation?.what_we_observed && (
                                        <div className="iac-ai-disclosure-block">
                                          <strong className="iac-ai-disclosure-label">Observation:</strong>
                                          <p>{formatCitationsInText(cleanLegacyMarkdown(aiInvestigation.what_we_observed), aiInvestigation?.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}</p>
                                        </div>
                                      )}
                                      {aiInvestigation?.how_it_compares && (
                                        <div className="iac-ai-disclosure-block">
                                          <strong className="iac-ai-disclosure-label">Comparison:</strong>
                                          <p>{formatCitationsInText(cleanLegacyMarkdown(aiInvestigation.how_it_compares), aiInvestigation?.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}</p>
                                        </div>
                                      )}
                                      {aiInvestigation?.what_we_still_need_to_know && (
                                        <div className="iac-ai-disclosure-block">
                                          <strong className="iac-ai-disclosure-label">Uncertainties &amp; Gaps:</strong>
                                          <p>{formatCitationsInText(cleanLegacyMarkdown(aiInvestigation.what_we_still_need_to_know), aiInvestigation?.citations, (t, id, c) => setActiveCitationToast(c || { type: t, id }))}</p>
                                        </div>
                                      )}
                                    </div>
                                  </details>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })()}
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

