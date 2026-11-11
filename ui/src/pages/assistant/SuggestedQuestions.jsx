import React from 'react';

const SUGGESTED_QUESTIONS = [
  'What is the total energy consumption across both plants?',
  'Compare energy intensity between SMT and Final Assembly.',
  'Which meters have the highest energy consumption?',
  'Explain the most significant energy anomalies.',
  'How much energy was consumed during zero-production periods?',
];

export default function SuggestedQuestions({ onSelectQuestion }) {
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
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
