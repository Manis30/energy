import React from 'react';
import { NavLink } from 'react-router-dom';
import logoImg from '../assets/logo.png';
import logoDarkImg from '../assets/logo-dark.png';

/**
 * Compact Sidebar Navigation Items with Inter typography:
 * 1. Home (Architecture Overview landing page)
 * 2. Dashboard (3x3 grid / keypad icon)
 * 3. Daily Operations (Arrow up with baseline icon)
 * 4. Energy Analytics (Phase wave / electricity curve icon)
 * 5. Production Analytics (Pulse / activity wave icon)
 * 6. Investigation Centre (Clean diamond icon)
 * 7. Data Connectors (Rectangle with 3 horizontal stripes icon)
 * 8. AI Assistant (4-pointed star / sparkle icon)
 */
const NAV_ITEMS = [
  {
    path: '/',
    label: 'Home',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
    end: true,
  },
  {
    path: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="4" height="4" rx="1" />
        <rect x="10" y="3" width="4" height="4" rx="1" />
        <rect x="17" y="3" width="4" height="4" rx="1" />
        <rect x="3" y="10" width="4" height="4" rx="1" />
        <rect x="10" y="10" width="4" height="4" rx="1" />
        <rect x="17" y="10" width="4" height="4" rx="1" />
        <rect x="3" y="17" width="4" height="4" rx="1" />
        <rect x="10" y="17" width="4" height="4" rx="1" />
        <rect x="17" y="17" width="4" height="4" rx="1" />
      </svg>
    ),
  },
  {
    path: '/daily-operations',
    label: 'Daily Operations',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="18" x2="12" y2="5" />
        <polyline points="6 11 12 5 18 11" />
        <line x1="8" y1="18" x2="16" y2="18" />
      </svg>
    ),
  },
  {
    path: '/energy-analytics',
    label: 'Energy Analytics',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 2c-1 2-4 3.5-4 6.5 0 3.5 6 3.5 6 7 0 3-3 4.5-4 6.5" />
      </svg>
    ),
  },
  {
    path: '/production-analytics',
    label: 'Production Analytics',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="2 13 6 13 9 7 13 17 16 12 18 13 22 13" />
      </svg>
    ),
  },
  {
    path: '/investigation-actions',
    label: 'Investigation Centre',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 3 20.5 12 12 21 3.5 12" />
      </svg>
    ),
  },
  {
    path: '/data-connectors',
    label: 'Data Connectors',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <line x1="8" y1="9" x2="16" y2="9" />
        <line x1="8" y1="12" x2="16" y2="12" />
        <line x1="8" y1="15" x2="16" y2="15" />
      </svg>
    ),
  },
  {
    path: '/ai-assistant',
    label: 'AI Assistant',
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="m12 3-1.9 6.1a2 2 0 0 1-1.2 1.2L2.8 12l6.1 1.9a2 2 0 0 1 1.2 1.2L12 21.2l1.9-6.1a2 2 0 0 1 1.2-1.2l6.1-1.9-6.1-1.9a2 2 0 0 1-1.2-1.2L12 3z" />
      </svg>
    ),
  },
];

export default function Sidebar({ isOpen = false, onClose }) {
  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`} aria-label="Application Sidebar">
      <div className="sidebar-glass-panel">
        {/* Brand / Logo Header */}
        <div className="sidebar-header">
          <div className="brand-group">
            <img src={logoImg} alt="GWC DATA.AI - Solution Matters" className="brand-full-logo brand-logo-light" />
            <img src={logoDarkImg} alt="GWC DATA.AI - Solution Matters" className="brand-full-logo brand-logo-dark" />
          </div>
          <button
            className="sidebar-close-btn"
            onClick={onClose}
            type="button"
            aria-label="Close navigation menu"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {/* WORKSPACE Category Label */}
        <div className="sidebar-section-header">
          <span className="sidebar-section-label">WORKSPACE</span>
        </div>

        {/* Navigation Items */}
        <nav className="sidebar-nav" role="navigation" aria-label="Main Navigation">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              title={item.label}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              onClick={() => {
                if (onClose) onClose();
              }}
            >
              <span className="nav-active-bar" aria-hidden="true" />
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
              <span className="nav-chevron" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </span>
            </NavLink>
          ))}
        </nav>

        {/* Platform Version Footer */}
        <div className="sidebar-footer">
          <div
            className="sidebar-version-pill"
            title="Industrial Energy Intelligence v1.0.0"
          >
            <span className="version-dot" aria-hidden="true" />
            <span>PLATFORM V1.0.0</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
