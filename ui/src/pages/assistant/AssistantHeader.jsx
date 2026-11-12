import React, { useEffect, useState } from 'react';
import { checkBackendHealth } from '../../services/api';

export default function AssistantHeader({ onNewConversation, messageCount = 0 }) {
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
    // Poll every 30 seconds
    const interval = setInterval(verifyHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="assistant-header-card">
      <div className="assistant-header-main">
        <div className="assistant-header-titles">
          <div className="assistant-title-row">
            <div className="assistant-bot-avatar">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 8V4H8"/>
                <rect width="16" height="12" x="4" y="8" rx="2"/>
                <path d="M2 14h2"/>
                <path d="M20 14h2"/>
                <path d="M15 13v2"/>
                <path d="M9 13v2"/>
              </svg>
            </div>
            <h2 className="assistant-title">AI Energy Assistant</h2>

            {backendStatus === 'online' && (
              <span className="assistant-status-badge online" title="Backend connected and operational">
                <span className="status-dot-online" />
                Operational
              </span>
            )}

            {backendStatus === 'offline' && (
              <span className="assistant-status-badge offline" title="Backend unreachable via Vite proxy">
                <span className="status-dot-offline" />
                Backend Offline
              </span>
            )}

            {backendStatus === 'checking' && (
              <span className="assistant-status-badge pending" title="Verifying backend connection">
                <span className="status-dot-pending" />
                Verifying...
              </span>
            )}
          </div>
          <p className="assistant-subtitle">
            Autonomous industrial intelligence powered by Domo AI, 21 deterministic analytics tools, and read-only PostgreSQL execution.
          </p>
        </div>

        {messageCount > 0 && (
          <div className="assistant-header-actions">
            <button
              type="button"
              className="assistant-btn-secondary"
              onClick={onNewConversation}
              title="Start a fresh conversation and reset context"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5v14M5 12h14"/>
              </svg>
              <span>New Conversation</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
