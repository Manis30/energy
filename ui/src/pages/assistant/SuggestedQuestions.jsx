import React from 'react';

const SUGGESTED_QUESTIONS = [
  'What is our total energy consumption?',
  'Compare energy consumption between plants.',
  'Which production line has the highest energy intensity?',
  'What anomalies were detected?',
  'Explain our zero-production energy consumption.',
  'What is our factory SEC?',
];

export default function SuggestedQuestions({ onSelectQuestion, disabled = false }) {
  return (
    <div className="assistant-suggestions-container">
      <div className="assistant-suggestions-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
        <span>Suggested Analytics Queries</span>
      </div>
      <div className="assistant-pills-row">
        {SUGGESTED_QUESTIONS.map((question, idx) => (
          <button
            key={idx}
            type="button"
            className="assistant-suggestion-pill"
            onClick={() => onSelectQuestion(question)}
            disabled={disabled}
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
