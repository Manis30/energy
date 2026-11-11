import React from 'react';

const PAGE_TITLES = {
  dashboard: 'Overview Dashboard',
  'energy-analytics': 'Energy Analytics',
  'production-analytics': 'Production Analytics',
  anomalies: 'Anomaly Detection',
  'daily-analysis': 'Daily Energy Analysis',
  'ai-assistant': 'Conversational AI Assistant',
};

export default function Header({ activeNav, theme, onToggleTheme }) {
  const currentTitle = PAGE_TITLES[activeNav] || 'Industrial Energy Intelligence';

  return (
    <header className="top-header">
      <div className="header-title-section">
        <h1 className="page-title">{currentTitle}</h1>
        <span className="system-badge">
          <span className="badge-dot"></span>
          System Ready
        </span>
      </div>

      <div className="header-actions">
        <button
          className="theme-toggle-btn"
          onClick={onToggleTheme}
          type="button"
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2"/>
              <path d="M12 20v2"/>
              <path d="m4.93 4.93 1.41 1.41"/>
              <path d="m17.66 17.66 1.41 1.41"/>
              <path d="M2 12h2"/>
              <path d="M20 12h2"/>
              <path d="m6.34 17.66-1.41 1.41"/>
              <path d="m19.07 4.93-1.41 1.41"/>
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
            </svg>
          )}
        </button>
      </div>
    </header>
  );
}
