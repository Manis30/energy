import React from 'react';

export default function AssistantHeader({ onClearChat, messageCount }) {
  return (
    <div className="assistant-header-card">
      <div className="assistant-header-main">
        <div className="assistant-header-titles">
          <div className="assistant-title-row">
            <div className="assistant-bot-avatar">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 8V4H8"/>
                <rect width="16" height="12" x="4" y="8" rx="2"/>
                <path d="M2 14h2"/>
                <path d="M20 14h2"/>
                <path d="M15 13v2"/>
                <path d="M9 13v2"/>
              </svg>
            </div>
            <h2 className="assistant-title">AI Energy Assistant</h2>
            <span className="assistant-status-badge pending" title="LLM backend integration scheduled for Phase 7">
              <span className="status-dot-pending" />
              Backend integration pending
            </span>
          </div>
          <p className="assistant-subtitle">
            Conversational industrial energy intelligence powered by deterministic calculations and read-only Neon telemetry.
          </p>
        </div>

        {messageCount > 0 && (
          <div className="assistant-header-actions">
            <button
              type="button"
              className="assistant-btn-secondary"
              onClick={onClearChat}
              title="Clear current conversation messages"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18"/>
                <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
                <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
              </svg>
              <span>Clear Chat</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
