import React, { useState, useEffect } from 'react';
import { CATALOG_CONNECTORS } from './connectors/connectorCatalog';
import ConnectorModal from './connectors/ConnectorModal';
import { connectorsApi } from '../services/connectorsApi';
import { formatDateTime } from '../utils/formatters';
import './connectors/data-connectors.css';

/**
 * Enterprise Data Connectors Directory
 * Consumes truthful backend status from /api/connectors.
 *
 * Operational Scope:
 * - PostgreSQL (Authoritative Operational Database)
 * - Manual File Intake (Current Operational Intake Path for CSV & Excel)
 *
 * Simulation Scope:
 * - MongoDB (Simulated Sandbox for Document Schema Mapping)
 * - SharePoint (Simulated Mock for Graph API Report Staging)
 *
 * Enterprise Roadmap Scope (Clearly Labeled as Planned):
 * - REST API Webhook, Siemens Opcenter, SAP ERP/CMMS, SAP HANA, Oracle, Snowflake, MS Teams
 */
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
  const mergedConnectors = CATALOG_CONNECTORS.map((cat) => {
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
          : 'Roadmap Spec'),
      mode: backendMatch.mode,
      connectionState: backendMatch.connection_state,
      isSimulation: isSim,
      isOperationalIntake: isOpIntake,
      lastCheck: backendMatch.last_connectivity_check_at,
      lastIngest: backendMatch.last_successful_ingestion_at,
      providerDetails: backendMatch.provider_details,
    };
  });

  const operationalCount = mergedConnectors.filter(
    (c) => c.isOperationalIntake || (c.mode === 'live_capable' && c.connectionState === 'reachable')
  ).length;
  const simulatedCount = mergedConnectors.filter((c) => c.isSimulation || c.mode === 'simulated').length;
  const roadmapCount = mergedConnectors.filter((c) => c.isRoadmap || c.mode === 'planned').length;

  return (
    <div className="data-connectors-page">
      {/* Capability Scope & Architecture Banner */}
      <div className="connectors-scope-banner" role="region" aria-label="Connector Architecture Scope">
        <div className="scope-banner-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2v20M2 12h20" />
            <circle cx="12" cy="12" r="10" />
          </svg>
        </div>
        <div className="scope-banner-content">
          <div className="scope-banner-title">
            <span>Operational &amp; Enterprise Integration Architecture</span>
            <span className="scope-badge operational">
              {operationalCount || 2} Operational Intake &amp; Database
            </span>
            <span className="scope-badge" style={{ background: 'rgba(234, 179, 8, 0.15)', color: '#eab308' }}>
              {simulatedCount || 2} Simulation Sandboxes
            </span>
            <span className="scope-badge roadmap">{roadmapCount || 6} Planned Roadmap</span>
          </div>
          <p className="scope-banner-text">
            <strong>Operational Data Ingestion:</strong> Factory energy and production telemetry are authoritatively ingested via <strong>Manual File Intake (CSV / Excel)</strong> and stored in <strong>PostgreSQL</strong> with two-stage schema validation and immutable revision pinning. <strong>MongoDB</strong> and <strong>SharePoint</strong> operate explicitly as simulated sandboxes; no live production telemetry flows through them. Enterprise ERP and MES connectors represent the planned roadmap.
          </p>
        </div>
      </div>

      {/* Modern Grid Layout */}
      <section className="connectors-gallery" aria-label="Enterprise Data Connectors Grid">
        <div className="connectors-grid">
          {mergedConnectors.map((connector) => {
            const isConnected = connector.status === 'CONNECTED' || connector.status === 'connected';
            const isSimulated = connector.status === 'SIMULATED' || connector.status === 'simulated' || connector.isSimulation;
            const isRoadmap = connector.isRoadmap || connector.mode === 'planned' || connector.status === 'ROADMAP';

            let cardBadgeClass = 'is-roadmap';
            let pillClass = 'status-roadmap';
            if (isConnected) {
              cardBadgeClass = 'is-operational';
              pillClass = 'status-connected';
            } else if (isSimulated) {
              cardBadgeClass = 'is-simulated';
              pillClass = 'status-simulated';
            }

            return (
              <article
                key={connector.id}
                className={`connector-card ${cardBadgeClass}`}
              >
                {/* Status Indicator Pill */}
                <div className="connector-status-header">
                  <span className={`connector-status-pill ${pillClass}`}>
                    <span className="status-dot" aria-hidden="true" />
                    {connector.statusLabel}
                  </span>
                  <span className="connector-category-tag">{connector.category}</span>
                </div>

                {/* Card Header: Icon Badge & Name */}
                <div className="connector-card-header">
                  <div
                    className={`connector-icon-badge ${
                      connector.initials.length > 2 ? 'len-3' : ''
                    }`}
                    style={{ backgroundColor: connector.iconColor }}
                    aria-hidden="true"
                  >
                    {connector.initials}
                  </div>
                  <div className="connector-title-group">
                    <h2 className="connector-name" title={connector.name}>
                      {connector.name}
                    </h2>
                    <span className="connector-capability-label" title={connector.capability}>
                      {connector.capability}
                    </span>
                  </div>
                </div>

                {/* Concise Card Description */}
                <p className="connector-desc">{connector.desc}</p>

                {/* Ingestion & Connectivity Timestamps */}
                <div style={{ padding: '0.4rem 0.85rem', fontSize: '0.7rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Last Connectivity Check:</span>
                    <strong style={{ color: 'var(--text-secondary)' }}>
                      {connector.lastCheck ? formatDateTime(connector.lastCheck) : 'Unavailable'}
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Last Successful Ingestion:</span>
                    <strong style={{ color: connector.lastIngest ? 'var(--brand-green, #10b981)' : 'var(--text-muted)' }}>
                      {connector.lastIngest ? formatDateTime(connector.lastIngest) : 'Unavailable'}
                    </strong>
                  </div>
                </div>

                {/* Card Footer: Action Button */}
                <div className="connector-card-footer">
                  <button
                    type="button"
                    className={`connector-connect-btn ${isConnected ? 'btn-active' : isSimulated ? 'btn-simulated' : 'btn-roadmap'}`}
                    onClick={() => setSelectedConnector(connector)}
                    aria-label={`${isConnected ? 'Configure' : isSimulated ? 'Inspect Simulation' : 'View Roadmap for'} ${connector.name}`}
                  >
                    <span>{isConnected ? 'View Connection' : isSimulated ? 'Inspect Simulation' : 'Roadmap Spec'}</span>
                    <svg
                      width="13"
                      height="13"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.4"
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
