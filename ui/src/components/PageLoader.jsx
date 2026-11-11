import React from 'react';

export default function PageLoader({
  message = 'Loading View...',
  subtitle = 'Loading application module and dependencies',
}) {
  return (
    <div className="dashboard-loading-state" style={{ minHeight: '360px' }} role="status" aria-live="polite">
      <div className="loading-spinner" aria-hidden="true" />
      <div className="loading-title">{message}</div>
      <div className="loading-subtitle">{subtitle}</div>
    </div>
  );
}
