import React, { useEffect, useState } from 'react';
import { checkBackendHealth } from '../../services/api';

export default function AssistantHeader({
  onNewConversation,
  messageCount = 0,
  theme = 'light',
  onToggleTheme,
}) {
  const [backendStatus, setBackendStatus] = useState('checking'); // 'checking' | 'online' | 'offline'

  useEffect(() => {
    let isMounted = true;

    async function verifyHealth() {
      try {
        const res = await checkBackendHealth();
        if (isMounted) {
          setBackendStatus(res.success ? 'online' : 'offline');
        }
      } catch {
        if (isMounted) {
          setBackendStatus('offline');
        }
      }
    }

    verifyHealth();
    const interval = setInterval(verifyHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="assistant-compact-header">
      <div className="compact-header-left">
        <div className="compact-bot-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 8V4H8"/>
            <rect width="16" height="12" x="4" y="8" rx="2"/>
            <path d="M2 14h2"/>
            <path d="M20 14h2"/>
            <path d="M15 13v2"/>
            <path d="M9 13v2"/>
          </svg>
        </div>
        <span className="compact-header-title" role="heading" aria-level="1">AI Assistant</span>
        <span
          className={`compact-status-badge ${backendStatus}`}
          title={backendStatus === 'online' ? 'Connected to backend' : 'Backend offline'}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <span className="compact-status-dot" aria-hidden="true" />
          {backendStatus === 'online' ? 'Operational' : backendStatus === 'checking' ? 'Connecting...' : 'Offline'}
        </span>
      </div>

      <div className="compact-header-right">
        {messageCount > 0 && (
          <button
            type="button"
            className="compact-new-chat-btn"
            onClick={onNewConversation}
            title="Start a fresh conversation and reset context"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            <span>New Chat</span>
          </button>
        )}
        {onToggleTheme && (
          <button
            type="button"
            className="compact-theme-btn"
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
              </svg>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
