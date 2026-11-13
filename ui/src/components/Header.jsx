import React from 'react';
import { useLocation } from 'react-router-dom';

const PATH_TITLES = {
  '/': 'Overview Dashboard',
  '/energy-analytics': 'Energy Analytics',
  '/production-analytics': 'Production Analytics',
  '/anomalies': 'Anomaly Detection',
  '/daily-analysis': 'Daily Energy Analysis',
  '/ai-assistant': 'Conversational AI Assistant',
};

export default function Header({ theme, onToggleTheme, backendStatus }) {
  const location = useLocation();

  // Hide the global top header on the AI Assistant chat page to maximize usable conversation height
  if (location.pathname === '/ai-assistant') {
    return null;
  }

  const currentTitle = PATH_TITLES[location.pathname] || 'Industrial Energy Intelligence';

  const renderBadge = () => {
    if (!backendStatus || backendStatus.loading) {
      return (
        <span className="system-badge loading" title="Checking backend connection...">
          <span className="badge-dot"></span>
          Connecting to API...
        </span>
      );
    }
    if (backendStatus.connected) {
      return (
        <span className="system-badge connected" title="FastAPI backend connected via proxy">
          <span className="badge-dot"></span>
          Backend Connected (v{backendStatus.version || '1.0.0'})
        </span>
      );
    }
    return (
      <span className="system-badge disconnected" title={backendStatus.error || 'FastAPI unavailable'}>
        <span className="badge-dot"></span>
        Backend Offline
      </span>
    );
  };

  return (
    <header className="top-header">
      <div className="header-title-section">
        <h1 className="page-title">{currentTitle}</h1>
        {renderBadge()}
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
