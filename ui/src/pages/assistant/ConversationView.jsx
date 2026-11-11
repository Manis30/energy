import React, { useEffect, useRef } from 'react';

export default function ConversationView({ messages, onSelectSuggestion }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="assistant-empty-state">
        <div className="assistant-welcome-card">
          <div className="assistant-welcome-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
          </div>
          <h3 className="assistant-welcome-title">Industrial Energy Intelligence Assistant</h3>
          <p className="assistant-welcome-desc">
            An interactive conversational agent designed to inspect factory electrical telemetry, compute production energy intensity, and investigate anomalies across plants IN-TN-01 and IN-KA-01.
          </p>

          <div className="assistant-capabilities-grid">
            <div className="assistant-cap-item">
              <div className="cap-icon-wrap">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                </svg>
              </div>
              <div className="cap-text">
                <div className="cap-title">Energy & Meter Analytics</div>
                <div className="cap-desc">Query total kWh, peak demand, utility cost, and emissions across meters and plants.</div>
              </div>
            </div>

            <div className="cap-item-spacer" />

            <div className="assistant-cap-item">
              <div className="cap-icon-wrap">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
              </div>
              <div className="cap-text">
                <div className="cap-title">Production & Intensity</div>
                <div className="cap-desc">Analyze kWh/unit for SMT lines, Final Assembly lines, and Aster product variants.</div>
              </div>
            </div>

            <div className="cap-item-spacer" />

            <div className="assistant-cap-item">
              <div className="cap-icon-wrap">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              </div>
              <div className="cap-text">
                <div className="cap-title">Anomaly Surveillance</div>
                <div className="cap-desc">Audit statistical outliers, rolling baseline spikes, and zero-production standby draw.</div>
              </div>
            </div>
          </div>

          <div className="assistant-notice-banner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            <div>
              <strong>Phase 7 Integration Notice:</strong> Full multi-turn reasoning powered by LangChain and Domo AI Services with deterministic tools and read-only database query execution will be activated in the next development phase. Select a question below or enter a prompt to preview the conversation shell.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="assistant-messages-list">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`assistant-message-row ${msg.role === 'user' ? 'user-row' : 'system-row'}`}
        >
          <div className={`assistant-bubble ${msg.role}`}>
            <div className="assistant-bubble-header">
              <span className="bubble-author">
                {msg.role === 'user' ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
                      <circle cx="12" cy="7" r="4"/>
                    </svg>
                    <span>User Query</span>
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 8V4H8"/>
                      <rect width="16" height="12" x="4" y="8" rx="2"/>
                      <path d="M2 14h2"/>
                      <path d="M20 14h2"/>
                    </svg>
                    <span>System Status</span>
                  </>
                )}
              </span>
              <span className="bubble-timestamp">{msg.timestamp}</span>
            </div>
            <div className="assistant-bubble-content">{msg.content}</div>
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
