import React, { useState, useEffect, useMemo } from 'react';
import { CATALOG_CONNECTORS } from './connectors/connectorCatalog';
import ConnectorModal from './connectors/ConnectorModal';
import { connectorsApi } from '../services/connectorsApi';
import './connectors/data-connectors.css';

/**
 * Helper to determine status category, badge label, and action details
 */
function getConnectorStatus(connector) {
  if (
    connector.status === 'CONNECTED' ||
    connector.status === 'connected' ||
    connector.isOperationalIntake ||
    (connector.mode === 'live_capable' && connector.connectionState === 'reachable')
  ) {
    return {
      group: 'operational',
      badgeClass: 'status-operational',
      label: 'Operational',
      actionLabel: 'View Connection',
      actionClass: 'btn-operational',
    };
  }

  if (
    connector.status === 'SIMULATED' ||
    connector.status === 'simulated' ||
    connector.isSimulation ||
    connector.mode === 'simulated'
  ) {
    return {
      group: 'simulated',
      badgeClass: 'status-simulated',
      label: 'Simulated',
      actionLabel: 'Inspect Simulation',
      actionClass: 'btn-simulated',
    };
  }

  // Planned / Roadmap: include planned quarter when available
  let quarter = '';
  if (connector.statusLabel) {
    const match = connector.statusLabel.match(/Q[1-4]\s*\d{4}/i);
    if (match) {
      quarter = match[0];
    }
  }

  return {
    group: 'planned',
    badgeClass: 'status-planned',
    label: quarter ? `Planned · ${quarter}` : 'Planned',
    actionLabel: 'Roadmap Spec',
    actionClass: 'btn-planned',
  };
}

export default function DataConnectors() {
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [backendConnectors, setBackendConnectors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    connectorsApi
      .getConnectors()
      .then((data) => {
        if (!cancelled && Array.isArray(data)) {
          setBackendConnectors(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.warn('Failed to fetch backend connectors:', err);
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Merge backend runtime status with static catalog descriptions
  const mergedConnectors = useMemo(() => {
    return CATALOG_CONNECTORS.map((cat) => {
      const backendMatch = backendConnectors.find(
        (b) =>
          b.id === cat.id ||
          b.id === cat.backendId ||
          (cat.id === 'neon-postgres' && b.id === 'conn-neon-primary') ||
          (cat.id === 'mongodb' && b.type === 'mongodb') ||
          (cat.id === 'sharepoint' && b.type === 'sharepoint')
      );

      if (!backendMatch) return cat;

      const isSim = Boolean(backendMatch.is_simulation);
      const isOpIntake = Boolean(backendMatch.is_operational_intake);
      const isLive = backendMatch.mode === 'live_capable' && backendMatch.connection_state === 'reachable';

      return {
        ...cat,
        name: backendMatch.name || cat.name,
        backendData: backendMatch,
        status: backendMatch.status,
        statusLabel:
          backendMatch.status_label ||
          (isLive
            ? 'Reachable (Live)'
            : isOpIntake
            ? 'Operational Intake'
            : isSim
            ? 'Simulated Sandbox'
            : cat.statusLabel),
        mode: backendMatch.mode,
        connectionState: backendMatch.connection_state,
        isSimulation: isSim,
        isOperationalIntake: isOpIntake,
        lastCheck: backendMatch.last_connectivity_check_at,
        lastIngest: backendMatch.last_successful_ingestion_at,
        providerDetails: backendMatch.provider_details,
      };
    });
  }, [backendConnectors]);

  // Derived counts for slim summary row
  const statusCounts = useMemo(() => {
    let operational = 0;
    let simulated = 0;
    let planned = 0;

    mergedConnectors.forEach((c) => {
      const { group } = getConnectorStatus(c);
      if (group === 'operational') operational++;
      else if (group === 'simulated') simulated++;
      else planned++;
    });

    return { operational, simulated, planned };
  }, [mergedConnectors]);

  return (
    <div className="data-connectors-page">
      {/* Slim Summary Row directly below page title */}
      <div className="connectors-summary-row" role="region" aria-label="Connector status summary">
        <div className="summary-pill operational">
          <span className="summary-dot" aria-hidden="true" />
          <span className="summary-count">{statusCounts.operational}</span>
          <span className="summary-label">Operational</span>
        </div>
        <div className="summary-pill simulated">
          <span className="summary-dot" aria-hidden="true" />
          <span className="summary-count">{statusCounts.simulated}</span>
          <span className="summary-label">Simulated</span>
        </div>
        <div className="summary-pill planned">
          <span className="summary-dot" aria-hidden="true" />
          <span className="summary-count">{statusCounts.planned}</span>
          <span className="summary-label">Planned</span>
        </div>
      </div>

      {/* 5-Column Responsive Directory Grid */}
      <section className="connectors-gallery" aria-label="Enterprise Data Connectors Grid">
        <div className="connectors-grid">
          {mergedConnectors.map((connector) => {
            const statusInfo = getConnectorStatus(connector);

            return (
              <article
                key={connector.id}
                className={`connector-card ${statusInfo.group}`}
                tabIndex={0}
                aria-label={`${connector.name} - ${statusInfo.label}`}
              >
                {/* 1. Small connector logo/initials beside connector name */}
                <div className="connector-card-header">
                  <div
                    className="connector-icon-badge"
                    style={{ backgroundColor: connector.iconColor }}
                    aria-hidden="true"
                  >
                    {connector.initials}
                  </div>
                  <h2 className="connector-name" title={connector.name}>
                    {connector.name}
                  </h2>
                </div>

                {/* 2. One status badge: Operational, Simulated, or Planned (with quarter) */}
                <div className="connector-status-wrap">
                  <span className={`connector-status-badge ${statusInfo.badgeClass}`}>
                    <span className="status-dot" aria-hidden="true" />
                    {statusInfo.label}
                  </span>
                </div>

                {/* 3. One short sentence describing what the connector does */}
                <p className="connector-desc">
                  {connector.shortDesc || connector.desc}
                </p>

                {/* 4. One compact action using existing label and handler */}
                <div className="connector-card-footer">
                  <button
                    type="button"
                    className={`connector-action-btn ${statusInfo.actionClass}`}
                    onClick={() => setSelectedConnector(connector)}
                    aria-label={`${statusInfo.actionLabel} for ${connector.name}`}
                  >
                    <span>{statusInfo.actionLabel}</span>
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {/* Centered Glassmorphism Connector Details / Config Modal */}
      {selectedConnector && (
        <ConnectorModal
          connector={selectedConnector}
          onClose={() => setSelectedConnector(null)}
        />
      )}
    </div>
  );
}
