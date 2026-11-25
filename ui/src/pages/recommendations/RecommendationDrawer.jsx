import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDateTime, formatNumber, formatFindingTitle } from '../../utils/formatters';
import { CompactProvenanceSummary } from '../findings/ProvenanceExplorer';

function formatDateClean(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const day = String(d.getDate()).padStart(2, '0');
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
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

function parseSavedDescription(desc) {
  if (!desc) return [];
  const sections = [];
  const rawSections = desc.split(/###\s+/).filter(Boolean);

  for (const raw of rawSections) {
    const lines = raw.split('\n');
    const heading = lines[0].trim();
    const body = lines.slice(1).join('\n').trim();

    const items = [];
    let plainText = '';

    const bulletLines = body.split('\n').filter((l) => l.trim().startsWith('-'));
    if (bulletLines.length > 0) {
      for (const bl of bulletLines) {
        const lineContent = bl.replace(/^-\s*/, '').trim();
        const tagMatch = lineContent.match(/^\[([A-Z_-]+)(?::\s*([^\]]+))?\]\s*(.*)$/i);
        if (tagMatch) {
          const isHypothesis = tagMatch[1].toUpperCase().includes('HYPOTHESIS');
          const tagLabel = tagMatch[2] || (isHypothesis ? 'Hypothesis' : 'Limitation');
          items.push({
            isHypothesis,
            tag: tagLabel,
            text: tagMatch[3] || lineContent,
          });
        } else {
          items.push({
            isHypothesis: false,
            tag: null,
            text: lineContent,
          });
        }
      }
    } else {
      plainText = body;
    }

    sections.push({
      heading,
      text: plainText,
      items,
    });
  }

  return sections;
}

function generateOverviewContent(rec) {
  const evidence = rec?.evidence_context || {};
  const finding = rec?.source_finding || {};
  const desc = rec?.description || '';

  const category = (rec?.category || '').toUpperCase();
  const title = (rec?.title || '').toLowerCase();
  const anomalyType = (finding?.anomaly_type || evidence?.source_anomaly_type || '').toUpperCase();
  const isPf =
    category.includes('POWER_FACTOR') ||
    title.includes('power factor') ||
    anomalyType.includes('POWER_FACTOR') ||
    anomalyType.includes('LOW_PF');

  // Stored deviation score (e.g. 0.15)
  let storedDeviationScore = null;
  if (evidence.current_deviation_score !== undefined && evidence.current_deviation_score !== null) {
    storedDeviationScore = Number(evidence.current_deviation_score);
  } else if (finding.current_deviation_score !== undefined && finding.current_deviation_score !== null) {
    storedDeviationScore = Number(finding.current_deviation_score);
  } else {
    const devMatch = desc.match(/deficit:\s*([0-9.]+)/i);
    if (devMatch) storedDeviationScore = Number(devMatch[1]);
  }

  // Actual & Baseline values
  let actualVal = null;
  if (evidence.current_actual_value !== undefined && evidence.current_actual_value !== null && evidence.current_actual_value !== '') {
    const n = Number(evidence.current_actual_value);
    if (!isNaN(n)) actualVal = n;
  } else if (finding.current_actual_value !== undefined && finding.current_actual_value !== null && finding.current_actual_value !== '') {
    const n = Number(finding.current_actual_value);
    if (!isNaN(n)) actualVal = n;
  }

  let baselineVal = null;
  if (evidence.current_baseline_value !== undefined && evidence.current_baseline_value !== null && evidence.current_baseline_value !== '') {
    const n = Number(evidence.current_baseline_value);
    if (!isNaN(n)) baselineVal = n;
  } else if (finding.current_baseline_value !== undefined && finding.current_baseline_value !== null && finding.current_baseline_value !== '') {
    const n = Number(finding.current_baseline_value);
    if (!isNaN(n)) baselineVal = n;
  } else if (isPf) {
    baselineVal = 0.90;
  }

  if (isPf && actualVal === null) {
    const pfMatch = desc.match(/measured power factor of\s*([0-9.]+)/i) || desc.match(/power factor was\s*([0-9.]+)/i);
    if (pfMatch) actualVal = Number(pfMatch[1]);
    else actualVal = 0.85;
  }

  // Build "What happened" sentence: keep power factor unitless, calculate gap only from comparable values
  let whatHappenedSentence = '';
  if (isPf) {
    const actStr = actualVal !== null ? actualVal.toFixed(2) : '0.85';
    const targetStr = baselineVal !== null ? baselineVal.toFixed(2) : '0.90';
    if (actualVal !== null && baselineVal !== null) {
      const diff = baselineVal - actualVal;
      if (diff > 0.0001) {
        whatHappenedSentence = `Power factor was ${actStr} against a target of ${targetStr} — ${diff.toFixed(2)} below target.`;
      } else if (diff < -0.0001) {
        whatHappenedSentence = `Power factor was ${actStr} against a target of ${targetStr} — ${Math.abs(diff).toFixed(2)} above target.`;
      } else {
        whatHappenedSentence = `Power factor was ${actStr} against a target of ${targetStr} — at target.`;
      }
    } else {
      whatHappenedSentence = `Power factor was ${actStr} against a target of ${targetStr}.`;
    }
  } else if (actualVal !== null && baselineVal !== null) {
    const unit = finding.unit || (category.includes('ENERGY') || category.includes('STANDBY') || category.includes('BASELOAD') ? 'kWh' : '');
    const unitSuffix = unit ? ` ${unit}` : '';
    const diff = actualVal - baselineVal;
    const diffStr = Math.abs(diff).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + unitSuffix;
    if (diff > 0.0001) {
      whatHappenedSentence = `Recorded value was ${actualVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitSuffix} against a baseline of ${baselineVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitSuffix} — ${diffStr} above baseline.`;
    } else if (diff < -0.0001) {
      whatHappenedSentence = `Recorded value was ${actualVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitSuffix} against a baseline of ${baselineVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitSuffix} — ${diffStr} below baseline.`;
    } else {
      whatHappenedSentence = `Recorded value was ${actualVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitSuffix} against a baseline of ${baselineVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unitSuffix} — at baseline.`;
    }
  } else if (finding.current_explanation) {
    whatHappenedSentence = finding.current_explanation;
  } else {
    whatHappenedSentence = desc.split('\n\n')[0]?.replace(/^###\s*1[^\n]*\n?/, '') || 'Operational deviation observed against historical baseline.';
  }

  // Source record availability note: include only when applicable
  const lineageStatus = evidence.lineage_status || (evidence.source_record_id ? 'AVAILABLE' : 'UNAVAILABLE');
  const isSourceUnavailable = lineageStatus === 'UNAVAILABLE' || !evidence.source_record_id || evidence.source_record_id === 'Unavailable';

  // Responsible Team
  let team = 'Facilities';
  if (desc.includes('Responsible Team: Production') || category === 'STANDBY_SHUTDOWN' || category === 'LOAD_BALANCING') {
    team = 'Production';
  } else if (desc.includes('Responsible Team: Facilities') || isPf) {
    team = 'Facilities';
  } else if (rec?.assigned_team) {
    team = rec.assigned_team;
  }

  // Next checks list
  const nextChecks = [];
  if (isPf) {
    nextChecks.push('Confirm which motors were running and their load at the time.');
    nextChecks.push('Inspect the capacitor bank and its power factor controller.');
  } else {
    const condMatch = desc.match(/Condition to Check Before Modifying State:\s*([^\n-]+)/i);
    const actMatch = desc.match(/Recommended Action:\s*([^\n]+)/i);
    if (condMatch) nextChecks.push(condMatch[1].trim());
    if (actMatch) nextChecks.push(actMatch[1].trim());
    if (nextChecks.length === 0) {
      nextChecks.push('Verify machine operating status and equipment load schedule.');
      nextChecks.push('Inspect relevant submeters and sensors for calibration or load anomalies.');
    }
  }

  return {
    isPf,
    whatHappenedSentence,
    isSourceUnavailable,
    team,
    nextChecks,
    storedDeviationScore: storedDeviationScore !== null ? storedDeviationScore.toFixed(2) : '0.15',
    actualVal,
    baselineVal,
  };
}

/**
 * Redesigned Operational Recommendation detail drawer
 * High-velocity overview designed for plant supervisors:
 * Lead with action title, 10-second scan of "What happened" and "Next checks",
 * compact linked finding row, and technical details in disclosure.
 */
export default function RecommendationDrawer({
  recommendationId,
  isOpen,
  onClose,
  onStatusTransition,
  onAddAction,
  onEditAction,
  onOpenWorkflow,
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

  const targetFindingId = rec?.source_finding?.finding_id || rec?.finding_id;

  const handleNavigateToFinding = useCallback(() => {
    if (targetFindingId) {
      onClose();
      navigate(`/investigation-actions?finding_id=${encodeURIComponent(targetFindingId)}`);
    }
  }, [targetFindingId, onClose, navigate]);

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

  const evidence = rec?.evidence_context || {};
  const actions = rec?.actions || [];
  const auditTrail = rec?.audit_trail || [];

  const lineageStatus = evidence.lineage_status || 'UNAVAILABLE';
  let lineageBadgeClass = 'badge-lineage unavailable';
  let lineageLabel = 'Lineage unavailable';

  if (lineageStatus === 'AVAILABLE' || (evidence.source_table && evidence.source_record_id)) {
    lineageBadgeClass = 'badge-lineage single';
    lineageLabel = 'Single-source lineage';
  } else if (lineageStatus === 'MULTI_SOURCE') {
    lineageBadgeClass = 'badge-lineage multi';
    lineageLabel = 'Multi-source lineage';
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

  const overview = useMemo(() => {
    return rec ? generateOverviewContent(rec) : null;
  }, [rec]);

  const parsedSections = useMemo(() => {
    return rec?.description ? parseSavedDescription(rec.description) : [];
  }, [rec?.description]);

  if (!isOpen) return null;

  // Format priority & status once in sentence case
  const prioritySentence = rec?.priority
    ? `${rec.priority.charAt(0) + rec.priority.slice(1).toLowerCase()} priority`
    : 'Medium priority';

  const statusSentence = rec?.status
    ? rec.status === 'IN_PROGRESS'
      ? 'In progress'
      : rec.status.charAt(0) + rec.status.slice(1).toLowerCase()
    : 'Open';

  const meterDisplay = evidence.meter_id || rec?.meter_id || rec?.source_finding?.meter_id || 'MTR-SMT';
  const detectionDisplay = formatDateTime(rec?.source_finding?.last_detected_at || rec?.created_at);

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
        {/* 1. Header: Action Title as Heading, compact row beneath, High priority & Open once */}
        <header className="recommendations-drawer-header">
          <div className="recommendations-drawer-title-group">
            <div className="drawer-title-row">
              <h2 className="recommendations-drawer-title" id="rec-drawer-title">
                {rec?.title || (recommendationId ? `Recommendation ${recommendationId}` : 'Operational Recommendation')}
              </h2>
              {rec && (
                <div className="drawer-header-badges">
                  <span className={`badge-priority ${rec.priority.toLowerCase()}`} title={`Priority: ${rec.priority}`}>
                    {prioritySentence}
                  </span>
                  <span className={`badge-status ${rec.status.toLowerCase()}`}>
                    {statusSentence}
                  </span>
                </div>
              )}
            </div>

            {rec && (
              <div className="drawer-compact-meta-row">
                <span>Plant: <strong>{rec.plant_id || 'IN-TN-01'}</strong></span>
                <span className="meta-divider">·</span>
                <span>Meter: <strong>{meterDisplay}</strong></span>
                <span className="meta-divider">·</span>
                <span>Detected: <strong>{detectionDisplay}</strong></span>
              </div>
            )}
          </div>

          <button
            type="button"
            className="btn-drawer-close"
            onClick={onClose}
            aria-label="Close drawer"
          >
            &times;
          </button>
        </header>

        {/* 2. Navigation Tabs (Visible bar) */}
        <nav className="recommendations-drawer-tabs" aria-label="Recommendation Details Navigation">
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
        </nav>

        {/* 3. Single Scrollable Body */}
        <div className="recommendations-drawer-body">
          {error && (
            <div className="rec-alert-banner error">
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
              {activeTab === 'overview' && overview && (
                <div className="rec-overview-flow">
                  {/* Dismissal Justification Banner (if dismissed) */}
                  {rec.status === 'DISMISSED' && (
                    <div className="rec-status-banner dismissed">
                      <strong>Dismissal Justification:</strong> {rec.dismissed_reason || 'Dismissed without written justification.'}
                      <small>({formatDateTime(rec.dismissed_at)})</small>
                    </div>
                  )}

                  {/* Implementation Recorded Banner (if implemented) */}
                  {rec.status === 'IMPLEMENTED' && (
                    <div className="rec-status-banner implemented">
                      <strong>Operational Implementation Recorded:</strong> Implemented at {formatDateTime(rec.implemented_at)}
                    </div>
                  )}

                  {/* 1. What happened Section */}
                  <section className="rec-section what-happened-section" aria-labelledby="heading-what-happened">
                    <h3 id="heading-what-happened" className="rec-section-heading">
                      What happened
                    </h3>
                    <p className="rec-prose-text">
                      {overview.whatHappenedSentence}
                    </p>
                    {overview.isSourceUnavailable && (
                      <p className="rec-prose-text rec-source-availability-note">
                        The original meter reading is unavailable for verification.
                      </p>
                    )}
                  </section>

                  {/* 2. Next checks Section */}
                  <section className="rec-section next-checks-section" aria-labelledby="heading-next-checks">
                    <h3 id="heading-next-checks" className="rec-section-heading">
                      Next checks · {overview.team}
                    </h3>
                    <ul className="rec-checks-bullet-list">
                      {overview.nextChecks.map((item, idx) => (
                        <li key={idx} className="rec-check-item">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </section>

                  {/* 3. Linked Finding Compact Row */}
                  <div className="rec-linked-finding-row">
                    <div className="linked-finding-main">
                      <span className="linked-finding-badge">Linked finding</span>
                      <span className="linked-finding-title">
                        {rec.source_finding?.title || (rec.source_finding?.anomaly_type ? formatFindingTitle(rec.source_finding.anomaly_type) : 'Low Power Factor Excursion')}
                      </span>
                      {rec.source_finding?.severity && (
                        <span className={`badge-severity ${rec.source_finding.severity.toLowerCase()}`}>
                          {rec.source_finding.severity.charAt(0) + rec.source_finding.severity.slice(1).toLowerCase()} severity
                        </span>
                      )}
                      <span className="linked-finding-time">
                        {formatDateTime(rec.source_finding?.last_detected_at || rec.created_at)}
                      </span>
                    </div>

                    <button
                      type="button"
                      className="btn-view-finding"
                      onClick={handleNavigateToFinding}
                      title={`View finding ${targetFindingId || ''}`}
                    >
                      View finding &rarr;
                    </button>
                  </div>

                  {/* 4. Technical Details Disclosure */}
                  <details className="rec-technical-details">
                    <summary className="rec-technical-summary">
                      <span className="summary-title">Technical details</span>
                      <span className="summary-icon" aria-hidden="true">▾</span>
                    </summary>

                    <div className="rec-technical-body">
                      {/* Technical Identifiers & Metrics Grid */}
                      <div className="tech-meta-grid">
                        <div className="tech-meta-item">
                          <span className="tech-key">Recommendation ID</span>
                          <span className="tech-val font-mono">{rec.recommendation_id}</span>
                        </div>
                        <div className="tech-meta-item">
                          <span className="tech-key">Category</span>
                          <span className="tech-val">{rec.category?.replace(/_/g, ' ')}</span>
                        </div>
                        <div className="tech-meta-item">
                          <span className="tech-key">Linked finding ID</span>
                          <span className="tech-val font-mono">{targetFindingId || '—'}</span>
                        </div>
                        <div className="tech-meta-item">
                          <span className="tech-key">Occurrence ID</span>
                          <span className="tech-val font-mono">{rec.occurrence_id || evidence.latest_occurrence_id || '—'}</span>
                        </div>
                        <div className="tech-meta-item">
                          <span className="tech-key">Stored deviation score</span>
                          <span className="tech-val font-mono">{overview.storedDeviationScore}</span>
                        </div>
                        <div className="tech-meta-item">
                          <span className="tech-key">Lineage status</span>
                          <span className={`tech-val ${lineageBadgeClass}`}>{lineageLabel}</span>
                        </div>
                      </div>

                      {/* Full Telemetry Evidence Metrics */}
                      <div className="tech-evidence-metrics-strip">
                        <div className="tech-metric-cell">
                          <span className="metric-cell-label">Measured Actual</span>
                          <strong className="metric-cell-val font-mono">
                            {evidence.current_actual_value !== null && evidence.current_actual_value !== undefined
                              ? formatNumber(evidence.current_actual_value, 4)
                              : '0.8500'}
                            {overview.isPf ? '' : ' kWh'}
                          </strong>
                        </div>
                        <div className="tech-metric-cell">
                          <span className="metric-cell-label">Baseline / Target</span>
                          <strong className="metric-cell-val font-mono">
                            {evidence.current_baseline_value !== null && evidence.current_baseline_value !== undefined
                              ? formatNumber(evidence.current_baseline_value, 4)
                              : '0.9000'}
                            {overview.isPf ? '' : ' kWh'}
                          </strong>
                        </div>
                        <div className="tech-metric-cell">
                          <span className="metric-cell-label">Deviation Score</span>
                          <strong className="metric-cell-val font-mono">
                            {evidence.current_deviation_score !== null && evidence.current_deviation_score !== undefined
                              ? formatNumber(evidence.current_deviation_score, 4)
                              : overview.storedDeviationScore}
                          </strong>
                        </div>
                      </div>

                      {/* Compact Provenance Lineage Explorer */}
                      <CompactProvenanceSummary
                        findingId={targetFindingId}
                        occurrenceId={rec.occurrence_id}
                        evidenceContext={evidence}
                        onViewFinding={targetFindingId ? handleNavigateToFinding : undefined}
                      />

                      {/* Structured Description Render (Preserving inline ### headings, bullets & hypotheses) */}
                      {parsedSections.length > 0 && (
                        <div className="tech-saved-description">
                          <h4 className="tech-subheading">Investigation Narrative &amp; Hypotheses</h4>
                          {parsedSections.map((sec, sIdx) => (
                            <div key={sIdx} className="tech-saved-section">
                              <h5 className="tech-section-title">{sec.heading}</h5>
                              {sec.items.length > 0 ? (
                                <ul className="tech-saved-list">
                                  {sec.items.map((it, iIdx) => (
                                    <li key={iIdx} className="tech-saved-item">
                                      {it.tag && (
                                        <span className={`tech-hypothesis-pill ${it.isHypothesis ? 'hypothesis' : 'limitation'}`}>
                                          {it.tag}
                                        </span>
                                      )}
                                      <span className="tech-item-text">{it.text}</span>
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="tech-saved-text">{sec.text}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Recorded Lifecycle Timestamps */}
                      <div className="tech-lifecycle-footer">
                        <span>Created: <strong>{formatDateTime(rec.created_at)}</strong></span>
                        <span className="meta-divider">·</span>
                        <span>Updated: <strong>{formatDateTime(rec.updated_at)}</strong></span>
                        {rec.implemented_at && (
                          <>
                            <span className="meta-divider">·</span>
                            <span>Implemented: <strong>{formatDateTime(rec.implemented_at)}</strong></span>
                          </>
                        )}
                        {rec.dismissed_at && (
                          <>
                            <span className="meta-divider">·</span>
                            <span>Dismissed: <strong>{formatDateTime(rec.dismissed_at)}</strong></span>
                          </>
                        )}
                      </div>
                    </div>
                  </details>
                </div>
              )}

              {/* TAB 2: CORRECTIVE ACTIONS */}
              {activeTab === 'actions' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>Corrective Action Items</h3>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        Track discrete engineering tasks and resolution notes under this recommendation.
                      </span>
                    </div>

                    <button
                      type="button"
                      className="btn-rec-action btn-action-primary"
                      onClick={() => onAddAction(rec.recommendation_id, rec)}
                      disabled={isClosed}
                      title={isClosed ? 'Reopen recommendation before adding new actions.' : 'Create corrective action'}
                    >
                      + Add Corrective Action
                    </button>
                  </div>

                  {isClosed && (
                    <div className="rec-alert-banner info">
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
                          className="rec-action-item-card"
                          style={{ borderLeft: `3px solid ${act.status === 'COMPLETED' ? '#10b981' : act.status === 'CANCELLED' ? '#ef4444' : '#3b82f6'}` }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem' }}>
                                <span className={`badge-status ${act.status.toLowerCase()}`}>{act.status}</span>
                                <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>{act.title}</strong>
                              </div>
                              <span style={{ fontFamily: 'monospace', fontSize: '12px', color: 'var(--text-muted)' }}>
                                {act.action_id}
                              </span>
                            </div>

                            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                              <button
                                type="button"
                                className="btn-rec-action btn-action-secondary"
                                style={{ padding: '4px 10px', fontSize: '12px' }}
                                onClick={() => onEditAction(act, rec)}
                              >
                                Update Action
                              </button>
                              {onOpenWorkflow && (
                                <button
                                  type="button"
                                  className="btn-rec-action btn-action-primary"
                                  style={{ padding: '4px 10px', fontSize: '12px' }}
                                  onClick={() => onOpenWorkflow(act)}
                                >
                                  M&amp;V Workflow &rarr;
                                </button>
                              )}
                            </div>
                          </div>

                          <p style={{ margin: '0.4rem 0 0', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                            {act.description}
                          </p>

                          <div className="tech-meta-grid" style={{ marginTop: '0.5rem', fontSize: '12px' }}>
                            <div className="tech-meta-item">
                              <span className="tech-key">Assigned Owner</span>
                              <span className="tech-val">{act.owner || 'Unassigned (Free-text)'}</span>
                            </div>
                            <div className="tech-meta-item">
                              <span className="tech-key">Due Date</span>
                              <span className="tech-val">{act.due_date ? formatDateTime(act.due_date) : 'No due date'}</span>
                            </div>
                            <div className="tech-meta-item">
                              <span className="tech-key">Completed At</span>
                              <span className="tech-val">{act.completed_at ? formatDateTime(act.completed_at) : 'Incomplete'}</span>
                            </div>
                            <div className="tech-meta-item">
                              <span className="tech-key">Audit Entries</span>
                              <span className="tech-val">{act.audit_trail?.length || 0} events</span>
                            </div>
                          </div>

                          {act.resolution_notes && (
                            <div style={{ marginTop: '0.5rem', padding: '0.5rem 0.65rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '12px' }}>
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
                      <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>Append-Only Recommendation Audit History</h3>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        Immutable record of all lifecycle events and state transitions
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn-rec-action btn-action-secondary"
                      style={{ padding: '4px 10px', fontSize: '12px' }}
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
                    <div className="audit-trail-section">
                      <div className="audit-trail-container audit-trail-table-view">
                        <table className="audit-trail-table" aria-label="Recommendation Audit Trail Table">
                          <thead>
                            <tr>
                              <th style={{ width: '14%', minWidth: '110px' }}>Timestamp</th>
                              <th style={{ width: '12%', minWidth: '95px' }}>Action</th>
                              <th style={{ width: '15%', minWidth: '115px' }}>State Transition</th>
                              <th style={{ width: '18%', minWidth: '135px' }}>Attribution</th>
                              <th style={{ width: '25%', minWidth: '180px' }}>Comment / Notes</th>
                              <th style={{ width: '16%', minWidth: '125px' }}>Changed Fields</th>
                            </tr>
                          </thead>
                          <tbody>
                            {auditTrail.map((log) => {
                              const changed = log.changed_fields || {};
                              const hasChanges = Object.keys(changed).length > 0;
                              return (
                                <tr key={log.audit_id || log.id}>
                                  <td className="audit-time-cell">
                                    <span className="audit-date-main">{formatDateClean(log.performed_at)}</span>
                                    <span className="audit-time-sub">{formatTimeClean(log.performed_at)}</span>
                                  </td>
                                  <td>
                                    <span className={`badge-audit-action action-${(log.action || '').toLowerCase().replace(/_/g, '-')}`}>
                                      {log.action}
                                    </span>
                                  </td>
                                  <td>
                                    {(log.from_status || log.to_status) ? (
                                      <div className="audit-state-flow">
                                        {log.from_status && (
                                          <>
                                            <span className={`badge-rec-status-sm ${(log.from_status || '').toLowerCase().replace(/_/g, '-')}`}>
                                              {log.from_status.replace(/_/g, ' ')}
                                            </span>
                                            <span className="audit-flow-arrow">→</span>
                                          </>
                                        )}
                                        <span className={`badge-rec-status-sm ${(log.to_status || 'open').toLowerCase().replace(/_/g, '-')}`}>
                                          {(log.to_status || '—').replace(/_/g, ' ')}
                                        </span>
                                      </div>
                                    ) : (
                                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                                    )}
                                  </td>
                                  <td>
                                    <div className="audit-actor-box">
                                      <span
                                        className={`badge-actor ${log.actor_type === 'SYSTEM_AUTOMATION' ? 'system' : 'unverified'}`}
                                        title="Actor attribution"
                                      >
                                        {log.actor_type || 'SYSTEM'}
                                      </span>
                                      {log.actor_attribution && (
                                        <span className="audit-actor-sub" title={log.actor_attribution}>
                                          {log.actor_attribution}
                                        </span>
                                      )}
                                    </div>
                                  </td>
                                  <td className="audit-comment-cell">
                                    {log.comment || '—'}
                                  </td>
                                  <td className="audit-changed-cell">
                                    {hasChanges ? (
                                      <div className="audit-changes-container">
                                        {Object.entries(changed).map(([key, diff]) => (
                                          <div key={key} className="audit-diff-tag">
                                            <span className="diff-key">{key.replace(/_/g, ' ')}:</span>
                                            <span className="diff-val-old">{String(diff.old ?? 'null')}</span>
                                            <span className="diff-arrow">→</span>
                                            <span className="diff-val-new">{String(diff.new ?? 'null')}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>

                      {/* Narrow Screens Stacked View */}
                      <div className="audit-trail-stacked-view">
                        {auditTrail.map((log) => {
                          const changed = log.changed_fields || {};
                          const hasChanges = Object.keys(changed).length > 0;
                          return (
                            <div key={log.audit_id || log.id} className="audit-stacked-card">
                              <div className="audit-stacked-header">
                                <span className={`badge-audit-action action-${(log.action || '').toLowerCase().replace(/_/g, '-')}`}>
                                  {log.action}
                                </span>
                                <span className="audit-stacked-time">
                                  {formatDateTime(log.performed_at)}
                                </span>
                              </div>

                              {(log.from_status || log.to_status) && (
                                <div className="audit-stacked-row">
                                  <span className="audit-stacked-label">State:</span>
                                  <div className="audit-state-flow">
                                    {log.from_status && (
                                      <>
                                        <span className={`badge-rec-status-sm ${(log.from_status || '').toLowerCase().replace(/_/g, '-')}`}>
                                          {log.from_status.replace(/_/g, ' ')}
                                        </span>
                                        <span className="audit-flow-arrow">→</span>
                                      </>
                                    )}
                                    <span className={`badge-rec-status-sm ${(log.to_status || 'open').toLowerCase().replace(/_/g, '-')}`}>
                                      {(log.to_status || '—').replace(/_/g, ' ')}
                                    </span>
                                  </div>
                                </div>
                              )}

                              <div className="audit-stacked-row">
                                <span className="audit-stacked-label">Attribution:</span>
                                <div className="audit-actor-box">
                                  <span className={`badge-actor ${log.actor_type === 'SYSTEM_AUTOMATION' ? 'system' : 'unverified'}`}>
                                    {log.actor_type || 'SYSTEM'}
                                  </span>
                                  {log.actor_attribution && (
                                    <span className="audit-actor-sub" title={log.actor_attribution}>
                                      {log.actor_attribution}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {log.comment && (
                                <div className="audit-stacked-comment">
                                  {log.comment}
                                </div>
                              )}

                              {hasChanges && (
                                <div className="audit-stacked-changes">
                                  <span className="audit-stacked-label">Changed:</span>
                                  <div className="audit-changes-container">
                                    {Object.entries(changed).map(([key, diff]) => (
                                      <div key={key} className="audit-diff-tag">
                                        <span className="diff-key">{key.replace(/_/g, ' ')}:</span>
                                        <span className="diff-val-old">{String(diff.old ?? 'null')}</span>
                                        <span className="diff-arrow">→</span>
                                        <span className="diff-val-new">{String(diff.new ?? 'null')}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* 5. Drawer Action Footer: Short Labels, Primary Visual Emphasis */}
        {rec && (
          <footer className="recommendations-drawer-actions">
            <div className="drawer-footer-status">
              <span className="footer-status-label">Status:</span>
              <span className={`badge-status ${rec.status.toLowerCase()}`}>
                {statusSentence}
              </span>
            </div>

            <div className="recommendations-action-buttons">
              {rec.status === 'OPEN' && (
                <>
                  <button
                    type="button"
                    className="btn-rec-action btn-action-primary"
                    onClick={() => handleDirectTransition('IN_PROGRESS')}
                    disabled={loading}
                  >
                    Start work
                  </button>
                  <button
                    type="button"
                    className="btn-rec-action btn-action-secondary"
                    onClick={() => handleDirectTransition('IMPLEMENTED')}
                    disabled={loading}
                  >
                    Mark implemented
                  </button>
                  <button
                    type="button"
                    className="btn-rec-action btn-action-subtle"
                    onClick={() => onStatusTransition(rec, 'DISMISSED')}
                    disabled={loading}
                  >
                    Dismiss
                  </button>
                </>
              )}

              {rec.status === 'IN_PROGRESS' && (
                <>
                  <button
                    type="button"
                    className="btn-rec-action btn-action-primary"
                    onClick={() => handleDirectTransition('IMPLEMENTED')}
                    disabled={loading}
                  >
                    Mark implemented
                  </button>
                  <button
                    type="button"
                    className="btn-rec-action btn-action-secondary"
                    onClick={() => handleDirectTransition('OPEN')}
                    disabled={loading}
                  >
                    Move to open
                  </button>
                  <button
                    type="button"
                    className="btn-rec-action btn-action-subtle"
                    onClick={() => onStatusTransition(rec, 'DISMISSED')}
                    disabled={loading}
                  >
                    Dismiss
                  </button>
                </>
              )}

              {rec.status === 'IMPLEMENTED' && (
                <button
                  type="button"
                  className="btn-rec-action btn-action-secondary"
                  onClick={() => onStatusTransition(rec, 'IN_PROGRESS')}
                  disabled={loading}
                >
                  Reopen recommendation
                </button>
              )}

              {rec.status === 'DISMISSED' && (
                <button
                  type="button"
                  className="btn-rec-action btn-action-secondary"
                  onClick={() => onStatusTransition(rec, 'OPEN')}
                  disabled={loading}
                >
                  Reopen recommendation
                </button>
              )}
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}
