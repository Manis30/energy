import React from 'react';

export default function DailyAnalysis() {
  const details = [
    'Action: Run Today\'s Energy Analysis trigger ready for integration',
    'Persistence: Neon report storage and historical audit log',
    'Auditing: Shift-level and line-level variance summaries',
    'Automation: Scheduled background run and on-demand execution capability',
  ];

  return (
    <div className="placeholder-card">
      <div className="placeholder-header">
        <h2 className="placeholder-heading">Automated Daily Energy Analysis</h2>
        <p className="placeholder-desc">
          One-click daily energy reporting workflow generating verified executive summaries, anomaly audits, and evidence-backed energy savings actions.
        </p>
      </div>
      <div className="placeholder-details">
        {details.map((detail, idx) => (
          <div key={idx} className="placeholder-item">
            <span className="item-bullet">›</span>
            <span>{detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
