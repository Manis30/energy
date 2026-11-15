import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatDate } from '../../utils/formatters';

export default function IngestionActionSection({
  validationResult,
  confirmedDate,
  onIngest,
  ingesting,
  ingestResult,
}) {
  const navigate = useNavigate();
  const [mode, setMode] = useState('INCREMENTAL'); // 'INCREMENTAL' | 'OVERWRITE_CORRECTION'
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  if (!validationResult) return null;

  const { summary } = validationResult;
  const isReady = summary && summary.valid_rows > 0;

  const handleStartIngest = () => {
    setShowConfirmModal(true);
  };

  const handleConfirmIngest = () => {
    setShowConfirmModal(false);
    onIngest(mode);
  };

  const handleNavigateToAnalysis = () => {
    const targetDate = ingestResult?.reporting_date || confirmedDate;
    navigate(`/daily-analysis?date=${targetDate}`);
  };

  return (
    <div className="reports-section-card">
      <div className="reports-card-header">
        <div>
          <h2 className="reports-card-title">3. Database Ingestion & Historical Integrity</h2>
          <p className="reports-card-subtitle">
            Configure idempotency mode, execute transactional commit to Neon PostgreSQL, and update audit trail.
          </p>
        </div>
      </div>

      {/* Mode Selection Cards */}
      <div className="reports-mode-grid">
        <div
          className={`reports-mode-card ${mode === 'INCREMENTAL' ? 'selected' : ''}`}
          onClick={() => setMode('INCREMENTAL')}
        >
          <div className="mode-radio">
            <span className={`radio-dot ${mode === 'INCREMENTAL' ? 'checked' : ''}`} />
          </div>
          <div className="mode-details">
            <div className="mode-title">
              Incremental Import
              <span className="mode-badge-rec">Recommended</span>
            </div>
            <div className="mode-desc">
              Preserves existing historical data. Inserts only new validated records. Automatically skips duplicate records matching existing business keys.
            </div>
          </div>
        </div>

        <div
          className={`reports-mode-card ${mode === 'OVERWRITE_CORRECTION' ? 'selected' : ''}`}
          onClick={() => setMode('OVERWRITE_CORRECTION')}
        >
          <div className="mode-radio">
            <span className={`radio-dot ${mode === 'OVERWRITE_CORRECTION' ? 'checked' : ''}`} />
          </div>
          <div className="mode-details">
            <div className="mode-title">
              Historical Correction / Overwrite
              <span className="mode-badge-warn">Audit Tracked</span>
            </div>
            <div className="mode-desc">
              Explicit correction process. Replaces ONLY existing records matching the incoming {summary.report_type === 'ENERGY' ? '(timestamp, plant, meter)' : '(event_ts, plant, line)'} keys. Hours and entities not present in this upload remain safely preserved.
            </div>
          </div>
        </div>
      </div>

      {/* Action Row */}
      <div className="reports-ingest-action-box">
        <div className="ingest-info-text">
          {isReady ? (
            <span>
              Target: <strong>{summary.valid_rows} valid records</strong> ready to be ingested for{' '}
              <strong>{formatDate(confirmedDate)}</strong> ({summary.report_type}).
            </span>
          ) : (
            <span style={{ color: 'var(--status-danger)' }}>
              No valid records available to ingest. Resolve validation issues above.
            </span>
          )}
        </div>

        <button
          type="button"
          className="reports-confirm-ingest-btn"
          disabled={!isReady || ingesting}
          onClick={handleStartIngest}
        >
          {ingesting ? (
            <>
              <span className="btn-spinner" />
              Writing Transactionally to PostgreSQL...
            </>
          ) : (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>
              Confirm & Ingest {summary.valid_rows} Records
            </>
          )}
        </button>
      </div>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="reports-modal-overlay">
          <div className="reports-modal-card">
            <div className="modal-header">
              <div className="modal-title">Confirm Database Ingestion</div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setShowConfirmModal(false)}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p>
                You are about to ingest <strong>{summary.valid_rows} records</strong> into{' '}
                <code>{summary.report_type === 'ENERGY' ? 'fact_energy_meter_hourly' : 'fact_hourly_production'}</code>{' '}
                for reporting date <strong>{formatDate(confirmedDate)}</strong>.
              </p>
              <div className="modal-mode-warning">
                <strong>Ingestion Mode:</strong>{' '}
                {mode === 'INCREMENTAL' ? (
                  <span>Incremental Import — Existing records will be preserved; duplicates skipped.</span>
                ) : (
                  <span style={{ color: 'var(--status-warning)' }}>
                    Historical Correction — Only existing records matching the specific incoming business keys ({summary.report_type === 'ENERGY' ? 'timestamp, plant, meter' : 'event timestamp, plant, line'}) will be replaced! Other hours and entities on this date are preserved.
                  </span>
                )}
              </div>
              {summary.coverage_status === 'PARTIAL' && (
                <div style={{ marginTop: '0.75rem', padding: '0.6rem 0.8rem', backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid var(--status-warning)', borderRadius: '6px', fontSize: '0.82rem', color: 'var(--status-warning)' }}>
                  <strong>Partial Day Coverage Warning:</strong> This report covers {summary.completeness?.hours_reported || 0} of 24 hours ({summary.missing_hours?.length || 0} hours missing). Resulting analytics will represent partial-day telemetry.
                </div>
              )}
              <p style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                This operation is atomic and logged in the platform audit trail.
              </p>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="reports-secondary-btn"
                onClick={() => setShowConfirmModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="reports-confirm-ingest-btn"
                onClick={handleConfirmIngest}
              >
                Proceed with Ingestion
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Post-Ingestion Success Card */}
      {ingestResult && (
        <div className="reports-success-card">
          <div className="success-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div className="success-content">
            <div className="success-title">Database Ingestion Completed Successfully!</div>
            <div className="success-details">
              {ingestResult.message}
            </div>
            <div className="success-meta">
              <span>Upload ID: <code>{ingestResult.upload_id}</code></span>
              <span>Reporting Date: <strong>{formatDate(ingestResult.reporting_date)}</strong></span>
              <span>Imported: <strong>{ingestResult.imported_rows} rows</strong></span>
              {ingestResult.replaced_rows > 0 && (
                <span>Replaced: <strong>{ingestResult.replaced_rows} records</strong></span>
              )}
              {ingestResult.duplicate_rows > 0 && (
                <span>Duplicates: <strong>{ingestResult.duplicate_rows} rows</strong></span>
              )}
            </div>
            {ingestResult.affected_scope && (
              <div style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Scoped to {ingestResult.affected_scope.plants?.length || 0} plant(s), {ingestResult.affected_scope.meters?.length || ingestResult.affected_scope.lines?.length || 0} {ingestResult.report_type === 'ENERGY' ? 'meters' : 'lines'}, and {ingestResult.affected_scope.hours_covered?.length || 0} operating hours.
              </div>
            )}
            <div className="success-action-row">
              <button
                type="button"
                className="reports-primary-btn"
                onClick={handleNavigateToAnalysis}
              >
                View Date in Daily Analysis
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginLeft: '6px' }}>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                  <polyline points="12 5 19 12 12 19"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

