import React from 'react';
import { useLocation } from 'react-router-dom';

const PATH_TITLES = {
  '/': 'Home',
  '/dashboard': 'Overview Dashboard',
  '/daily-operations': 'Daily Operations',
  '/daily-reports': 'Daily Operations',
  '/energy-analytics': 'Energy Analytics',
  '/production-analytics': 'Production Analytics',
  '/investigation-actions': 'Investigation & Actions Centre',
  '/findings': 'Investigation & Actions Centre',
  '/recommendations-actions': 'Investigation & Actions Centre',
  '/anomalies': 'Anomaly Surveillance',
  '/data-connectors': 'Data Connectors',
  '/ai-assistant': 'Conversational AI Assistant',
  '/platform-story': 'Home',
};

export default function Header({ theme, onToggleTheme, backendStatus, onToggleSidebar }) {
  const location = useLocation();

  // Hide the global top header on the AI Assistant chat page to maximize usable conversation height
  if (location.pathname === '/ai-assistant') {
    return null;
  }

  const currentTitle = PATH_TITLES[location.pathname] || 'Industrial Energy Intelligence';
  const isDashboard = location.pathname === '/dashboard';
  const isDailyOps = location.pathname === '/daily-operations' || location.pathname === '/daily-reports';
  const isCompactHeader = isDashboard || isDailyOps;

  const renderBadge = () => {
    const badgeStyle = isCompactHeader ? { fontSize: '12px', fontWeight: 500 } : undefined;
    if (!backendStatus || backendStatus.loading) {
      return (
        <span
          className={`system-badge loading ${isCompactHeader ? 'dashboard-badge' : ''}`}
          style={badgeStyle}
          title="Checking backend connection..."
        >
          <span className="badge-dot"></span>
          Connecting to API...
        </span>
      );
    }
    if (backendStatus.connected) {
      return (
        <span
          className={`system-badge connected ${isCompactHeader ? 'dashboard-badge' : ''}`}
          style={badgeStyle}
          title="FastAPI backend connected via proxy"
        >
          <span className="badge-dot"></span>
          Backend Connected (v{backendStatus.version || '1.0.0'})
        </span>
      );
    }
    return (
      <span
        className={`system-badge disconnected ${isCompactHeader ? 'dashboard-badge' : ''}`}
        style={badgeStyle}
        title={backendStatus.error || 'FastAPI unavailable'}
      >
        <span className="badge-dot"></span>
        Backend Offline
      </span>
    );
  };

  const isConnectorsRoute = location.pathname === '/data-connectors' || location.pathname === '/connectors';

  return (
    <header className={`top-header ${isConnectorsRoute ? 'route-data-connectors' : ''} ${isDashboard ? 'route-dashboard' : ''} ${isDailyOps ? 'route-daily-operations' : ''}`}>
      <div className="header-title-section">
        <button
          className="mobile-menu-btn"
          onClick={onToggleSidebar}
          type="button"
          aria-label="Toggle navigation menu"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="3" y1="12" x2="21" y2="12"></line>
            <line x1="3" y1="6" x2="21" y2="6"></line>
            <line x1="3" y1="18" x2="21" y2="18"></line>
          </svg>
        </button>
        <h1 className="page-title">
          {currentTitle}
        </h1>
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
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2" />
              <path d="M12 20v2" />
              <path d="m4.93 4.93 1.41 1.41" />
              <path d="m17.66 17.66 1.41 1.41" />
              <path d="M2 12h2" />
              <path d="M20 12h2" />
              <path d="m6.34 17.66-1.41 1.41" />
              <path d="m19.07 4.93-1.41 1.41" />
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  );
}
