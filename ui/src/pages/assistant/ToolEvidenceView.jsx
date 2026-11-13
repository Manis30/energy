import React, { useState } from 'react';

export default function ToolEvidenceView({
  evidenceId = 'assistant-evidence-details',
  toolReferences = [],
  toolEvidence = [],
  toolCount = 0,
  modelCallCount = 0,
  executionLimitReached = false,
}) {
  const [isOpen, setIsOpen] = useState(false);

  // If no tools were executed for this answer
  if (!toolCount || toolCount === 0) {
    return (
      <div className="assistant-evidence-empty-note">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
        <span>Direct domain synthesis &bull; No database analytics tools executed for this response</span>
      </div>
    );
  }

  return (
    <div className={`assistant-evidence-card ${isOpen ? 'open' : ''}`}>
      <button
        type="button"
        className="assistant-evidence-header"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-controls={evidenceId}
      >
        <div className="evidence-header-left">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 18 22 12 16 6"/>
            <polyline points="8 6 2 12 8 18"/>
          </svg>
          <span className="evidence-title">Analytics evidence</span>
          <span className="evidence-count-badge">
            {toolCount} {toolCount === 1 ? 'tool executed' : 'tools executed'}
          </span>
          {executionLimitReached && (
            <span className="evidence-limit-badge" title="Maximum 5 tool executions per turn reached">
              Limit Reached (5/5)
            </span>
          )}
        </div>

        <div className="evidence-header-right">
          <span className="evidence-toggle-hint">{isOpen ? 'Hide details' : 'View telemetry tools'}</span>
          <svg
            className={`evidence-chevron ${isOpen ? 'rotated' : ''}`}
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </button>

      <div id={evidenceId} className="assistant-evidence-body" hidden={!isOpen}>
          <div className="evidence-steps-list">
            {toolEvidence.length === 0 && (
              <p className="evidence-unavailable">
                Execution details are unavailable for this response.
              </p>
            )}
            {toolEvidence.map((ev, idx) => (
              <div key={idx} className={`evidence-step-item ${ev.success ? 'success' : 'failed'}`}>
                <div className="evidence-step-header">
                  <div className="evidence-step-order">Step {ev.execution_order}</div>
                  <code className="evidence-tool-name">{ev.tool_name}</code>
                  <span className={`evidence-status-pill ${ev.success ? 'success' : 'failed'}`}>
                    {ev.success ? (
                      <>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                        Success
                      </>
                    ) : (
                      <>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18"/>
                          <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                        Failed
                      </>
                    )}
                  </span>
                </div>

                {ev.summary && (
                  <div className="evidence-summary-text">
                    {ev.summary}
                  </div>
                )}
                {!ev.success && !ev.summary && (
                  <div className="evidence-summary-text">
                    The tool did not return a result.
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="evidence-footer-metrics">
            <div className="evidence-metric">
              <span className="metric-label">Reasoning Calls:</span>
              <span className="metric-val">{modelCallCount}</span>
            </div>
            <div className="evidence-metric">
              <span className="metric-label">Tools Executed:</span>
              <span className="metric-val">{toolCount} / 5</span>
            </div>
            {toolReferences && toolReferences.length > 0 && (
              <div className="evidence-metric">
                <span className="metric-label">Citations:</span>
                <span className="metric-val citations">{toolReferences.join(', ')}</span>
              </div>
            )}
          </div>
        </div>
    </div>
  );
}
