import React, { useRef, useEffect } from 'react';
import SuggestedQuestions from './SuggestedQuestions';

const MAX_CHARS = 2000;

export default function MessageComposer({
  input,
  setInput,
  onSendMessage,
  onSelectSuggestion,
  disabled = false,
  showSuggestions = false,
  setShowSuggestions,
}) {
  const textareaRef = useRef(null);

  // Auto-resize textarea to content height (up to max 120px)
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 120)}px`;
    }
  }, [input]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const trimmed = (input || '').trim();
    if (!trimmed || trimmed.length > MAX_CHARS || disabled) return;
    if (showSuggestions && setShowSuggestions) {
      setShowSuggestions(false);
    }
    onSendMessage(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleInputChange = (e) => {
    setInput(e.target.value);
    // Keep suggestions closed while user types
    if (showSuggestions && setShowSuggestions) {
      setShowSuggestions(false);
    }
  };

  const handleInputFocus = () => {
    // Prevent suggestions panel from blocking composer interaction
    if (showSuggestions && setShowSuggestions) {
      setShowSuggestions(false);
    }
  };

  const trimmedLength = (input || '').trim().length;
  const isSendDisabled = trimmedLength === 0 || trimmedLength > MAX_CHARS || disabled;
  const showCharWarning = (input || '').length > 1500;

  return (
    <div className="assistant-composer-wrapper">
      <div className={`assistant-composer-box ${disabled ? 'disabled' : ''}`}>
        <textarea
          ref={textareaRef}
          className="assistant-textarea"
          aria-label="Message to AI Assistant"
          value={input}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Waiting for assistant response...' : 'Ask about plant energy, line intensity, anomalies, or shift performance...'}
          rows={1}
          maxLength={MAX_CHARS}
          disabled={disabled}
          aria-describedby="assistant-composer-hints"
        />
        <button
          type="button"
          className="assistant-send-btn"
          onClick={handleSubmit}
          disabled={isSendDisabled}
          aria-label="Send message"
          title={isSendDisabled ? 'Type a question to send' : 'Send message (Enter)'}
        >
          {disabled ? (
            <svg className="composer-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          )}
        </button>
      </div>

      <div className="assistant-composer-meta-row">
        <div className="composer-meta-left">
          <SuggestedQuestions
            isOpen={showSuggestions}
            onToggle={() => setShowSuggestions && setShowSuggestions((prev) => !prev)}
            onClose={() => setShowSuggestions && setShowSuggestions(false)}
            onSelectQuestion={onSelectSuggestion || onSendMessage}
            disabled={disabled}
          />
        </div>
        <div className="composer-meta-hints" id="assistant-composer-hints">
          <span>Enter to send</span>
          <span className="meta-dot">&bull;</span>
          <span>Shift+Enter for newline</span>
          <span className="meta-dot">&bull;</span>
          <span className="assistant-safe-notice">Read-only SQL telemetry</span>
          {showCharWarning && (
            <>
              <span className="meta-dot">&bull;</span>
              <span className={`char-counter ${trimmedLength >= MAX_CHARS ? 'limit' : ''}`}>
                {trimmedLength} / {MAX_CHARS}
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
