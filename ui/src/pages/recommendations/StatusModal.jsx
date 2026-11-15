import React, { useState, useEffect } from 'react';

/**
 * Modal dialog for transitioning recommendation lifecycle status.
 * Enforces dismissal justification and reopening rationale.
 */
export default function StatusModal({
  isOpen,
  rec,
  targetStatus,
  onClose,
  onSubmit,
  loading = false,
  error = null,
}) {
  const [selectedStatus, setSelectedStatus] = useState(targetStatus || 'DISMISSED');
  const [reason, setReason] = useState('');
  const [callerAttribution, setCallerAttribution] = useState('');
  const [validationError, setValidationError] = useState('');

  useEffect(() => {
    setSelectedStatus(targetStatus || 'DISMISSED');
    setReason('');
    setCallerAttribution('');
    setValidationError('');
  }, [isOpen, targetStatus]);

  if (!isOpen || !rec) return null;

  const isDismissing = selectedStatus === 'DISMISSED';
  const isReopening = (rec.status === 'DISMISSED' || rec.status === 'IMPLEMENTED') &&
    (selectedStatus === 'OPEN' || selectedStatus === 'IN_PROGRESS');

  const handleSubmit = (e) => {
    e.preventDefault();
    setValidationError('');

    if (isDismissing && !reason.trim()) {
      setValidationError('A reason for dismissal is required.');
      return;
    }

    if (isReopening && !reason.trim()) {
      setValidationError('A justification for reopening is required.');
      return;
    }

    onSubmit({
      status: selectedStatus,
      reason: reason.trim() || undefined,
      caller_attribution: callerAttribution.trim() || undefined,
    });
  };

  return (
    <div className="recommendations-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="status-modal-title">
      <div className="recommendations-modal">
        <header className="recommendations-modal-header">
          <h3 id="status-modal-title">
            {isDismissing ? 'Dismiss Recommendation' : isReopening ? 'Reopen Recommendation' : `Transition to ${selectedStatus}`}
          </h3>
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
              <label>Target Lifecycle Status</label>
              {isReopening ? (
                <select
                  value={selectedStatus}
                  onChange={(e) => setSelectedStatus(e.target.value)}
                  disabled={loading}
                >
                  <option value="IN_PROGRESS">IN_PROGRESS (Resume Active Investigation)</option>
                  <option value="OPEN">OPEN (Queue for Evaluation)</option>
                </select>
              ) : (
                <input
                  type="text"
                  value={selectedStatus}
                  disabled
                  readOnly
                  style={{ opacity: 0.8 }}
                />
              )}
            </div>

            <div className="recommendations-modal-field">
              <label>
                {isDismissing ? 'Reason for Dismissal *' : isReopening ? 'Reopen Justification *' : 'Transition Comment (Optional)'}
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={
                  isDismissing
                    ? 'State the technical, operational, or economic justification for dismissal...'
                    : isReopening
                    ? 'State why this recommendation is being reopened (e.g. process changes, budget approved)...'
                    : 'Add operational context for this lifecycle transition...'
                }
                disabled={loading}
                rows={3}
                required={isDismissing || isReopening}
              />
              <span className="recommendations-modal-disclaimer">
                {isDismissing
                  ? 'This reason will be immutably preserved in the audit log even if the recommendation is reopened later.'
                  : isReopening
                  ? 'Reopening will reactivate the recommendation while preserving previous dismissal reasons in audit history.'
                  : 'Recorded as an append-only audit event.'}
              </span>
            </div>

            <div className="recommendations-modal-field">
              <label>Caller Attribution (Optional)</label>
              <input
                type="text"
                value={callerAttribution}
                onChange={(e) => setCallerAttribution(e.target.value)}
                placeholder="e.g. Plant Electrical Lead, Shift Supervisor"
                disabled={loading}
                maxLength={100}
              />
              <span className="recommendations-modal-disclaimer">
                Attribution is classified as an UNVERIFIED CALLER label; not an authenticated identity.
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
              className={`btn-rec ${isDismissing ? 'btn-rec-danger' : isReopening ? 'btn-rec-primary' : 'btn-rec-success'}`}
              disabled={loading}
            >
              {loading ? 'Processing…' : isDismissing ? 'Confirm Dismissal' : isReopening ? 'Confirm Reopen' : 'Update Status'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

