import React, { useState, useEffect } from 'react';
import { formatDateTime } from '../../utils/formatters';
import { recommendationsApi } from '../../services/recommendationsApi';

// Permitted state transitions for Corrective Actions matching backend validation
const VALID_ACTION_TRANSITIONS = {
  OPEN: [
    { value: 'OPEN', label: 'OPEN (Task queued)' },
    { value: 'IN_PROGRESS', label: 'IN_PROGRESS (Task underway)' },
    { value: 'COMPLETED', label: 'COMPLETED (Task executed)' },
    { value: 'CANCELLED', label: 'CANCELLED (Task revoked / redundant)' },
  ],
  IN_PROGRESS: [
    { value: 'IN_PROGRESS', label: 'IN_PROGRESS (Task underway)' },
    { value: 'COMPLETED', label: 'COMPLETED (Task executed)' },
    { value: 'CANCELLED', label: 'CANCELLED (Task revoked / redundant)' },
    { value: 'OPEN', label: 'OPEN (Queue back to open)' },
  ],
  COMPLETED: [
    { value: 'COMPLETED', label: 'COMPLETED (Currently executed)' },
    { value: 'OPEN', label: 'OPEN (Reopen action)' },
    { value: 'IN_PROGRESS', label: 'IN_PROGRESS (Reopen & resume investigation)' },
  ],
  CANCELLED: [
    { value: 'CANCELLED', label: 'CANCELLED (Currently revoked)' },
    { value: 'OPEN', label: 'OPEN (Reopen action)' },
    { value: 'IN_PROGRESS', label: 'IN_PROGRESS (Reopen & resume investigation)' },
  ],
};

/**
 * Modal dialog for creating and updating corrective actions.
 * Enforces unauthenticated free-text owner assignment, due date management,
 * and decoupling of action completion from recommendation completion.
 */
export default function ActionModal({
  isOpen,
  mode = 'create',
  recId,
  action = null,
  parentRec = null,
  onClose,
  onSubmit,
  loading = false,
  error = null,
}) {
  const [activeTab, setActiveTab] = useState('form'); // 'form' | 'audit'
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('OPEN');
  const [owner, setOwner] = useState('');
  const [clearOwner, setClearOwner] = useState(false);
  const [dueDate, setDueDate] = useState('');
  const [clearDueDate, setClearDueDate] = useState(false);
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [callerAttribution, setCallerAttribution] = useState('');
  const [validationError, setValidationError] = useState('');
  const [liveAuditLogs, setLiveAuditLogs] = useState(null);
  const [refreshingAudit, setRefreshingAudit] = useState(false);

  useEffect(() => {
    setActiveTab('form');
    setValidationError('');

    if (mode === 'edit' && action) {
      setTitle(action.title || '');
      setDescription(action.description || '');
      setStatus(action.status || 'OPEN');
      setOwner(action.owner || '');
      setClearOwner(false);
      // Format YYYY-MM-DD for date input
      const rawDue = action.due_date ? action.due_date.substring(0, 10) : '';
      setDueDate(rawDue);
      setClearDueDate(false);
      setResolutionNotes(action.resolution_notes || '');
      setCallerAttribution('');
    } else {
      setTitle('');
      setDescription('');
      setStatus('OPEN');
      setOwner('');
      setClearOwner(false);
      setDueDate('');
      setClearDueDate(false);
      setResolutionNotes('');
      setCallerAttribution('');
    }
  }, [isOpen, mode, action]);

  const fetchActionAudit = async () => {
    if (!action?.action_id || refreshingAudit) return;
    setRefreshingAudit(true);
    try {
      const logs = await recommendationsApi.getActionAudit(action.action_id);
      setLiveAuditLogs(logs);
    } catch (err) {
      console.warn('Failed to fetch action audit trail:', err);
    } finally {
      setRefreshingAudit(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'audit' && mode === 'edit' && action?.action_id) {
      fetchActionAudit();
    }
  }, [activeTab]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setValidationError('');

    if (!title.trim() || title.trim().length < 3) {
      setValidationError('Action title must be at least 3 characters.');
      return;
    }

    if (!description.trim() || description.trim().length < 3) {
      setValidationError('Action description must be at least 3 characters.');
      return;
    }

    if (mode === 'create') {
      onSubmit({
        title: title.trim(),
        description: description.trim(),
        owner: owner.trim() || undefined,
        due_date: dueDate ? `${dueDate}T00:00:00` : undefined,
        caller_attribution: callerAttribution.trim() || undefined,
      });
    } else {
      const payload = {
        title: title.trim(),
        description: description.trim(),
        status,
        caller_attribution: callerAttribution.trim() || undefined,
      };

      if (clearOwner) {
        payload.clear_owner = true;
      } else if (owner.trim() !== (action?.owner || '')) {
        payload.owner = owner.trim() || undefined;
      }

      if (clearDueDate) {
        payload.clear_due_date = true;
      } else if (dueDate) {
        payload.due_date = `${dueDate}T00:00:00`;
      }

      if (resolutionNotes.trim() !== (action?.resolution_notes || '')) {
        payload.resolution_notes = resolutionNotes.trim() || undefined;
      }

      onSubmit(payload);
    }
  };

  const effectiveAuditTrail = liveAuditLogs || action?.audit_trail || [];

  return (
    <div className="recommendations-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="action-modal-title">
      <div className="recommendations-modal" style={{ maxWidth: '640px' }}>
        <header className="recommendations-modal-header">
          <div>
            <h3 id="action-modal-title">
              {mode === 'create' ? 'Create Corrective Action' : `Update Action: ${action?.action_id || ''}`}
            </h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginTop: '0.2rem', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Parent Recommendation: <strong style={{ fontFamily: 'monospace' }}>{recId || action?.recommendation_id}</strong>
              </span>
              {parentRec?.status && (
                <span className={`badge-status ${parentRec.status.toLowerCase()}`}>
                  Parent: {parentRec.status}
                </span>
              )}
              {parentRec?.priority && (
                <span className={`badge-priority ${parentRec.priority.toLowerCase()}`} title="Recommendation Operational Priority">
                  Rec Priority: {parentRec.priority}
                </span>
              )}
            </div>
            {parentRec?.title && (
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                {parentRec.title}
              </div>
            )}
          </div>
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

        {mode === 'edit' && (
          <div style={{ display: 'flex', gap: '0.5rem', padding: '0.6rem 1.4rem 0', borderBottom: '1px solid var(--border-color)' }}>
            <button
              type="button"
              className={`recommendations-drawer-tab-btn ${activeTab === 'form' ? 'active' : ''}`}
              onClick={() => setActiveTab('form')}
            >
              Action Details
            </button>
            <button
              type="button"
              className={`recommendations-drawer-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
              onClick={() => setActiveTab('audit')}
            >
              Audit History ({effectiveAuditTrail.length})
            </button>
          </div>
        )}

        {activeTab === 'form' ? (
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
                <label>Action Title *</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Inspect APFC capacitor bank relay contacts"
                  disabled={loading}
                  required
                  maxLength={200}
                />
              </div>

              <div className="recommendations-modal-field">
                <label>Description &amp; Operational Steps *</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe specific engineering or operational steps to resolve this finding..."
                  disabled={loading}
                  rows={3}
                  required
                />
              </div>

              {mode === 'edit' && (
                <div className="recommendations-modal-field">
                  <label>Lifecycle Status</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    disabled={loading}
                  >
                    {(VALID_ACTION_TRANSITIONS[action?.status || 'OPEN'] || VALID_ACTION_TRANSITIONS.OPEN).map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <span className="recommendations-modal-disclaimer">
                    Note: Marking this action completed does NOT mark the parent recommendation as implemented. Permitted transitions strictly adhere to backend lifecycle rules.
                  </span>
                </div>
              )}

              <div className="recommendations-modal-field">
                <label>Assigned Owner / Team (Free-Text Label)</label>
                <input
                  type="text"
                  value={owner}
                  onChange={(e) => {
                    setOwner(e.target.value);
                    if (clearOwner) setClearOwner(false);
                  }}
                  placeholder="e.g. Electrical Maintenance Team, Shift Tech"
                  disabled={loading || clearOwner}
                  maxLength={100}
                />
                {mode === 'edit' && action?.owner && (
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', marginTop: '0.2rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={clearOwner}
                      onChange={(e) => {
                        setClearOwner(e.target.checked);
                        if (e.target.checked) setOwner('');
                      }}
                      disabled={loading}
                    />
                    Clear assigned owner (unassign)
                  </label>
                )}
                <span className="recommendations-modal-disclaimer">
                  Unauthenticated free-text assignment; no fake user accounts are required.
                </span>
              </div>

              <div className="recommendations-modal-field">
                <label>Target Due Date (Optional)</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => {
                    setDueDate(e.target.value);
                    if (clearDueDate) setClearDueDate(false);
                  }}
                  disabled={loading || clearDueDate}
                />
                {mode === 'edit' && action?.due_date && (
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', marginTop: '0.2rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={clearDueDate}
                      onChange={(e) => {
                        setClearDueDate(e.target.checked);
                        if (e.target.checked) setDueDate('');
                      }}
                      disabled={loading}
                    />
                    Clear target due date
                  </label>
                )}
              </div>

              {mode === 'edit' && (
                <div className="recommendations-modal-field">
                  <label>Resolution Notes / Progress Documentation</label>
                  <textarea
                    value={resolutionNotes}
                    onChange={(e) => setResolutionNotes(e.target.value)}
                    placeholder="Document task outcome, test readings, work orders, or resolution findings..."
                    disabled={loading}
                    rows={2}
                  />
                </div>
              )}

              <div className="recommendations-modal-field">
                <label>Caller Attribution (Optional)</label>
                <input
                  type="text"
                  value={callerAttribution}
                  onChange={(e) => setCallerAttribution(e.target.value)}
                  placeholder="e.g. Operator Mike, Maintenance Lead"
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
                {loading ? 'Saving…' : mode === 'create' ? 'Create Action' : 'Save Changes'}
              </button>
            </footer>
          </form>
        ) : (
          <div className="recommendations-modal-body" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                Immutable historical event records for this corrective action.
              </span>
              <button
                type="button"
                className="btn-rec btn-rec-secondary btn-rec-sm"
                onClick={fetchActionAudit}
                disabled={refreshingAudit}
                title="Fetch latest action audit trail from server"
              >
                {refreshingAudit ? 'Refreshing…' : '↻ Refresh Audit'}
              </button>
            </div>

            {effectiveAuditTrail.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: '2rem 1rem' }}>
                No audit log records found for this action.
              </div>
            ) : (
              <table className="recommendations-table" style={{ fontSize: '0.75rem' }}>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Transition</th>
                    <th>Attribution</th>
                    <th>Notes / Comment</th>
                    <th>Changed Fields</th>
                  </tr>
                </thead>
                <tbody>
                  {effectiveAuditTrail.map((entry) => {
                    const changed = entry.changed_fields || {};
                    const hasChanges = Object.keys(changed).length > 0;
                    return (
                      <tr key={entry.audit_id || entry.id}>
                        <td style={{ whiteSpace: 'nowrap' }}>{formatDateTime(entry.performed_at)}</td>
                        <td><strong>{entry.action}</strong></td>
                        <td>
                          {entry.from_status
                            ? `${entry.from_status} → ${entry.to_status}`
                            : entry.to_status || '—'}
                        </td>
                        <td>
                          <span
                            className={`badge-actor ${entry.actor_type === 'SYSTEM_AUTOMATION' ? 'system' : 'unverified'}`}
                            title="Unverified client attribution; not an authenticated identity"
                          >
                            {entry.actor_attribution ? `${entry.actor_type}: ${entry.actor_attribution}` : entry.actor_type}
                          </span>
                        </td>
                        <td style={{ maxWidth: '180px' }}>{entry.comment || '—'}</td>
                        <td style={{ maxWidth: '180px', fontSize: '0.72rem' }}>
                          {hasChanges ? (
                            <table className="audit-diff-table">
                              <tbody>
                                {Object.entries(changed).map(([key, diff]) => (
                                  <tr key={key}>
                                    <td style={{ color: 'var(--text-muted)' }}>{key}:</td>
                                    <td>{String(diff?.old ?? 'null')} → {String(diff?.new ?? 'null')}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            <footer className="recommendations-modal-footer" style={{ marginTop: '1rem', background: 'transparent' }}>
              <button
                type="button"
                className="btn-rec btn-rec-secondary"
                onClick={onClose}
              >
                Close
              </button>
            </footer>
          </div>
        )}
      </div>
    </div>
  );
}

