import React, { useEffect, useRef } from 'react';
import { marked } from 'marked';
import ToolEvidenceView from './ToolEvidenceView';

// Configure marked with standard GFM tables and breaks
marked.setOptions({
  gfm: true,
  breaks: true,
});

export default function ConversationView({
  messages = [],
  isLoading = false,
  onSelectSuggestion,
}) {
  const bottomRef = useRef(null);

  // Auto-scroll to latest message or loading state
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

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
            An autonomous conversational agent designed to inspect factory electrical telemetry, compute production energy intensity, and investigate anomalies across manufacturing plants IN-TN-01 and IN-KA-01.
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

          <div className="assistant-notice-banner active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <div>
              <strong>ReAct Agent Active:</strong> Connected to live Domo AI Services and Neon PostgreSQL. Every numerical claim is backed by deterministic analytics tools or read-only SQL queries with a strict 5-tool limit per turn. Select a suggestion below or enter a question to start.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="assistant-messages-list">
      {messages.map((msg) => {
        const isUser = msg.role === 'user';
        const isError = msg.isError;

        return (
          <div
            key={msg.id}
            className={`assistant-message-row ${isUser ? 'user-row' : 'assistant-row'}`}
          >
            <div className={`assistant-bubble ${isUser ? 'user' : 'assistant'} ${isError ? 'error-bubble' : ''}`}>
              <div className="assistant-bubble-header">
                <span className="bubble-author">
                  {isUser ? (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
                        <circle cx="12" cy="7" r="4"/>
                      </svg>
                      <span>You</span>
                    </>
                  ) : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 8V4H8"/>
                        <rect width="16" height="12" x="4" y="8" rx="2"/>
                        <path d="M2 14h2"/>
                        <path d="M20 14h2"/>
                        <path d="M15 13v2"/>
                        <path d="M9 13v2"/>
                      </svg>
                      <span>Energy Intelligence Agent</span>
                    </>
                  )}
                </span>
                <span className="bubble-timestamp">{msg.timestamp}</span>
              </div>

              {isUser ? (
                <div className="assistant-bubble-content user-text">{msg.content}</div>
              ) : (
                <div className="assistant-bubble-content">
                  <div
                    className="assistant-markdown"
                    dangerouslySetInnerHTML={{ __html: marked.parse(msg.content || '') }}
                  />

                  {!isError && (
                    <ToolEvidenceView
                      toolReferences={msg.tool_references || []}
                      toolEvidence={msg.tool_evidence || []}
                      toolCount={msg.tool_count || 0}
                      modelCallCount={msg.model_call_count || 0}
                      executionLimitReached={Boolean(msg.execution_limit_reached)}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}

      {isLoading && (
        <div className="assistant-message-row assistant-row">
          <div className="assistant-bubble assistant loading-bubble">
            <div className="assistant-bubble-header">
              <span className="bubble-author">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 8V4H8"/>
                  <rect width="16" height="12" x="4" y="8" rx="2"/>
                  <path d="M2 14h2"/>
                  <path d="M20 14h2"/>
                </svg>
                <span>Energy Intelligence Agent</span>
              </span>
              <span className="bubble-timestamp">Thinking...</span>
            </div>
            <div className="assistant-loading-indicator">
              <span className="loading-dot" />
              <span className="loading-dot" />
              <span className="loading-dot" />
              <span className="loading-text">Analyzing telemetry and coordinating analytical tools...</span>
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
