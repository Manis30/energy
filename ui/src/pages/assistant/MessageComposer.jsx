import React, { useRef, useEffect } from 'react';

export default function MessageComposer({ input, setInput, onSendMessage, disabled = false }) {
  const textareaRef = useRef(null);

  // Auto-resize textarea to content height (up to max 160px)
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!input || !input.trim() || disabled) return;
    onSendMessage(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const isSendDisabled = !input || !input.trim() || disabled;

  return (
    <div className="assistant-composer-wrapper">
      <div className="assistant-composer-box">
        <textarea
          ref={textareaRef}
          className="assistant-textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about plant energy, line intensity, anomalies, or shift performance..."
          rows={1}
          disabled={disabled}
        />
        <button
          type="button"
          className="assistant-send-btn"
          onClick={handleSubmit}
          disabled={isSendDisabled}
          aria-label="Send message"
          title={isSendDisabled ? 'Type a question to send' : 'Send message (Enter)'}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <div className="assistant-composer-hints">
        <span>Enter to send &bull; Shift + Enter for new line</span>
        <span className="assistant-safe-notice">Read-only SQL telemetry access &bull; Non-destructive</span>
      </div>
    </div>
  );
}
