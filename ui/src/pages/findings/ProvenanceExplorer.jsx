import React, { useState, useEffect } from 'react';
import { formatDateTime, formatNumber } from '../../utils/formatters';
import { findingsApi } from '../../services/findingsApi';

/**
 * Copy to clipboard button with tactile visual feedback.
 */
export function CopyButton({ text, label = 'Copy', title = 'Copy to clipboard', className = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e) => {
    e.stopPropagation();
    if (!text) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (err) {
      console.warn('Clipboard write failed:', err);
    }
  };

  return (
    <button
      type="button"
      className={`btn-copy-provenance ${copied ? 'copied' : ''} ${className}`}
      onClick={handleCopy}
      title={title}
      aria-label={`${label} ${text}`}
    >
      {copied ? (
        <>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span>Copied!</span>
        </>
      ) : (
        <>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
          </svg>
          <span>{label}</span>
        </>
      )}
    </button>
  );
}

/**
 * Determine deterministic lineage category from occurrence or context fields.
 * Returns: 'AVAILABLE' | 'MULTI_SOURCE' | 'UPLOAD_UNAVAILABLE' | 'SOURCE_MISSING' | 'LEGACY_UNLINKED' | 'LEGACY' | 'UNAVAILABLE'
 */
export function getLineageStatus(occ) {
  if (!occ) return 'UNAVAILABLE';

  // Explicit status from backend occurrence provenance response
  if (occ.overall_lineage_state) {
    return occ.overall_lineage_state;
  }

  // Explicit stream-level state if inspecting a single resolved record
  if (occ.lineage_state) {
    if (occ.upload_status === 'UPLOAD_NOT_FOUND') {
      return 'UPLOAD_NOT_FOUND';
    }
    if (occ.record_status === 'UNSUPPORTED_TABLE') {
      return 'UNSUPPORTED_TABLE';
    }
    return occ.lineage_state;
  }

  if (occ.revision_status === 'ORIGINAL_REVISION_UNAVAILABLE' || occ.lineage_status === 'ORIGINAL_REVISION_UNAVAILABLE') {
    return 'ORIGINAL_REVISION_UNAVAILABLE';
  }

  // Explicit multi-source from backend schema or composite source records list
  if (
    occ.lineage_status === 'MULTI_SOURCE' ||
    (Array.isArray(occ.source_records) && occ.source_records.length > 1)
  ) {
    return 'MULTI_SOURCE';
  }

  // Check if primary source identity exists
  const hasSourceRecord = Boolean(occ.source_table && occ.source_record_id);
  const hasUploadId = Boolean(occ.upload_id);

  if (hasSourceRecord) {
    // If source table and record ID are present but upload_id is null, it's historical/upload unavailable
    return hasUploadId ? 'AVAILABLE' : 'UPLOAD_UNAVAILABLE';
  }

  // Check single item in source_records array
  if (Array.isArray(occ.source_records) && occ.source_records.length === 1) {
    const single = occ.source_records[0];
    if (single.source_table && single.source_record_id) {
      if (single.upload_status === 'UPLOAD_NOT_FOUND') return 'UPLOAD_NOT_FOUND';
      if (single.record_status === 'UNSUPPORTED_TABLE') return 'UNSUPPORTED_TABLE';
      return single.upload_id ? 'AVAILABLE' : 'UPLOAD_UNAVAILABLE';
    }
  }

  if (occ.lineage_status === 'AVAILABLE') {
    return hasUploadId ? 'AVAILABLE' : 'UPLOAD_UNAVAILABLE';
  }

  if (occ.lineage_status === 'LEGACY' || occ.lineage_status === 'LEGACY_UNLINKED') {
    return occ.lineage_status;
  }

  return 'LEGACY_UNLINKED';
}

/**
 * Formats machine roles into human-readable titles.
 */
export function formatRoleLabel(role) {
  if (!role) return 'Source Telemetry Stream';
  switch (role) {
    case 'PRODUCTION_ZERO_OUTPUT_EVENT':
      return 'Production Output Event (Line Idle / Zero Units)';
    case 'PROCESS_ENERGY_MEASUREMENT':
      return 'Process Energy Measurement (Submeter Draw)';
    case 'MAIN_INCOMER_ENERGY':
      return 'Main Incomer Grid Telemetry';
    case 'SUBMETER_ENERGY':
      return 'Submeter Energy Telemetry';
    case 'PRIMARY_OBSERVATION':
      return 'Primary Physical Sensor Observation';
    default:
      return role.replace(/_/g, ' ');
  }
}

/**
 * Badge indicating deterministic lineage status.
 * Supports all explicit states: AVAILABLE, MULTI_SOURCE, UPLOAD_UNAVAILABLE, UPLOAD_NOT_FOUND, SOURCE_MISSING, UNSUPPORTED_TABLE, LEGACY_UNLINKED
 */
export function LineageStatusBadge({ status, streamCount = 0, isCompact = false, occurrence = null }) {
  const resolvedStatus = status || (occurrence ? getLineageStatus(occurrence) : 'UNAVAILABLE');
  let badgeClass = 'badge-lineage badge-lineage-unavailable';
  let label = 'Lineage Unavailable';
  let title = 'Source record identity could not be resolved from telemetry records';

  switch (resolvedStatus) {
    case 'AVAILABLE':
      badgeClass = 'badge-lineage badge-lineage-available';
      label = isCompact ? 'Single-Source' : 'Single-Source Lineage';
      title = 'Grounded directly in physical sensor records with verified upload batch attribution';
      break;
    case 'MULTI_SOURCE':
      badgeClass = 'badge-lineage badge-lineage-multi';
      label = isCompact
        ? `Multi-Source (${streamCount || 2})`
        : `Multi-Source Lineage (${streamCount || 2} streams)`;
      title = 'Composite anomaly derived by cross-correlating production execution events and electrical meter readings';
      break;
    case 'UPLOAD_UNAVAILABLE':
      badgeClass = 'badge-lineage badge-lineage-upload-unavailable';
      label = isCompact ? 'Upload Unlinked' : 'Upload Metadata Unavailable';
      title = 'Source telemetry record exists in database, but batch upload metadata is unavailable or record predates upload tracking';
      break;
    case 'UPLOAD_NOT_FOUND':
      badgeClass = 'badge-lineage badge-lineage-upload-not-found';
      label = isCompact ? 'Upload Missing' : 'Upload Record Missing';
      title = 'Upload batch ID was referenced, but no matching record exists in upload_history (batch unlinked or purged)';
      break;
    case 'SOURCE_MISSING':
      badgeClass = 'badge-lineage badge-lineage-source-missing';
      label = isCompact ? 'Source Missing' : 'Source Record Missing';
      title = 'Stored source record identifier exists, but original record could not be retrieved from the database';
      break;
    case 'UNSUPPORTED_TABLE':
      badgeClass = 'badge-lineage badge-lineage-unsupported';
      label = isCompact ? 'Unsupported' : 'Unsupported Source Table';
      title = 'Source table is not in allowlisted telemetry tables; query execution was blocked';
      break;
    case 'LEGACY_UNLINKED':
      badgeClass = 'badge-lineage badge-lineage-legacy-unlinked';
      label = isCompact ? 'Legacy Unlinked' : 'Legacy Unlinked Finding';
      title = 'Historical finding has no stored source record identity; recorded prior to telemetry tracking';
      break;
    case 'LEGACY':
      badgeClass = 'badge-lineage badge-lineage-legacy';
      label = isCompact ? 'Legacy Upload' : 'Legacy Record (Unattributed Upload)';
      title = 'Historical sensor record; row ID resolved, but batch upload metadata was not tracked prior to provenance tracking';
      break;
    case 'ORIGINAL_REVISION_UNAVAILABLE':
      badgeClass = 'badge-lineage badge-lineage-legacy';
      label = isCompact ? 'Rev Unavailable' : 'Original Revision Unavailable';
      title = 'Original source revision was not pinned at detection; historical values retained from snapshot';
      break;
    case 'UNAVAILABLE':
    default:
      badgeClass = 'badge-lineage badge-lineage-unavailable';
      label = isCompact ? 'Unavailable' : 'Lineage Unavailable';
      title = 'Source record identity is unavailable; no fake or inferred IDs are displayed';
      break;
  }

  return (
    <span className={badgeClass} title={title}>
      <span className="badge-lineage-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

/**
 * Visual card representing a single contributing source record.
 */
export function SourceStreamCard({ record, role, index = 0, isMulti = false }) {
  if (!record) return null;

  const roleName = role || record.role;
  const isProductionRole = roleName === 'PRODUCTION_ZERO_OUTPUT_EVENT' || record.source_table?.includes('production');
  const isEnergyRole = roleName === 'PROCESS_ENERGY_MEASUREMENT' || record.source_table?.includes('energy');

  let cardRoleClass = 'role-default';
  if (isProductionRole) cardRoleClass = 'role-prod';
  else if (isEnergyRole) cardRoleClass = 'role-energy';

  const hasUpload = Boolean(record.upload_id);

  return (
    <div className={`provenance-stream-card ${cardRoleClass}`}>
      <div className="provenance-stream-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
          {isMulti && (
            <span className="provenance-stream-index">Stream #{index + 1}</span>
          )}
          <span className="provenance-role-badge">
            {formatRoleLabel(roleName)}
          </span>
        </div>
        <span className="provenance-table-badge" title="Underlying PostgreSQL physical database table">
          {record.source_table || 'Source Table Unavailable'}
        </span>
      </div>

      <div className="provenance-fields-list">
        {/* Source Record ID */}
        <div className="provenance-field-row">
          <label className="provenance-field-label">Original Source Record ID</label>
          <div className="provenance-field-value">
            {record.source_record_id ? (
              <>
                <span className="provenance-id-text" title={record.source_record_id}>
                  {record.source_record_id}
                </span>
                <CopyButton text={record.source_record_id} label="Copy ID" />
              </>
            ) : (
              <span className="provenance-val-unavailable">ID Unavailable</span>
            )}
          </div>
        </div>

        {/* Upload Batch ID */}
        <div className="provenance-field-row">
          <label className="provenance-field-label">Source Upload Batch ID</label>
          <div className="provenance-field-value">
            {hasUpload ? (
              <>
                <span className="provenance-id-text" title={record.upload_id}>
                  {record.upload_id}
                </span>
                <CopyButton text={record.upload_id} label="Copy Batch" />
              </>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem', width: '100%' }}>
                <span className="provenance-val-legacy">Unavailable (Historical Data)</span>
                <span className="provenance-legacy-hint">
                  Original upload batch attribution is unavailable for this historical record (ingested prior to provenance tracking).
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Full Evidence & Data Provenance card for an occurrence.
 */
export function EvidenceProvenanceCard({
  occurrence,
  finding,
  isPrimary = false,
  title = 'Evidence & Data Provenance',
  onOpenProvenanceTab = null,
}) {
  if (!occurrence) return null;

  const lineageStatus = getLineageStatus(occurrence);
  const sourceRecords = Array.isArray(occurrence.source_records) && occurrence.source_records.length > 0
    ? occurrence.source_records
    : (occurrence.source_table && occurrence.source_record_id
      ? [{
          source_table: occurrence.source_table,
          source_record_id: occurrence.source_record_id,
          upload_id: occurrence.upload_id,
        }]
      : []);

  const streamCount = sourceRecords.length;

  return (
    <div className={`provenance-card ${isPrimary ? 'primary' : ''}`}>
      <div className="provenance-card-header">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
          <h4 style={{ margin: 0, fontSize: '0.86rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {title}
          </h4>
          <span className="provenance-breadcrumb">
            Finding: {finding?.finding_id || occurrence.finding_id} &rarr; Occurrence: {occurrence.occurrence_id}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <LineageStatusBadge status={lineageStatus} streamCount={streamCount} />
          {occurrence.detector_version && (
            <span className="provenance-detector-pill" title="Deterministic detector version">
              Detector: {occurrence.detector_version}
            </span>
          )}
          {onOpenProvenanceTab && (
            <button
              type="button"
              className="btn-findings-link-compact"
              style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
              onClick={onOpenProvenanceTab}
              title="Open full interactive provenance drill-down"
            >
              Deep Lineage Trace &rarr;
            </button>
          )}
        </div>
      </div>

      {/* Explanatory Banner based on State */}
      {lineageStatus === 'MULTI_SOURCE' && (
        <div className="provenance-callout multi">
          <strong>Multi-Source Composite Evidence:</strong> This anomaly is detected by cross-referencing multiple discrete records. Each supporting stream is tracked independently below with its originating table and batch attribution.
        </div>
      )}

      {lineageStatus === 'AVAILABLE' && (
        <div className="provenance-callout available">
          <strong>Single-Source Evidence:</strong> Grounded in an individual verified sensor record. Exact database table, record ID, and ingestion upload batch are fully traceable.
        </div>
      )}

      {lineageStatus === 'LEGACY' && (
        <div className="provenance-callout legacy">
          <strong>Historical Telemetry Record:</strong> The physical database observation ID is verified, but upload batch attribution is unavailable because this record predates the provenance audit system.
        </div>
      )}

      {lineageStatus === 'UNAVAILABLE' && (
        <div className="provenance-callout unavailable">
          <strong>Lineage Unavailable:</strong> Originating row identity could not be resolved from telemetry records. The platform strictly presents confirmed metadata only and never fabricates identifiers.
        </div>
      )}

      {/* Source Record Streams */}
      {sourceRecords.length > 0 ? (
        <div className={`provenance-streams-grid ${sourceRecords.length > 1 ? 'is-multi' : 'is-single'}`}>
          {sourceRecords.map((rec, idx) => (
            <SourceStreamCard
              key={`${rec.source_table}-${rec.source_record_id || idx}`}
              record={rec}
              role={rec.role}
              index={idx}
              isMulti={sourceRecords.length > 1}
            />
          ))}
        </div>
      ) : (
        <div className="provenance-empty-box">
          No detailed source records are linked to this occurrence.
        </div>
      )}

      {/* Metadata Footer: Ingestion & Recorded Timestamps */}
      <div className="provenance-footer-meta">
        <div>
          <label>Observation Timestamp:</label>
          <span>{formatDateTime(occurrence.occurrence_ts)}</span>
        </div>
        {occurrence.recorded_at && (
          <div>
            <label>Recorded In System:</label>
            <span>{formatDateTime(occurrence.recorded_at)}</span>
          </div>
        )}
        <div>
          <label>Audit Persistence:</label>
          <span>Neon PostgreSQL (Append-Only)</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Compact provenance summary component for RecommendationDrawer and RecommendationsActions.
 */
export function CompactProvenanceSummary({
  findingId,
  occurrenceId,
  evidenceContext,
  onViewFinding,
}) {
  const evidence = evidenceContext || {};
  const status = getLineageStatus(evidence);

  const sourceRecords = Array.isArray(evidence.source_records) && evidence.source_records.length > 0
    ? evidence.source_records
    : (evidence.source_table && evidence.source_record_id
      ? [{
          source_table: evidence.source_table,
          source_record_id: evidence.source_record_id,
          upload_id: evidence.upload_id,
        }]
      : []);

  return (
    <div className="provenance-compact-box">
      <div className="provenance-compact-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontWeight: 700, fontSize: '0.8rem', color: 'var(--text-primary)' }}>
            Telemetry Lineage
          </span>
          <LineageStatusBadge status={status} streamCount={sourceRecords.length} isCompact />
        </div>
        {onViewFinding && findingId && (
          <button
            type="button"
            className="btn-findings-link-compact"
            onClick={onViewFinding}
            title="Open complete evidence and occurrence history in Findings Centre"
          >
            Inspect in Findings Centre &rarr;
          </button>
        )}
      </div>

      <div className="provenance-compact-grid">
        {sourceRecords.length > 0 ? (
          sourceRecords.map((rec, idx) => (
            <div key={`${rec.source_table}-${idx}`} className="provenance-compact-row">
              <span className="provenance-compact-table">{rec.source_table}</span>
              <div className="provenance-compact-id-group">
                <span className="provenance-compact-label">ID:</span>
                <span className="provenance-compact-id">{rec.source_record_id || 'Unavailable'}</span>
                {rec.source_record_id && (
                  <CopyButton text={rec.source_record_id} label="Copy" className="btn-copy-mini" />
                )}
              </div>
              <div className="provenance-compact-id-group">
                <span className="provenance-compact-label">Upload:</span>
                <span className="provenance-compact-id">
                  {rec.upload_id || 'Historical (Legacy)'}
                </span>
                {rec.upload_id && (
                  <CopyButton text={rec.upload_id} label="Copy" className="btn-copy-mini" />
                )}
              </div>
            </div>
          ))
        ) : (
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            Source record identification is unavailable for this recommendation evidence context.
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Interactive end-to-end Source Record Provenance Drill-Down Component.
 * Supports single-source and multi-source occurrences, allowlisted tables (energy & production),
 * upload history metadata inspection, and expandable raw database record viewers.
 */
export function ProvenanceDrillDownView({
  findingId,
  initialOccurrenceId = null,
  occurrences = [],
  onSelectOccurrence = null,
}) {
  const [selectedOccId, setSelectedOccId] = useState(
    initialOccurrenceId || (occurrences.length > 0 ? occurrences[0].occurrence_id : null)
  );
  const [drillData, setDrillData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedStreams, setExpandedStreams] = useState({});
  const [viewModes, setViewModes] = useState({});

  useEffect(() => {
    if (initialOccurrenceId) {
      setSelectedOccId(initialOccurrenceId);
    } else if (!selectedOccId && occurrences.length > 0) {
      setSelectedOccId(occurrences[0].occurrence_id);
    }
  }, [initialOccurrenceId, occurrences]);

  useEffect(() => {
    if (!findingId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    findingsApi
      .getOccurrenceProvenance(findingId, selectedOccId)
      .then((res) => {
        if (!cancelled) {
          setDrillData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || 'Failed to load provenance drill-down.');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [findingId, selectedOccId]);

  const handleToggleStream = (idx) => {
    setExpandedStreams((prev) => ({
      ...prev,
      [idx]: !prev[idx],
    }));
  };

  const handleSetViewMode = (idx, mode) => {
    setViewModes((prev) => ({
      ...prev,
      [idx]: mode,
    }));
  };

  const handleOccurrenceChange = (newOccId) => {
    setSelectedOccId(newOccId);
    if (onSelectOccurrence) {
      onSelectOccurrence(newOccId);
    }
  };

  if (loading && !drillData) {
    return (
      <div className="provenance-drilldown-wrapper" style={{ padding: '2rem', textAlign: 'center' }}>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Loading end-to-end source telemetry provenance...
        </div>
      </div>
    );
  }

  if (error && !drillData) {
    return (
      <div className="provenance-drilldown-wrapper">
        <div className="provenance-callout unavailable">
          <strong>Provenance Resolution Error:</strong> {error}
        </div>
      </div>
    );
  }

  const data = drillData || {};
  const overallState = data.overall_lineage_state || 'UNAVAILABLE';
  const streams = data.source_records || [];
  const currentOccId = data.occurrence_id || selectedOccId || 'N/A';

  return (
    <div className="provenance-drilldown-wrapper">
      {/* 1. Header Toolbar with Occurrence Switcher */}
      <div className="provenance-toolbar">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.86rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Source Record Provenance Drill-Down
            </span>
            <LineageStatusBadge status={overallState} streamCount={streams.length} />
            {data.qualification_status && (
              <span className={`provenance-detector-pill status-${data.qualification_status.toLowerCase()}`} title="Baseline qualification status">
                Qualification: {data.qualification_status}
              </span>
            )}
            {data.confidence && (
              <span className="provenance-detector-pill" title="Detector confidence score">
                Confidence: {data.confidence}
              </span>
            )}
            {data.trust_level && (
              <span className="provenance-detector-pill" title="Detector trust level">
                Trust: {data.trust_level}
              </span>
            )}
            {data.comparison_window && (
              <span className="provenance-detector-pill" title="Comparison window used by detector">
                Window: {data.comparison_window}
              </span>
            )}
          </div>
          <span className="provenance-breadcrumb">
            Trace: Finding {findingId} &rarr; Occurrence {currentOccId}
          </span>
        </div>

        {occurrences && occurrences.length > 1 && (
          <div className="provenance-occurrence-select-wrap">
            <label htmlFor="provenance-occ-select" style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
              Select Occurrence:
            </label>
            <select
              id="provenance-occ-select"
              className="provenance-occurrence-select"
              value={selectedOccId || ''}
              onChange={(e) => handleOccurrenceChange(e.target.value)}
            >
              {occurrences.map((occ, idx) => (
                <option key={occ.occurrence_id} value={occ.occurrence_id}>
                  #{occurrences.length - idx}: {formatDateTime(occ.occurrence_ts || occ.detected_at)} ({occ.occurrence_id.slice(-6)})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* 2. Visual End-to-End Trace Stepper */}
      <div className="provenance-trace-stepper">
        <div className="provenance-trace-node">
          <span className="provenance-trace-step-num">Step 1 &bull; Entity</span>
          <span className="provenance-trace-label">Operational Finding</span>
          <span className="provenance-trace-val" title={findingId}>{findingId}</span>
        </div>

        <span className="provenance-trace-arrow">&rarr;</span>

        <div className="provenance-trace-node active">
          <span className="provenance-trace-step-num">Step 2 &bull; Evidence</span>
          <span className="provenance-trace-label">Occurrence Record</span>
          <span className="provenance-trace-val" title={currentOccId}>{currentOccId}</span>
        </div>

        <span className="provenance-trace-arrow">&rarr;</span>

        <div className="provenance-trace-node">
          <span className="provenance-trace-step-num">Step 3 &bull; Source Data</span>
          <span className="provenance-trace-label">
            {streams.length > 1 ? `${streams.length} Source Streams` : (streams[0]?.source_table || 'Telemetry Row')}
          </span>
          <span className="provenance-trace-val" title={streams[0]?.source_record_id || 'ID'}>
            {streams.length > 1 ? 'Multi-Source Correlation' : (streams[0]?.source_record_id || 'ID Unavailable')}
          </span>
        </div>

        <span className="provenance-trace-arrow">&rarr;</span>

        <div className="provenance-trace-node">
          <span className="provenance-trace-step-num">Step 4 &bull; Provenance</span>
          <span className="provenance-trace-label">Upload Batch Audit</span>
          <span className="provenance-trace-val" title={streams[0]?.upload?.upload_id || 'Batch ID'}>
            {streams.some((s) => s.upload?.upload_id)
              ? (streams.find((s) => s.upload?.upload_id)?.upload?.upload_id || 'Linked')
              : 'Historical / Unlinked'}
          </span>
        </div>
      </div>

      {/* 3. Explanatory Callout Banner based on Lineage State */}
      {overallState === 'MULTI_SOURCE' && (
        <div className="provenance-callout multi">
          <strong>Multi-Source Composite Telemetry:</strong> {data.lineage_explanation || 'This anomaly is derived by cross-correlating manufacturing production output and discrete electrical submetering. Each stream is grounded independently in PostgreSQL.'}
        </div>
      )}

      {overallState === 'AVAILABLE' && (
        <div className="provenance-callout available">
          <strong>Single-Source Grounded Lineage:</strong> {data.lineage_explanation || 'Originating physical sensor record and its batch ingestion audit trail are verified in the database.'}
        </div>
      )}

      {overallState === 'UPLOAD_UNAVAILABLE' && (
        <div className="provenance-callout upload_unavailable">
          <strong>Source Record Grounded (Batch Ingestion Unlinked):</strong> {data.lineage_explanation || 'Originating sensor observation is verified in PostgreSQL, but batch upload metadata is unavailable (historical baseline data).'}
        </div>
      )}

      {overallState === 'SOURCE_MISSING' && (
        <div className="provenance-callout source_missing">
          <strong>Source Record Not Found:</strong> {data.lineage_explanation || 'The occurrence references a primary key identifier that could not be retrieved from the database.'}
        </div>
      )}

      {overallState === 'LEGACY_UNLINKED' && (
        <div className="provenance-callout legacy_unlinked">
          <strong>Legacy Unlinked Finding:</strong> {data.lineage_explanation || 'Historical finding with no recorded occurrences or source telemetry links.'}
        </div>
      )}

      {/* Evidence Quality & Physical Conditions Card */}
      {(data.observed_condition || data.limits_of_interpretation || data.suggested_investigation) && (
        <div className="provenance-evidence-quality-box" style={{ padding: '0.85rem', background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '6px', marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.04em' }}>
            Detector Evidence Quality &amp; Physical Conditions
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem' }}>
            {data.observed_condition && (
              <div style={{ padding: '0.6rem', background: 'rgba(59, 130, 246, 0.05)', borderRadius: '4px', borderLeft: '3px solid var(--brand-blue, #3b82f6)' }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--brand-blue, #3b82f6)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                  Observed Physical Condition
                </span>
                <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                  {data.observed_condition}
                </p>
              </div>
            )}
            {data.limits_of_interpretation && (
              <div style={{ padding: '0.6rem', background: 'rgba(234, 179, 8, 0.05)', borderRadius: '4px', borderLeft: '3px solid var(--brand-yellow, #eab308)' }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--brand-yellow, #eab308)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                  Limits of Interpretation
                </span>
                <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                  {data.limits_of_interpretation}
                </p>
              </div>
            )}
            {data.suggested_investigation && (
              <div style={{ padding: '0.6rem', background: 'rgba(16, 185, 129, 0.05)', borderRadius: '4px', borderLeft: '3px solid var(--brand-green, #10b981)' }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--brand-green, #10b981)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                  Suggested Operational Investigation
                </span>
                <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                  {data.suggested_investigation}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4. Contributing Source Streams */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h4 style={{ margin: 0, fontSize: '0.84rem', fontWeight: 700, color: 'var(--text-secondary)' }}>
            Contributing Source Observations ({streams.length})
          </h4>
          {data.detector_name && (
            <span className="provenance-detector-pill" title="Detector name and version">
              Detector: <code>{data.detector_name}</code> (v{data.detector_version || '1.0'})
            </span>
          )}
        </div>

        {streams.length === 0 ? (
          <div className="provenance-empty-box" style={{ padding: '1.5rem', textAlign: 'center' }}>
            No source records are linked to this occurrence.
          </div>
        ) : (
          streams.map((stream, idx) => {
            const roleName = stream.role || 'PRIMARY_OBSERVATION';
            const isProd = roleName === 'PRODUCTION_ZERO_OUTPUT_EVENT' || stream.source_table?.includes('production');
            const isEnergy = roleName === 'PROCESS_ENERGY_MEASUREMENT' || stream.source_table?.includes('energy');
            const cardClass = isProd ? 'role-prod' : (isEnergy ? 'role-energy' : '');
            const isExpanded = Boolean(expandedStreams[idx]);
            const viewMode = viewModes[idx] || 'table';

            return (
              <div key={`${stream.source_table}-${stream.source_record_id || idx}`} className={`provenance-stream-detail-card ${cardClass}`}>
                {/* Stream Header */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {streams.length > 1 && (
                      <span className="provenance-stream-index">Stream #{idx + 1}</span>
                    )}
                    <span className="provenance-role-badge">
                      {formatRoleLabel(roleName)}
                    </span>
                    <span className="provenance-table-badge" title="Underlying physical table">
                      <code>{stream.source_table}</code>
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span className={`badge-db-status ${stream.record_status === 'FOUND' ? 'found' : 'missing'}`}>
                      DB: {stream.record_status}
                    </span>
                    <LineageStatusBadge status={stream.lineage_state} isCompact />
                  </div>
                </div>

                {/* Metadata Grid */}
                <div className="provenance-stream-meta-grid">
                  <div className="provenance-meta-item">
                    <span className="provenance-meta-label">Primary Key Record ID</span>
                    <div className="provenance-meta-value">
                      {stream.source_record_id ? (
                        <>
                          <span><code>{stream.source_record_id}</code></span>
                          <CopyButton text={stream.source_record_id} label="Copy" className="btn-copy-mini" />
                        </>
                      ) : (
                        <span className="provenance-val-unavailable">Unavailable</span>
                      )}
                    </div>
                  </div>

                  <div className="provenance-meta-item">
                    <span className="provenance-meta-label">Observation Timestamp</span>
                    <span className="provenance-meta-value">
                      {formatDateTime(stream.reporting_timestamp) || 'Unavailable'}
                    </span>
                  </div>

                  <div className="provenance-meta-item">
                    <span className="provenance-meta-label">Plant Facility</span>
                    <span className="provenance-meta-value">
                      {stream.plant_id || 'N/A'}
                    </span>
                  </div>

                  <div className="provenance-meta-item">
                    <span className="provenance-meta-label">{stream.entity_type === 'METER' ? 'Submeter Entity' : 'Production Line'}</span>
                    <span className="provenance-meta-value">
                      {stream.entity_id ? <code>{stream.entity_id}</code> : 'N/A'}
                    </span>
                  </div>

                  <div className="provenance-meta-item">
                    <span className="provenance-meta-label">Historical Source Revision</span>
                    <div className="provenance-meta-value">
                      {stream.revision_id ? (
                        <>
                          <span><code>{stream.revision_id}</code></span>
                          <CopyButton text={stream.revision_id} label="Copy Rev" className="btn-copy-mini" />
                        </>
                      ) : (
                        <span className="provenance-val-unavailable">
                          {stream.revision_status === 'ORIGINAL_REVISION_UNAVAILABLE' ? 'Original Revision Unavailable' : 'Historical Snapshot'}
                        </span>
                      )}
                    </div>
                  </div>

                  {stream.revision_timestamp && (
                    <div className="provenance-meta-item">
                      <span className="provenance-meta-label">Revision Pinned At</span>
                      <span className="provenance-meta-value">
                        {formatDateTime(stream.revision_timestamp)}
                      </span>
                    </div>
                  )}
                </div>

                {/* Upload History Provenance Block */}
                <div className="provenance-upload-box">
                  <div className="provenance-upload-box-header">
                    <span style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase' }}>
                      Batch Ingestion Provenance (upload_history)
                    </span>
                    {stream.upload ? (
                      <span className="badge-lineage badge-lineage-available" style={{ fontSize: '0.65rem' }}>
                        Batch Verified
                      </span>
                    ) : (
                      <span className="badge-lineage badge-lineage-upload-unavailable" style={{ fontSize: '0.65rem' }}>
                        Historical / Unlinked
                      </span>
                    )}
                  </div>

                  {stream.upload ? (
                    <div className="provenance-upload-grid">
                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Upload Batch ID</span>
                        <div className="provenance-meta-value">
                          <span><code>{stream.upload.upload_id}</code></span>
                          <CopyButton text={stream.upload.upload_id} label="Copy" className="btn-copy-mini" />
                        </div>
                      </div>

                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Source Filename</span>
                        <span className="provenance-meta-value" title={stream.upload.filename}>
                          <code>{stream.upload.filename}</code>
                        </span>
                      </div>

                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Report Type &amp; Format</span>
                        <span className="provenance-meta-value">
                          {stream.upload.report_type} ({stream.upload.file_format})
                        </span>
                      </div>

                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Ingestion Mode &amp; Status</span>
                        <span className="provenance-meta-value">
                          {stream.upload.mode} &bull; {stream.upload.status}
                        </span>
                      </div>

                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Uploaded At</span>
                        <span className="provenance-meta-value">
                          {formatDateTime(stream.upload.uploaded_at)}
                        </span>
                      </div>

                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Batch Rows (Valid / Total)</span>
                        <span className="provenance-meta-value">
                          {formatNumber(stream.upload.valid_rows)} / {formatNumber(stream.upload.total_rows)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      {stream.lineage_note || 'Batch upload metadata is unavailable because this physical record predates upload tracking or was seeded prior to batch audit.'}
                    </div>
                  )}
                </div>

                {/* Current Corrected Reading (Exposed separately when superseded after detection) */}
                {stream.has_newer_revision && stream.current_corrected_reading && (
                  <div className="provenance-corrected-box" style={{ marginTop: '0.85rem', padding: '0.75rem', background: 'rgba(234, 179, 8, 0.06)', border: '1px solid rgba(234, 179, 8, 0.28)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                      <span style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--brand-yellow, #eab308)', textTransform: 'uppercase' }}>
                        Current Corrected Reading (Superseded after Detection)
                      </span>
                      <span className="badge-lineage badge-lineage-legacy" style={{ fontSize: '0.65rem' }}>
                        Replacement Revision Active
                      </span>
                    </div>
                    <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      A replacement revision was ingested for this business key after anomaly detection. The original evidence panel above retains the values and batch used at detection.
                    </p>
                    <div className="provenance-upload-grid">
                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Replacement Revision ID</span>
                        <div className="provenance-meta-value">
                          <span><code>{stream.current_corrected_reading.revision_id}</code></span>
                          <CopyButton text={stream.current_corrected_reading.revision_id} label="Copy" className="btn-copy-mini" />
                        </div>
                      </div>
                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Replacement Upload Batch</span>
                        <div className="provenance-meta-value">
                          <span><code>{stream.current_corrected_reading.upload_id || 'Correction Batch'}</code></span>
                        </div>
                      </div>
                      <div className="provenance-meta-item">
                        <span className="provenance-meta-label">Replacement Timestamp</span>
                        <span className="provenance-meta-value">
                          {formatDateTime(stream.current_corrected_reading.revision_timestamp)}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Expandable Raw Record Viewer */}
                {stream.raw_data && (
                  <div>
                    <button
                      type="button"
                      className="provenance-raw-toggle-btn"
                      onClick={() => handleToggleStream(idx)}
                    >
                      <span>{isExpanded ? '▲ Hide Raw Database Row' : '▼ Inspect Raw Database Row'}</span>
                      <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                        ({Object.keys(stream.raw_data).length} attributes)
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="provenance-raw-drawer">
                        <div className="provenance-raw-drawer-header">
                          <span style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                            Physical PostgreSQL Row: <code>{stream.source_table}</code> ({stream.source_record_id})
                          </span>

                          <div className="provenance-view-mode-pills">
                            <button
                              type="button"
                              className={`provenance-mode-pill ${viewMode === 'table' ? 'active' : ''}`}
                              onClick={() => handleSetViewMode(idx, 'table')}
                            >
                              Table View
                            </button>
                            <button
                              type="button"
                              className={`provenance-mode-pill ${viewMode === 'json' ? 'active' : ''}`}
                              onClick={() => handleSetViewMode(idx, 'json')}
                            >
                              JSON View
                            </button>
                            <CopyButton
                              text={JSON.stringify(stream.raw_data, null, 2)}
                              label="Copy JSON"
                              className="btn-copy-mini"
                            />
                          </div>
                        </div>

                        {viewMode === 'table' ? (
                          <div className="provenance-raw-table-wrap">
                            <table className="provenance-raw-table">
                              <thead>
                                <tr>
                                  <th>Column / Attribute</th>
                                  <th>Database Value</th>
                                </tr>
                              </thead>
                              <tbody>
                                {Object.entries(stream.raw_data).map(([key, val]) => (
                                  <tr key={key}>
                                    <td className="col-name">{key}</td>
                                    <td className="col-val">
                                      {val === null || val === undefined ? (
                                        <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>null</span>
                                      ) : typeof val === 'boolean' ? (
                                        val ? 'true' : 'false'
                                      ) : (
                                        String(val)
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <pre className="provenance-raw-pre">
                            {JSON.stringify(stream.raw_data, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* 5. Footer Metadata: Audit & Storage Details */}
      <div className="provenance-footer-meta">
        <div>
          <label>Audit Persistence:</label>
          <span>Neon PostgreSQL (Append-Only)</span>
        </div>
        <div>
          <label>Query Mechanism:</label>
          <span>Indexed Primary-Key Direct Resolution (No N+1)</span>
        </div>
        <div>
          <label>Retrieved Timestamp:</label>
          <span>{formatDateTime(data.retrieved_at)}</span>
        </div>
      </div>
    </div>
  );
}

