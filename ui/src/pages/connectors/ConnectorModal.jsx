import React, { useEffect } from 'react';

/**
 * Connector-specific field definitions and metadata for enterprise connectors.
 * Approved Operational Scope:
 * - Neon PostgreSQL (Primary Platform Database)
 * - MongoDB (Telemetry & Time-Series Staging)
 * - Microsoft SharePoint (M365 Daily Report Ingestion)
 *
 * Enterprise Roadmap Scope:
 * - REST API Webhook, Siemens Opcenter, SAP ERP/CMMS, SAP HANA, Oracle, Snowflake, MS Teams
 */
const CONNECTOR_METADATA = {
  'conn-neon-primary': {
    isOperational: true,
    statusText: 'Connected & Operational (Primary Database)',
    statusClass: 'status-connected',
    provider: 'PostgreSQL Operational Database (Neon Serverless / Cloud)',
    fields: [
      { name: 'role', label: 'Platform Role', value: 'Authoritative Primary Relational Storage', type: 'text', readOnly: true },
      { name: 'schema', label: 'Database Schema', value: 'public (fact_energy_meter_hourly, fact_hourly_production, upload_history, operational_findings)', type: 'text', readOnly: true },
      { name: 'revisions', label: 'Data Integrity Mode', value: 'Immutable Source Revisions (fact_source_revisions) & Exact Numeric Precision', type: 'text', readOnly: true },
      { name: 'access', label: 'Access & Governance', value: 'Protected Engine Connection Pool with Transactional Isolation', type: 'text', readOnly: true },
    ],
  },
  'neon-postgres': {
    isOperational: true,
    statusText: 'Connected & Operational (Primary Database)',
    statusClass: 'status-connected',
    provider: 'PostgreSQL Operational Database (Neon Serverless / Cloud)',
    fields: [
      { name: 'role', label: 'Platform Role', value: 'Authoritative Primary Relational Storage', type: 'text', readOnly: true },
      { name: 'schema', label: 'Database Schema', value: 'public (fact_energy_meter_hourly, fact_hourly_production, upload_history, operational_findings)', type: 'text', readOnly: true },
      { name: 'revisions', label: 'Data Integrity Mode', value: 'Immutable Source Revisions (fact_source_revisions) & Exact Numeric Precision', type: 'text', readOnly: true },
      { name: 'access', label: 'Access & Governance', value: 'Protected Engine Connection Pool with Transactional Isolation', type: 'text', readOnly: true },
    ],
  },
  'conn-manual-file-intake': {
    isOperational: true,
    statusText: 'Operational Intake Path (Active)',
    statusClass: 'status-connected',
    provider: 'Direct File Upload & Schema Validation Pipeline',
    fields: [
      { name: 'role', label: 'Intake Role', value: 'Primary Operational Data Ingestion Path', type: 'text', readOnly: true },
      { name: 'endpoints', label: 'Ingestion Endpoints', value: 'POST /api/daily-reports/upload (Multipart Form)', type: 'text', readOnly: true },
      { name: 'validation', label: 'Validation Pipeline', value: 'Two-stage schema verification, bounds checking, SHA-256 content hashing', type: 'text', readOnly: true },
      { name: 'formats', label: 'Supported File Formats', value: 'CSV (.csv) and Excel (.xlsx, .xls) Daily Energy & Production Reports', type: 'text', readOnly: true },
      { name: 'deduplication', label: 'Duplicate Handling', value: 'Deterministic no-change detection returning imported_rows=0 on exact duplicate retry', type: 'text', readOnly: true },
    ],
  },
  'conn-mongo-analytics': {
    isOperational: false,
    isSimulation: true,
    statusText: 'Simulation Sandbox (No Live Ingestion)',
    statusClass: 'status-simulated',
    provider: 'MongoDB Atlas (Simulation Sandbox)',
    fields: [
      { name: 'role', label: 'Connector Role', value: 'NoSQL Document Schema Discovery Simulation', type: 'text', readOnly: true },
      { name: 'uri', label: 'Connection URI', value: 'mongodb+srv://plant_operator:••••••••@cluster0.mfg-iot.mongodb.net/energy_telemetry', type: 'text', readOnly: true },
      { name: 'database', label: 'Database Name', value: 'energy_telemetry (Mock Staging)', type: 'text', readOnly: true },
      { name: 'collections', label: 'Target Collections', value: 'sensor_telemetry_raw, meter_intervals_staging, alarm_events (Simulated Fixtures)', type: 'text', readOnly: true },
      { name: 'notice', label: 'Operational Status', value: 'Simulated testbed only; no live production equipment telemetry flows through this connector', type: 'text', readOnly: true },
    ],
  },
  mongodb: {
    isOperational: false,
    isSimulation: true,
    statusText: 'Simulation Sandbox (No Live Ingestion)',
    statusClass: 'status-simulated',
    provider: 'MongoDB Atlas (Simulation Sandbox)',
    fields: [
      { name: 'role', label: 'Connector Role', value: 'NoSQL Document Schema Discovery Simulation', type: 'text', readOnly: true },
      { name: 'uri', label: 'Connection URI', value: 'mongodb+srv://plant_operator:••••••••@cluster0.mfg-iot.mongodb.net/energy_telemetry', type: 'text', readOnly: true },
      { name: 'database', label: 'Database Name', value: 'energy_telemetry (Mock Staging)', type: 'text', readOnly: true },
      { name: 'collections', label: 'Target Collections', value: 'sensor_telemetry_raw, meter_intervals_staging, alarm_events (Simulated Fixtures)', type: 'text', readOnly: true },
      { name: 'notice', label: 'Operational Status', value: 'Simulated testbed only; no live production equipment telemetry flows through this connector', type: 'text', readOnly: true },
    ],
  },
  'conn-sp-mfg': {
    isOperational: false,
    isSimulation: true,
    statusText: 'Simulation Mock (No Live Ingestion)',
    statusClass: 'status-simulated',
    provider: 'Microsoft 365 SharePoint Online (Simulation Mock)',
    fields: [
      { name: 'role', label: 'Connector Role', value: 'Microsoft Graph API Report Staging Simulation', type: 'text', readOnly: true },
      { name: 'siteUrl', label: 'Plant SharePoint Site URL', value: 'https://industrial-energy.sharepoint.com/sites/plant-operations', type: 'text', readOnly: true },
      { name: 'library', label: 'Monitored Document Library', value: 'Energy & Production Reports (Mock Fixture)', type: 'text', readOnly: true },
      { name: 'notice', label: 'Operational Status', value: 'Simulated testbed only; operational reports are ingested via the Manual File Intake path', type: 'text', readOnly: true },
    ],
  },
  sharepoint: {
    isOperational: false,
    isSimulation: true,
    statusText: 'Simulation Mock (No Live Ingestion)',
    statusClass: 'status-simulated',
    provider: 'Microsoft 365 SharePoint Online (Simulation Mock)',
    fields: [
      { name: 'role', label: 'Connector Role', value: 'Microsoft Graph API Report Staging Simulation', type: 'text', readOnly: true },
      { name: 'siteUrl', label: 'Plant SharePoint Site URL', value: 'https://industrial-energy.sharepoint.com/sites/plant-operations', type: 'text', readOnly: true },
      { name: 'library', label: 'Monitored Document Library', value: 'Energy & Production Reports (Mock Fixture)', type: 'text', readOnly: true },
      { name: 'notice', label: 'Operational Status', value: 'Simulated testbed only; operational reports are ingested via the Manual File Intake path', type: 'text', readOnly: true },
    ],
  },
  api: {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q2 2027)',
    statusClass: 'status-roadmap',
    provider: 'Platform API Gateway (HTTPS Webhook Ingest)',
    fields: [
      { name: 'endpoint', label: 'Planned Webhook Endpoint', value: 'https://api.energyintel.internal/v1/telemetry/stream', type: 'text', readOnly: true },
      { name: 'authMode', label: 'Target Authentication', value: 'Bearer API Key + HMAC SHA-256 Signature', type: 'text', readOnly: true },
      { name: 'payloads', label: 'Supported Payload Schema', value: 'JSON Time-Series (High-Frequency Meter Batches)', type: 'text', readOnly: true },
      { name: 'dispatch', label: 'Alert Dispatch Webhook', value: 'Outbound HTTP POST on Critical Anomaly Triggers', type: 'text', readOnly: true },
    ],
  },
  opcenter: {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q3 2027)',
    statusClass: 'status-roadmap',
    provider: 'Siemens Opcenter Execution (MES Interface)',
    fields: [
      { name: 'protocol', label: 'Interface Protocol', value: 'OPC-UA Binary + REST Webhook Gateway', type: 'text', readOnly: true },
      { name: 'lines', label: 'Target Production Lines', value: 'SMT Line 1, SMT Line 2, FAL Assembly Line 1', type: 'text', readOnly: true },
      { name: 'events', label: 'Planned Event Subscriptions', value: 'Order State, Machine Fault Codes, OEE Downtime Reasons', type: 'text', readOnly: true },
      { name: 'targetRelease', label: 'Scheduled Availability', value: 'Multi-Plant Enterprise Rollout (Q3 2027)', type: 'text', readOnly: true },
    ],
  },
  sap: {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q3 2027)',
    statusClass: 'status-roadmap',
    provider: 'SAP S/4HANA & ECC 6.0 Integration (CMMS / ERP)',
    fields: [
      { name: 'protocol', label: 'Interface Protocol', value: 'RFC / BAPI / SAP OData v4 Gateway', type: 'text', readOnly: true },
      { name: 'modules', label: 'Integrated Modules', value: 'PM (Plant Maintenance) & CO/FI (Cost Center Accounting)', type: 'text', readOnly: true },
      { name: 'scope', label: 'Planned Capabilities', value: 'Automated PM Work Order Creation on Critical Anomaly Verification', type: 'text', readOnly: true },
      { name: 'targetRelease', label: 'Scheduled Availability', value: 'Multi-Plant Enterprise Rollout (Q3 2027)', type: 'text', readOnly: true },
    ],
  },
  'sap-hana': {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q3 2027)',
    statusClass: 'status-roadmap',
    provider: 'SAP HANA In-Memory Database (Enterprise Calc Views)',
    fields: [
      { name: 'protocol', label: 'Interface Protocol', value: 'HDB SQL Driver / Calculation View Introspection', type: 'text', readOnly: true },
      { name: 'views', label: 'Target Analytical Views', value: '_SYS_BIC/sap.mfg.energy/CV_HOURLY_BASELINE_PROFILE', type: 'text', readOnly: true },
      { name: 'scope', label: 'Planned Capabilities', value: 'Enterprise yield baseline sync & memory cache replication', type: 'text', readOnly: true },
      { name: 'targetRelease', label: 'Scheduled Availability', value: 'Multi-Plant Enterprise Rollout (Q3 2027)', type: 'text', readOnly: true },
    ],
  },
  oracle: {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q4 2027)',
    statusClass: 'status-roadmap',
    provider: 'Oracle Plant Historian & Warehouse Mirror',
    fields: [
      { name: 'protocol', label: 'Interface Protocol', value: 'Oracle OCI / JDBC Thin Client', type: 'text', readOnly: true },
      { name: 'schema', label: 'Target Schema', value: 'ENERGY_HISTORIAN_ARCHIVE', type: 'text', readOnly: true },
      { name: 'scope', label: 'Planned Capabilities', value: 'Multi-year cold storage archive & historical batch comparison', type: 'text', readOnly: true },
      { name: 'targetRelease', label: 'Scheduled Availability', value: 'Multi-Plant Enterprise Rollout (Q4 2027)', type: 'text', readOnly: true },
    ],
  },
  snowflake: {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q4 2027)',
    statusClass: 'status-roadmap',
    provider: 'Snowflake Enterprise Data Cloud (ESG Data Share)',
    fields: [
      { name: 'protocol', label: 'Interface Protocol', value: 'Snowpipe Continuous Staging & Secure Data Sharing', type: 'text', readOnly: true },
      { name: 'database', label: 'Target Warehouse', value: 'CORP_ESG_REPORTING / FACTORY_DATA_SHARE', type: 'text', readOnly: true },
      { name: 'scope', label: 'Planned Capabilities', value: 'Group-level SEC benchmark federation and carbon emissions rollup', type: 'text', readOnly: true },
      { name: 'targetRelease', label: 'Scheduled Availability', value: 'Multi-Plant Enterprise Rollout (Q4 2027)', type: 'text', readOnly: true },
    ],
  },
  teams: {
    isOperational: false,
    statusText: 'Enterprise Roadmap (Planned Q2 2027)',
    statusClass: 'status-roadmap',
    provider: 'Microsoft Teams Webhook & Shift Collaboration Bot',
    fields: [
      { name: 'protocol', label: 'Interface Protocol', value: 'Microsoft Graph API & Adaptive Cards Webhook', type: 'text', readOnly: true },
      { name: 'channels', label: 'Target Channels', value: '#plant-engineering-ops, #daily-shift-handover', type: 'text', readOnly: true },
      { name: 'scope', label: 'Planned Capabilities', value: 'Real-time alert dispatch with one-click acknowledgment buttons', type: 'text', readOnly: true },
      { name: 'targetRelease', label: 'Scheduled Availability', value: 'Enterprise Operations Release (Q2 2027)', type: 'text', readOnly: true },
    ],
  },
};

export default function ConnectorModal({ connector, onClose }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!connector) return null;

  const meta = CONNECTOR_METADATA[connector.id] || {
    isOperational: false,
    statusText: 'Roadmap Specification',
    statusClass: 'status-roadmap',
    provider: connector.category,
    fields: [
      { name: 'info', label: 'Architecture Note', value: connector.desc, type: 'text', readOnly: true },
    ],
  };

  return (
    <div
      className="connector-modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        className="connector-modal-container"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="connector-modal-header">
          <div className="connector-modal-brand">
            <div
              className={`connector-icon-badge ${connector.initials.length > 2 ? 'len-3' : ''}`}
              style={{ backgroundColor: connector.iconColor }}
              aria-hidden="true"
            >
              {connector.initials}
            </div>
            <div className="connector-modal-title-group">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                <h2 id="modal-title" className="connector-modal-title">
                  {connector.name}
                </h2>
                <span className={`modal-status-badge ${meta.statusClass}`}>
                  <span className="status-dot" aria-hidden="true" />
                  {meta.statusText}
                </span>
              </div>
              <span className="connector-modal-category">{meta.provider}</span>
            </div>
          </div>

          <button
            type="button"
            className="connector-modal-close-btn"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Informational Callout */}
        {meta.isOperational ? (
          <div className="connector-modal-alert operational">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <span>
              <strong>Operational Data Path:</strong> This connector is actively used for platform operational intake and relational fact storage. Telemetry is validated with immutable source revisions and batch lineage.
            </span>
          </div>
        ) : meta.isSimulation ? (
          <div className="connector-modal-alert" style={{ background: 'rgba(234, 179, 8, 0.1)', borderColor: 'rgba(234, 179, 8, 0.3)', color: 'var(--text-primary)' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#eab308" strokeWidth="2.2">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
            <span>
              <strong>Simulation Sandbox:</strong> This is an isolated simulation sandbox for testing schema mapping and mock payloads. Simulated success or fixture discovery does not represent live equipment connectivity or active data ingestion.
            </span>
          </div>
        ) : (
          <div className="connector-modal-alert roadmap">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>
              <strong>Enterprise Roadmap Specification:</strong> This integration is scheduled for future multi-plant deployments. Operational factory data is currently ingested via the Manual File Intake (CSV/Excel) path into PostgreSQL.
            </span>
          </div>
        )}

        {/* Configuration / Specification Details */}
        <div className="connector-modal-form">
          <div className="connector-form-fields-grid">
            {meta.fields.map((field) => (
              <div key={field.name} className="connector-form-group">
                <label className="connector-form-label" htmlFor={`field-${field.name}`}>
                  {field.label}
                </label>
                <input
                  id={`field-${field.name}`}
                  type="text"
                  className="connector-form-input"
                  value={field.value}
                  readOnly
                />
              </div>
            ))}
          </div>

          {/* Action Footers */}
          <div className="connector-modal-actions">
            <button
              type="button"
              className="connector-btn-secondary"
              onClick={onClose}
            >
              Close
            </button>
            {meta.isOperational && (
              <button
                type="button"
                className="connector-btn-primary"
                onClick={onClose}
              >
                Done (Connection Verified)
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
