import React, { useRef, useEffect } from 'react';

const SUGGESTED_QUESTIONS = [
  'What is our total energy consumption?',
  'Compare energy consumption between plants.',
  'Which production line has the highest energy intensity?',
  'What anomalies were detected?',
  'Explain our zero-production energy consumption.',
  'What is our factory SEC?',
];

export default function SuggestedQuestions({
  isOpen = false,
  onToggle,
  onClose,
  onSelectQuestion,
  disabled = false,
}) {
  const anchorRef = useRef(null);
  const triggerRef = useRef(null);

  const handleClose = () => {
    if (onClose) {
      onClose();
    }
    triggerRef.current?.focus();
  };

  // Close popover when clicking outside or pressing Escape
  useEffect(() => {
    function handleClickOutside(event) {
      if (anchorRef.current && !anchorRef.current.contains(event.target)) {
        if (onClose) onClose();
      }
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        handleClose();
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const handleSelect = (question) => {
    if (disabled) return;
    if (onClose) onClose();
    if (onSelectQuestion) {
      onSelectQuestion(question);
    }
  };

  return (
    <div className="assistant-suggestions-popover-anchor" ref={anchorRef}>
      <button
        type="button"
        className={`assistant-suggestions-trigger ${isOpen ? 'active' : ''}`}
        onClick={onToggle}
        disabled={disabled}
        ref={triggerRef}
        title="View suggested energy analytics queries"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls="assistant-suggestions-dialog"
      >
        <span className="trigger-icon" aria-hidden="true">💡</span>
        <span className="trigger-label">Suggestions</span>
        <svg
          className={`trigger-chevron ${isOpen ? 'open' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      {isOpen && (
        <div
          id="assistant-suggestions-dialog"
          className="assistant-suggestions-popover"
          role="dialog"
          aria-label="Suggested Energy Queries"
        >
          <div className="suggestions-popover-header">
            <span className="popover-title">Suggested Energy Queries</span>
            <button
              type="button"
              className="popover-close-btn"
              onClick={handleClose}
              aria-label="Close suggestions"
              title="Close"
            >
              ✕
            </button>
          </div>
          <div className="suggestions-popover-list">
            {SUGGESTED_QUESTIONS.map((question, idx) => (
              <button
                key={idx}
                type="button"
                className="popover-suggestion-item"
                onClick={() => handleSelect(question)}
                disabled={disabled}
              >
                <span className="suggestion-bullet">›</span>
                <span className="suggestion-text">{question}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
