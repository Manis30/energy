import React, { useEffect, useRef } from 'react';
import { marked } from 'marked';
import ToolEvidenceView from './ToolEvidenceView';

// Configure marked with standard GFM tables and breaks
marked.setOptions({
  gfm: true,
  breaks: true,
});

export default function ConversationView({
  conversationRef,
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
      <div ref={conversationRef} className="assistant-empty-state" role="status" tabIndex={-1}>
        <div className="compact-welcome-box">
          <div className="compact-welcome-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
          </div>
          <h3 className="compact-welcome-title">Ask about your plant's energy</h3>
          <p className="compact-welcome-desc">
            Explore consumption, line intensity, SEC, and anomalies.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="assistant-messages-list"
      ref={conversationRef}
      tabIndex={-1}
      role="log"
      aria-label="Conversation messages"
      aria-live="polite"
      aria-relevant="additions"
    >
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
                      evidenceId={`assistant-evidence-${msg.id}`}
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
