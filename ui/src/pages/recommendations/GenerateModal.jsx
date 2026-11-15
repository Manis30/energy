import React, { useState, useEffect } from 'react';
import { findingsApi } from '../../services/findingsApi';
import { formatDateTime } from '../../utils/formatters';

/**
 * Modal dialog for deterministically generating recommendations from existing operational findings.
 */
export default function GenerateModal({
  isOpen,
  prefillFindingId = '',
  onClose,
  onSubmit,
  loading = false,
  error = null,
}) {
  const [findingId, setFindingId] = useState(prefillFindingId || '');
  const [callerAttribution, setCallerAttribution] = useState('');
  const [recentFindings, setRecentFindings] = useState([]);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [validationError, setValidationError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setFindingId(prefillFindingId || '');
      setCallerAttribution('');
      setValidationError('');
      loadRecentFindings();
    }
  }, [isOpen, prefillFindingId]);

  const loadRecentFindings = async () => {
    setLoadingFindings(true);
    try {
      const res = await findingsApi.listFindings({ limit: 10 });
      setRecentFindings(res.items || []);
    } catch {
      // Non-critical helper, ignore error
      setRecentFindings([]);
    } finally {
      setLoadingFindings(false);
    }
  };

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setValidationError('');

    const cleanId = findingId.trim();
    if (!cleanId) {
      setValidationError('Please specify an operational finding ID.');
      return;
    }

    onSubmit({
      finding_id: cleanId,
      caller_attribution: callerAttribution.trim() || undefined,
    });
  };

  return (
    <div className="recommendations-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="generate-modal-title">
      <div className="recommendations-modal" style={{ maxWidth: '620px' }}>
        <header className="recommendations-modal-header">
          <h3 id="generate-modal-title">Generate Recommendations from Finding</h3>
          <button
            type="button"
            className="btn-drawer-close"
            onClick={onClose}
            disabled={loading}
            aria-label="Close dialog"
          >
            ×
          </button>
        </header>

        <form onSubmit={handleSubmit}>
          <div className="recommendations-modal-body">
            {error && (
              <div className="recommendations-banner-alert error">
                <span>{error}</span>
              </div>
            )}
            {validationError && (
              <div className="recommendations-banner-alert error">
                <span>{validationError}</span>
              </div>
            )}

            <div className="recommendations-modal-field">
              <label>Operational Finding ID *</label>
              <input
                type="text"
                value={findingId}
                onChange={(e) => setFindingId(e.target.value)}
                placeholder="e.g. FND-PLANT-01-A1B2C3D4E5"
                disabled={loading}
                required
              />
              <span className="recommendations-modal-disclaimer">
                The generator evaluates finding telemetry, anomaly type, meter/line scope, and lineage without fabricating financial savings.
              </span>
            </div>

            {/* Quick picker from recent findings */}
            <div className="recommendations-modal-field">
              <label style={{ color: 'var(--text-secondary)', fontSize: '0.72rem' }}>
                Or select from recent findings:
              </label>
              {loadingFindings ? (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Loading recent findings…</div>
              ) : recentFindings.length === 0 ? (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>No recent findings available.</div>
              ) : (
                <div style={{ maxHeight: '140px', overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}>
                  {recentFindings.map((f) => (
                    <div
                      key={f.finding_id}
                      onClick={() => setFindingId(f.finding_id)}
                      style={{
                        padding: '0.45rem 0.65rem',
                        borderBottom: '1px solid var(--border-color)',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: findingId === f.finding_id ? 'var(--bg-hover)' : 'transparent',
                      }}
                    >
                      <div>
                        <strong>{f.finding_id}</strong>
                        <span style={{ marginLeft: '0.5rem', color: 'var(--text-secondary)' }}>
                          {(f.anomaly_type || '').replace(/_/g, ' ')}
                        </span>
                      </div>
                      <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                        {f.plant_id} · {formatDateTime(f.last_detected_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="recommendations-modal-field">
              <label>Caller Attribution (Optional)</label>
              <input
                type="text"
                value={callerAttribution}
                onChange={(e) => setCallerAttribution(e.target.value)}
                placeholder="e.g. Engineer Jane, Automation Runner"
                disabled={loading}
                maxLength={100}
              />
              <span className="recommendations-modal-disclaimer">
                Classified as unverified caller attribution in audit logs.
              </span>
            </div>
          </div>

          <footer className="recommendations-modal-footer">
            <button
              type="button"
              className="btn-rec btn-rec-secondary"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-rec btn-rec-primary"
              disabled={loading}
            >
              {loading ? 'Generating…' : 'Generate Recommendation'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

