import React, { useState } from 'react';
import { formatDateTime } from '../../utils/formatters';

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
 * Returns: 'AVAILABLE' | 'MULTI_SOURCE' | 'LEGACY' | 'UNAVAILABLE'
 */
export function getLineageStatus(occ) {
  if (!occ) return 'UNAVAILABLE';

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
    // If source table and record ID are present but upload_id is null, it's historical/legacy
    return hasUploadId ? 'AVAILABLE' : 'LEGACY';
  }

  // Check single item in source_records array
  if (Array.isArray(occ.source_records) && occ.source_records.length === 1) {
    const single = occ.source_records[0];
    if (single.source_table && single.source_record_id) {
      return single.upload_id ? 'AVAILABLE' : 'LEGACY';
    }
  }

  if (occ.lineage_status === 'AVAILABLE') {
    return hasUploadId ? 'AVAILABLE' : 'LEGACY';
  }

  return 'UNAVAILABLE';
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
    default:
      return role.replace(/_/g, ' ');
  }
}

/**
 * Badge indicating deterministic lineage status.
 */
export function LineageStatusBadge({ status, streamCount = 0, isCompact = false }) {
  let badgeClass = 'badge-lineage badge-lineage-unavailable';
  let label = 'Lineage Unavailable';
  let title = 'Source record identity could not be resolved from telemetry records';

  switch (status) {
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
    case 'LEGACY':
      badgeClass = 'badge-lineage badge-lineage-legacy';
      label = isCompact ? 'Legacy Upload' : 'Legacy Record (Unattributed Upload)';
      title = 'Historical sensor record; row ID resolved, but batch upload metadata was not tracked prior to Phase 10';
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

