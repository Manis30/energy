import React, { useCallback, useEffect, useState } from 'react';
import { connectorsApi } from '../services/connectorsApi';
import { formatDateTime } from '../utils/formatters';
import './connectors/data-connectors.css';

export default function DataConnectors() {
  // Main Navigation Tabs
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'sources' | 'discovery' | 'migration' | 'history'

  // Data State
  const [connectors, setConnectors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bannerNotice, setBannerNotice] = useState(null);

  // Sync History State
  const [syncHistory, setSyncHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Test Connectivity State
  const [testModal, setTestModal] = useState({
    open: false,
    loading: false,
    result: null,
    connector: null,
  });

  // Add / Edit Connector Modal State
  const [configModal, setConfigModal] = useState({
    open: false,
    mode: 'create', // 'create' | 'edit'
    type: 'mongodb', // 'mongodb' | 'sharepoint'
    connectorId: null,
    formData: {
      name: '',
      uri: '',
      database_name: '',
      auth_database: 'admin',
      replica_set: '',
      ssl: true,
      site_url: '',
      tenant_id: '',
      client_id: '',
      client_secret: '',
      default_library: 'Energy & Production Reports',
    },
    submitting: false,
    error: null,
  });

  // Discovery State
  const [discoveryState, setDiscoveryState] = useState({
    selectedConnectorId: 'conn-neon-primary',
    loading: false,
    data: null,
    selectedEntity: null,
    error: null,
  });

  // Data Preview Modal State
  const [previewModal, setPreviewModal] = useState({
    open: false,
    loading: false,
    data: null,
    error: null,
  });

  // Migration Workflow State
  const [migrationState, setMigrationState] = useState({
    sourceConnectorId: 'conn-neon-primary',
    destConnectorId: 'conn-mongo-analytics',
    sourceEntity: 'fact_energy_meter_hourly',
    destEntity: 'meter_raw_events',
    fieldMappings: [
      { source_field: 'meter_reading_id', source_type: 'bigint', destination_field: 'sql_source_id', destination_type: 'int64', transformation: 'direct' },
      { source_field: 'timestamp', source_type: 'timestamptz', destination_field: 'timestamp', destination_type: 'ISODate', transformation: 'direct' },
      { source_field: 'plant_id', source_type: 'varchar(50)', destination_field: 'plant_id', destination_type: 'String', transformation: 'direct' },
      { source_field: 'meter_id', source_type: 'varchar(50)', destination_field: 'meter_id', destination_type: 'String', transformation: 'direct' },
      { source_field: 'consumption_kwh', source_type: 'numeric(12,4)', destination_field: 'active_power_kw', destination_type: 'Double', transformation: 'direct' },
      { source_field: 'demand_kw', source_type: 'numeric(12,4)', destination_field: 'peak_demand_kw', destination_type: 'Double', transformation: 'direct' },
      { source_field: 'power_factor', source_type: 'numeric(4,3)', destination_field: 'power_factor', destination_type: 'Double', transformation: 'direct' },
    ],
    previewResult: null,
    loading: false,
    error: null,
  });

  // SharePoint Ingestion Staging State
  const [stagingState, setStagingState] = useState({
    loading: false,
    result: null,
    error: null,
  });

  // -------------------------------------------------------------------------
  // Initial Data Fetching
  // -------------------------------------------------------------------------

  const fetchConnectors = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await connectorsApi.getConnectors();
      if (res.success && Array.isArray(res.data)) {
        setConnectors(res.data);
      } else {
        throw new Error(res.error || 'Failed to load data connectors');
      }
    } catch (err) {
      setError(err.message || 'Error connecting to connector backend');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      setLoadingHistory(true);
      const res = await connectorsApi.getSyncHistory(50);
      if (res.success && res.data?.items) {
        setSyncHistory(res.data.items);
      }
    } catch {
      // Non-blocking history load
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    fetchConnectors();
    fetchHistory();
  }, [fetchConnectors, fetchHistory]);

  // Load discovery data when discovery tab or connector changes
  const loadDiscovery = useCallback(async (connectorId) => {
    try {
      setDiscoveryState((prev) => ({
        ...prev,
        selectedConnectorId: connectorId,
        loading: true,
        error: null,
      }));
      const res = await connectorsApi.discoverResources(connectorId);
      if (res.success && res.data) {
        const data = res.data;
        let defaultEntity = null;
        if (data.tables?.length) defaultEntity = data.tables[0].table_name;
        else if (data.collections?.length) defaultEntity = data.collections[0].collection_name;
        else if (data.files?.length) defaultEntity = data.files[0].file_id;

        setDiscoveryState((prev) => ({
          ...prev,
          loading: false,
          data,
          selectedEntity: defaultEntity,
        }));
      } else {
        throw new Error(res.error || 'Discovery failed');
      }
    } catch (err) {
      setDiscoveryState((prev) => ({
        ...prev,
        loading: false,
        error: err.message,
      }));
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'discovery') {
      loadDiscovery(discoveryState.selectedConnectorId);
    }
  }, [activeTab, discoveryState.selectedConnectorId, loadDiscovery]);

  // -------------------------------------------------------------------------
  // Connectivity Testing
  // -------------------------------------------------------------------------

  const handleTestConnection = async (connector) => {
    setTestModal({
      open: true,
      loading: true,
      result: null,
      connector,
    });
    try {
      const res = await connectorsApi.testConnection(connector.id);
      if (res.success && res.data) {
        setTestModal((prev) => ({
          ...prev,
          loading: false,
          result: res.data,
        }));
        fetchConnectors();
        fetchHistory();
      } else {
        throw new Error(res.error || 'Connection test returned an error');
      }
    } catch (err) {
      setTestModal((prev) => ({
        ...prev,
        loading: false,
        result: {
          success: false,
          status: 'error',
          latency_ms: 0,
          message: err.message,
          diagnostics: { error: err.message },
          tested_at: new Date().toISOString(),
        },
      }));
    }
  };

  // -------------------------------------------------------------------------
  // Preview Data
  // -------------------------------------------------------------------------

  const handlePreviewEntity = async (connectorId, entityName, entityType = 'table') => {
    setPreviewModal({
      open: true,
      loading: true,
      data: null,
      error: null,
    });
    try {
      const res = await connectorsApi.previewData(connectorId, entityName, entityType);
      if (res.success && res.data) {
        setPreviewModal((prev) => ({
          ...prev,
          loading: false,
          data: res.data,
        }));
      } else {
        throw new Error(res.error || 'Failed to preview data');
      }
    } catch (err) {
      setPreviewModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message,
      }));
    }
  };

  // -------------------------------------------------------------------------
  // Migration Preview Workflow
  // -------------------------------------------------------------------------

  const handleRunMigrationPreview = async () => {
    setMigrationState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const payload = {
        source_connector_id: migrationState.sourceConnectorId,
        destination_connector_id: migrationState.destConnectorId,
        source_entity: migrationState.sourceEntity,
        destination_entity: migrationState.destEntity,
        field_mappings: migrationState.fieldMappings,
      };
      const res = await connectorsApi.previewMigration(payload);
      if (res.success && res.data) {
        setMigrationState((prev) => ({
          ...prev,
          loading: false,
          previewResult: res.data,
        }));
        fetchHistory();
      } else {
        throw new Error(res.error || 'Migration preview generation failed');
      }
    } catch (err) {
      setMigrationState((prev) => ({
        ...prev,
        loading: false,
        error: err.message,
      }));
    }
  };

  // -------------------------------------------------------------------------
  // SharePoint Ingestion Staging
  // -------------------------------------------------------------------------

  const handleStageSharePointFile = async (connectorId, fileId) => {
    setStagingState({ loading: true, result: null, error: null });
    try {
      const payload = {
        connector_id: connectorId,
        file_id: fileId,
        target_pipeline: 'daily_reports',
      };
      const res = await connectorsApi.prepareSharePointIngestion(payload);
      if (res.success && res.data) {
        setStagingState({ loading: false, result: res.data, error: null });
        setBannerNotice(`File successfully staged for platform pipeline (ID: ${res.data.staging_id})`);
        fetchHistory();
      } else {
        throw new Error(res.error || 'Failed to stage SharePoint file');
      }
    } catch (err) {
      setStagingState({ loading: false, result: null, error: err.message });
    }
  };

  // -------------------------------------------------------------------------
  // Connector Save / Modal Submission
  // -------------------------------------------------------------------------

  const handleOpenConfigModal = (type, mode = 'create', connector = null) => {
    setConfigModal({
      open: true,
      mode,
      type,
      connectorId: connector?.id || null,
      formData: {
        name: connector?.name || (type === 'mongodb' ? 'MongoDB Replica Instance' : 'Manufacturing SharePoint'),
        uri: connector?.connection_info?.uri || (type === 'mongodb' ? 'mongodb+srv://user:pass@cluster.mongodb.net/energy_db' : ''),
        database_name: connector?.connection_info?.database_name || 'energy_db',
        auth_database: 'admin',
        replica_set: '',
        ssl: true,
        site_url: connector?.connection_info?.site_url || 'https://company.sharepoint.com/sites/plant-energy',
        tenant_id: connector?.connection_info?.tenant_id || '',
        client_id: connector?.connection_info?.client_id || '',
        client_secret: '',
        default_library: 'Energy & Production Reports',
      },
      submitting: false,
      error: null,
    });
  };

  const handleSubmitConfig = async (e) => {
    e.preventDefault();
    setConfigModal((prev) => ({ ...prev, submitting: true, error: null }));

    try {
      if (configModal.type === 'mongodb') {
        const payload = {
          name: configModal.formData.name,
          uri: configModal.formData.uri,
          database_name: configModal.formData.database_name,
          auth_database: configModal.formData.auth_database,
          replica_set: configModal.formData.replica_set || null,
          ssl: configModal.formData.ssl,
        };
        let res;
        if (configModal.mode === 'create') {
          res = await connectorsApi.createMongoDBConnector(payload);
        } else {
          res = await connectorsApi.updateMongoDBConnector(configModal.connectorId, payload);
        }
        if (!res.success) throw new Error(res.error || 'Failed to save MongoDB connector');
      } else if (configModal.type === 'sharepoint') {
        const payload = {
          name: configModal.formData.name,
          tenant_id: configModal.formData.tenant_id,
          client_id: configModal.formData.client_id,
          client_secret: configModal.formData.client_secret,
          site_url: configModal.formData.site_url,
          default_library: configModal.formData.default_library,
        };
        let res;
        if (configModal.mode === 'create') {
          res = await connectorsApi.createSharePointConnector(payload);
        } else {
          res = await connectorsApi.updateSharePointConnector(configModal.connectorId, payload);
        }
        if (!res.success) throw new Error(res.error || 'Failed to save SharePoint connector');
      }

      setConfigModal((prev) => ({ ...prev, open: false, submitting: false }));
      setBannerNotice('Data connector saved and verified successfully.');
      fetchConnectors();
      fetchHistory();
    } catch (err) {
      setConfigModal((prev) => ({ ...prev, submitting: false, error: err.message }));
    }
  };

  const handleDeleteConnector = async (connectorId) => {
    if (!window.confirm('Are you sure you want to delete this custom data connector?')) {
      return;
    }
    try {
      const res = await connectorsApi.deleteConnector(connectorId);
      if (res.success) {
        setBannerNotice('Connector removed successfully.');
        fetchConnectors();
        fetchHistory();
      } else {
        alert(res.error || 'Failed to delete connector');
      }
    } catch (err) {
      alert(err.message);
    }
  };

  // Helper metrics
  const activeCount = connectors.filter((c) => c.status === 'connected').length;
  const totalCount = connectors.length;

  return (
    <div className="connectors-page">
      {/* Page Header */}
      <div className="connectors-header">
        <div className="connectors-header-info">
          <h1>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <ellipse cx="12" cy="5" rx="9" ry="3"/>
              <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
              <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
            </svg>
            Data Connectors
          </h1>
          <p>Manage enterprise database and document connections across Neon PostgreSQL, MongoDB, and SharePoint.</p>
        </div>
        <div className="connectors-header-actions">
          <button className="btn btn-secondary" onClick={() => { fetchConnectors(); fetchHistory(); }} disabled={loading}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
            </svg>
            Refresh
          </button>
          <button className="btn btn-primary" onClick={() => handleOpenConfigModal('mongodb', 'create')}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add MongoDB
          </button>
          <button className="btn btn-primary" onClick={() => handleOpenConfigModal('sharepoint', 'create')}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Connect SharePoint
          </button>
        </div>
      </div>

      {/* Architecture & Safety Banner */}
      <div className="safety-banner">
        <div className="safety-banner-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <path d="m9 12 2 2 4-4"/>
          </svg>
        </div>
        <div className="safety-banner-content">
          <div className="safety-banner-title">Architectural Boundary & Protection Notice</div>
          <div className="safety-banner-desc">
            <strong>Neon PostgreSQL</strong> is predefined and locked as the platform’s authoritative primary database.
            Credentials and access tokens are strictly masked. Migration execution is guarded (Approval Gated);
            no destructive or automatic bulk writes are performed.
          </div>
        </div>
      </div>

      {bannerNotice && (
        <div className="safety-banner" style={{ borderLeft: '4px solid var(--status-success)', background: 'var(--bg-surface)' }}>
          <div className="safety-banner-content" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--status-success)', fontWeight: 600 }}>{bannerNotice}</span>
            <button className="btn btn-outline btn-sm" onClick={() => setBannerNotice(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {/* KPI Overview Cards */}
      <div className="connectors-kpi-grid">
        <div className="connectors-kpi-card">
          <div className="connectors-kpi-label">Active Connectors</div>
          <div className="connectors-kpi-value">{activeCount} / {totalCount}</div>
          <div className="connectors-kpi-sub">Neon, MongoDB, SharePoint online</div>
        </div>
        <div className="connectors-kpi-card">
          <div className="connectors-kpi-label">Primary Database</div>
          <div className="connectors-kpi-value" style={{ fontSize: '20px', color: 'var(--brand-purple)' }}>Neon PostgreSQL</div>
          <div className="connectors-kpi-sub">Authoritative source & write master</div>
        </div>
        <div className="connectors-kpi-card">
          <div className="connectors-kpi-label">Security & Token Isolation</div>
          <div className="connectors-kpi-value" style={{ color: 'var(--status-success)' }}>100% Masked</div>
          <div className="connectors-kpi-sub">Zero plaintext credential leakage</div>
        </div>
        <div className="connectors-kpi-card">
          <div className="connectors-kpi-label">Migration Guard Status</div>
          <div className="connectors-kpi-value" style={{ color: 'var(--status-warning)' }}>Approval Gated</div>
          <div className="connectors-kpi-sub">Bulk transfer safely guarded</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="connectors-tabs">
        <button
          className={`connectors-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="7" height="9" x="3" y="3" rx="1"/>
            <rect width="7" height="5" x="14" y="3" rx="1"/>
            <rect width="7" height="9" x="14" y="12" rx="1"/>
            <rect width="7" height="5" x="3" y="16" rx="1"/>
          </svg>
          Available Connectors
        </button>
        <button
          className={`connectors-tab-btn ${activeTab === 'sources' ? 'active' : ''}`}
          onClick={() => setActiveTab('sources')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="8" y1="6" x2="21" y2="6"/>
            <line x1="8" y1="12" x2="21" y2="12"/>
            <line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/>
            <line x1="3" y1="12" x2="3.01" y2="12"/>
            <line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
          Connected Sources ({connectors.length})
        </button>
        <button
          className={`connectors-tab-btn ${activeTab === 'discovery' ? 'active' : ''}`}
          onClick={() => setActiveTab('discovery')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.3-4.3"/>
          </svg>
          Discovery Explorer
        </button>
        <button
          className={`connectors-tab-btn ${activeTab === 'migration' ? 'active' : ''}`}
          onClick={() => setActiveTab('migration')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m16 3 4 4-4 4"/>
            <path d="M20 7H4"/>
            <path d="m8 21-4-4 4-4"/>
            <path d="M4 17h16"/>
          </svg>
          Migration & Ingestion
        </button>
        <button
          className={`connectors-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          Sync History ({syncHistory.length})
        </button>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* TAB 1: OVERVIEW & AVAILABLE CONNECTORS */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="section-header">
            <div className="section-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                <line x1="6" y1="6" x2="6.01" y2="6"/>
                <line x1="6" y1="18" x2="6.01" y2="18"/>
              </svg>
              Supported Enterprise Connectors (3 of 3)
            </div>
          </div>

          <div className="available-connectors-grid">
            {/* Card 1: Neon PostgreSQL */}
            <div className="connector-card">
              <div>
                <div className="connector-card-header">
                  <div className="connector-card-icon neon">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <ellipse cx="12" cy="5" rx="9" ry="3"/>
                      <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
                      <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
                    </svg>
                  </div>
                  <div className="connector-card-title-area">
                    <div className="connector-card-title">Neon PostgreSQL</div>
                    <div className="connector-card-badges">
                      <span className="badge badge-primary">Primary Platform DB</span>
                      <span className="badge badge-success">Predefined</span>
                    </div>
                  </div>
                </div>

                <div className="connector-card-desc">
                  The active operational relational database powering factory telemetry, production dimensions, operational findings, and daily SEC calculations.
                </div>

                <ul className="connector-card-features">
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Authoritative migration source
                  </li>
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Live schema & table introspection
                  </li>
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Protected credentials & managed connection pooling
                  </li>
                </ul>
              </div>

              <div className="connector-card-footer">
                <span className="status-indicator">
                  <span className="status-dot connected"></span> Active Primary
                </span>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => {
                    setActiveTab('discovery');
                    loadDiscovery('conn-neon-primary');
                  }}
                >
                  Inspect Schema
                </button>
              </div>
            </div>

            {/* Card 2: MongoDB */}
            <div className="connector-card">
              <div>
                <div className="connector-card-header">
                  <div className="connector-card-icon mongo">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                    </svg>
                  </div>
                  <div className="connector-card-title-area">
                    <div className="connector-card-title">MongoDB</div>
                    <div className="connector-card-badges">
                      <span className="badge badge-secondary">Document Store</span>
                      <span className="badge badge-neutral">Multi-Instance</span>
                    </div>
                  </div>
                </div>

                <div className="connector-card-desc">
                  High-throughput document and time-series database supporting raw meter streams, sensor telemetry, and flexible NoSQL archival.
                </div>

                <ul className="connector-card-features">
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Register multiple MongoDB instances securely
                  </li>
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Database & collection schema discovery
                  </li>
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Source and destination migration prep
                  </li>
                </ul>
              </div>

              <div className="connector-card-footer">
                <span className="status-indicator">
                  <span className="status-dot connected"></span> Ready
                </span>
                <button className="btn btn-outline btn-sm" onClick={() => handleOpenConfigModal('mongodb', 'create')}>
                  Add Instance
                </button>
              </div>
            </div>

            {/* Card 3: SharePoint */}
            <div className="connector-card">
              <div>
                <div className="connector-card-header">
                  <div className="connector-card-icon sharepoint">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                      <polyline points="10 9 9 9 8 9"/>
                    </svg>
                  </div>
                  <div className="connector-card-title-area">
                    <div className="connector-card-title">SharePoint (M365)</div>
                    <div className="connector-card-badges">
                      <span className="badge badge-warning">Cloud Files</span>
                      <span className="badge badge-secondary">OAuth 2.0</span>
                    </div>
                  </div>
                </div>

                <div className="connector-card-desc">
                  Microsoft Graph API integration to discover and ingest factory daily reports in Excel (.xlsx, .xls) and CSV formats.
                </div>

                <ul className="connector-card-features">
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Site & document library discovery
                  </li>
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Excel/CSV report preview & header validation
                  </li>
                  <li>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                    Direct staging into platform daily ingestion pipeline
                  </li>
                </ul>
              </div>

              <div className="connector-card-footer">
                <span className="status-indicator">
                  <span className="status-dot connected"></span> Connected
                </span>
                <button className="btn btn-outline btn-sm" onClick={() => handleOpenConfigModal('sharepoint', 'create')}>
                  Connect Site
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* TAB 2: CONNECTED SOURCES TABLE */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'sources' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="section-header">
            <div className="section-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
                <line x1="4" y1="22" x2="4" y2="15"/>
              </svg>
              Registered Data Sources
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button className="btn btn-secondary btn-sm" onClick={() => handleOpenConfigModal('mongodb', 'create')}>
                + Register MongoDB
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => handleOpenConfigModal('sharepoint', 'create')}>
                + Connect SharePoint
              </button>
            </div>
          </div>

          <div className="data-table-container">
            <table className="connectors-table">
              <thead>
                <tr>
                  <th>Source Name</th>
                  <th>Type</th>
                  <th>Role</th>
                  <th>Endpoint / Target (Masked)</th>
                  <th>Status</th>
                  <th>Last Tested</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {connectors.map((c) => {
                  let endpointDesc = 'Predefined';
                  if (c.type === 'neon_postgres') {
                    endpointDesc = `${c.connection_info?.host || 'ep-pooler.aws.neon.tech'} (Port 5432)`;
                  } else if (c.type === 'mongodb') {
                    endpointDesc = `${c.connection_info?.uri || 'mongodb+srv://...'} [DB: ${c.connection_info?.database_name || ''}]`;
                  } else if (c.type === 'sharepoint') {
                    endpointDesc = `${c.connection_info?.site_url || 'SharePoint Site'} [Lib: ${c.connection_info?.default_library || ''}]`;
                  }

                  return (
                    <tr key={c.id}>
                      <td>
                        <strong style={{ display: 'block', color: 'var(--text-primary)' }}>{c.name}</strong>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ID: {c.id}</span>
                      </td>
                      <td>
                        {c.type === 'neon_postgres' && <span className="badge badge-primary">Neon PostgreSQL</span>}
                        {c.type === 'mongodb' && <span className="badge badge-success">MongoDB</span>}
                        {c.type === 'sharepoint' && <span className="badge badge-secondary">SharePoint</span>}
                      </td>
                      <td>
                        {c.is_primary ? (
                          <span className="badge badge-warning">Primary Source</span>
                        ) : c.role === 'source_destination' ? (
                          <span className="badge badge-neutral">Source / Destination</span>
                        ) : (
                          <span className="badge badge-neutral">File Ingestion</span>
                        )}
                      </td>
                      <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <span style={{ fontFamily: 'monospace', fontSize: '12px' }} title={endpointDesc}>
                          {endpointDesc}
                        </span>
                      </td>
                      <td>
                        <span className="status-indicator">
                          <span className={`status-dot ${c.status}`}></span>
                          <span style={{ textTransform: 'capitalize' }}>{c.status}</span>
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {c.last_tested_at ? formatDateTime(c.last_tested_at) : 'Not tested'}
                        </span>
                      </td>
                      <td>
                        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn-outline btn-sm"
                            title="Test live connectivity"
                            onClick={() => handleTestConnection(c)}
                          >
                            Test
                          </button>
                          <button
                            className="btn btn-outline btn-sm"
                            title="Inspect schema and files"
                            onClick={() => {
                              setActiveTab('discovery');
                              loadDiscovery(c.id);
                            }}
                          >
                            Discover
                          </button>
                          {!c.is_predefined && (
                            <>
                              <button
                                className="btn btn-secondary btn-sm"
                                title="Edit connection configuration"
                                onClick={() => handleOpenConfigModal(c.type, 'edit', c)}
                              >
                                Edit
                              </button>
                              <button
                                className="btn btn-danger-outline btn-sm"
                                title="Delete connector"
                                onClick={() => handleDeleteConnector(c.id)}
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* TAB 3: DISCOVERY EXPLORER */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'discovery' && (
        <div className="discovery-container">
          <div className="discovery-selector-bar">
            <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>Active Source:</span>
            <select
              className="form-select"
              style={{ width: '320px' }}
              value={discoveryState.selectedConnectorId}
              onChange={(e) => loadDiscovery(e.target.value)}
            >
              {connectors.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.type})
                </option>
              ))}
            </select>

            <button
              className="btn btn-secondary btn-sm"
              onClick={() => loadDiscovery(discoveryState.selectedConnectorId)}
              disabled={discoveryState.loading}
            >
              Re-scan Schema
            </button>
          </div>

          {discoveryState.loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              Introspecting metadata and discovering resources...
            </div>
          ) : discoveryState.error ? (
            <div className="conflict-card high">
              <div className="conflict-icon">⚠️</div>
              <div>
                <strong>Discovery Error</strong>
                <p>{discoveryState.error}</p>
              </div>
            </div>
          ) : discoveryState.data ? (
            <div className="discovery-layout">
              {/* Left Sidebar List of Entities */}
              <div className="discovery-sidebar">
                <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  {discoveryState.data.connector_type === 'neon_postgres'
                    ? 'Discovered Tables'
                    : discoveryState.data.connector_type === 'mongodb'
                    ? 'Discovered Collections'
                    : 'Discovered Files'}
                </div>

                <div className="discovery-entity-list">
                  {discoveryState.data.tables?.map((tbl) => (
                    <button
                      key={tbl.table_name}
                      className={`discovery-entity-item ${discoveryState.selectedEntity === tbl.table_name ? 'active' : ''}`}
                      onClick={() => setDiscoveryState((p) => ({ ...p, selectedEntity: tbl.table_name }))}
                    >
                      <span>{tbl.table_name}</span>
                      <span className="badge badge-neutral">{tbl.columns.length} cols</span>
                    </button>
                  ))}

                  {discoveryState.data.collections?.map((col) => (
                    <button
                      key={col.collection_name}
                      className={`discovery-entity-item ${discoveryState.selectedEntity === col.collection_name ? 'active' : ''}`}
                      onClick={() => setDiscoveryState((p) => ({ ...p, selectedEntity: col.collection_name }))}
                    >
                      <span>{col.collection_name}</span>
                      <span className="badge badge-neutral">{col.fields.length} fields</span>
                    </button>
                  ))}

                  {discoveryState.data.files?.map((f) => (
                    <button
                      key={f.file_id}
                      className={`discovery-entity-item ${discoveryState.selectedEntity === f.file_id ? 'active' : ''}`}
                      onClick={() => setDiscoveryState((p) => ({ ...p, selectedEntity: f.file_id }))}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.file_name}</span>
                      <span className={`badge ${f.is_supported ? 'badge-success' : 'badge-danger'}`}>
                        {f.file_extension}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Right Content Panel */}
              <div className="discovery-content-panel">
                {/* Neon Table Details */}
                {discoveryState.data.connector_type === 'neon_postgres' && (
                  (() => {
                    const currentTable = discoveryState.data.tables?.find(
                      (t) => t.table_name === discoveryState.selectedEntity
                    ) || discoveryState.data.tables?.[0];

                    if (!currentTable) return <div>No table selected</div>;

                    return (
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                          <div>
                            <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary)' }}>{currentTable.table_name}</h3>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                              Schema: {currentTable.schema_name} | Est. Rows: {currentTable.row_count.toLocaleString()}
                            </span>
                          </div>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handlePreviewEntity(discoveryState.selectedConnectorId, currentTable.table_name, 'table')}
                          >
                            Preview Sample Rows
                          </button>
                        </div>

                        <div className="data-table-container">
                          <table className="connectors-table">
                            <thead>
                              <tr>
                                <th>Column Name</th>
                                <th>Data Type</th>
                                <th>Nullable</th>
                                <th>Key</th>
                                <th>Sample Value</th>
                              </tr>
                            </thead>
                            <tbody>
                              {currentTable.columns.map((col) => (
                                <tr key={col.name}>
                                  <td><strong>{col.name}</strong></td>
                                  <td><code>{col.data_type}</code></td>
                                  <td>{col.is_nullable ? 'YES' : 'NO'}</td>
                                  <td>{col.is_primary_key ? <span className="badge badge-primary">PK</span> : '-'}</td>
                                  <td><span style={{ fontFamily: 'monospace', color: 'var(--text-secondary)' }}>{col.sample_value || '-'}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })()
                )}

                {/* MongoDB Collection Details */}
                {discoveryState.data.connector_type === 'mongodb' && (
                  (() => {
                    const currentCol = discoveryState.data.collections?.find(
                      (c) => c.collection_name === discoveryState.selectedEntity
                    ) || discoveryState.data.collections?.[0];

                    if (!currentCol) return <div>No collection selected</div>;

                    return (
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                          <div>
                            <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary)' }}>{currentCol.collection_name}</h3>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                              Database: {currentCol.database_name} | Documents: {currentCol.document_count.toLocaleString()} | Size: {(currentCol.estimated_size_kb / 1024).toFixed(1)} MB
                            </span>
                          </div>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handlePreviewEntity(discoveryState.selectedConnectorId, currentCol.collection_name, 'collection')}
                          >
                            Preview Documents
                          </button>
                        </div>

                        <div className="data-table-container">
                          <table className="connectors-table">
                            <thead>
                              <tr>
                                <th>BSON Field Name</th>
                                <th>Inferred Type</th>
                                <th>Index Status</th>
                                <th>Sample Value</th>
                              </tr>
                            </thead>
                            <tbody>
                              {currentCol.fields.map((fld) => (
                                <tr key={fld.field_name}>
                                  <td><strong>{fld.field_name}</strong></td>
                                  <td><code>{fld.field_type}</code></td>
                                  <td>{fld.is_indexed ? <span className="badge badge-success">Indexed</span> : 'Standard'}</td>
                                  <td><span style={{ fontFamily: 'monospace', color: 'var(--text-secondary)' }}>{fld.sample_value || '-'}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })()
                )}

                {/* SharePoint File Details */}
                {discoveryState.data.connector_type === 'sharepoint' && (
                  (() => {
                    const currentFile = discoveryState.data.files?.find(
                      (f) => f.file_id === discoveryState.selectedEntity
                    ) || discoveryState.data.files?.[0];

                    if (!currentFile) return <div>No file selected</div>;

                    return (
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                          <div>
                            <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary)' }}>{currentFile.file_name}</h3>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                              Library: {currentFile.library_name} | Path: {currentFile.path} | Size: {currentFile.size_formatted}
                            </span>
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              className="btn btn-outline btn-sm"
                              onClick={() => handlePreviewEntity(discoveryState.selectedConnectorId, currentFile.file_name, 'file')}
                            >
                              Preview Content
                            </button>
                            {currentFile.is_supported && (
                              <button
                                className="btn btn-primary btn-sm"
                                onClick={() => handleStageSharePointFile(discoveryState.selectedConnectorId, currentFile.file_id)}
                                disabled={stagingState.loading}
                              >
                                {stagingState.loading ? 'Staging...' : 'Stage for Ingestion'}
                              </button>
                            )}
                          </div>
                        </div>

                        <div className="connectors-kpi-grid" style={{ marginBottom: '16px' }}>
                          <div className="connectors-kpi-card" style={{ padding: '12px' }}>
                            <div className="connectors-kpi-label">Format Support</div>
                            <div className="connectors-kpi-value" style={{ fontSize: '16px' }}>
                              {currentFile.is_supported ? (
                                <span style={{ color: 'var(--status-success)' }}>Ingestion Supported</span>
                              ) : (
                                <span style={{ color: 'var(--status-danger)' }}>Unsupported Format</span>
                              )}
                            </div>
                          </div>
                          <div className="connectors-kpi-card" style={{ padding: '12px' }}>
                            <div className="connectors-kpi-label">Report Pipeline Hint</div>
                            <div className="connectors-kpi-value" style={{ fontSize: '14px', color: 'var(--brand-purple)' }}>
                              {currentFile.report_type_hint || 'General Report'}
                            </div>
                          </div>
                          <div className="connectors-kpi-card" style={{ padding: '12px' }}>
                            <div className="connectors-kpi-label">Modified Date</div>
                            <div className="connectors-kpi-value" style={{ fontSize: '14px' }}>
                              {formatDateTime(currentFile.modified_at)}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })()
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* TAB 4: MIGRATION & INGESTION WORKFLOW */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'migration' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Section 1: Database Migration Workflow */}
          <div className="migration-workflow-card">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div className="section-title">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>
                  <path d="M12 12v9"/>
                  <path d="m8 17 4 4 4-4"/>
                </svg>
                Database Schema Migration & Replication Workflow
              </div>
              <span className="badge badge-warning">Approval Gated</span>
            </div>

            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
              Configure source-to-destination schema mappings between Neon PostgreSQL and MongoDB. Validate field types and identify schema conflicts prior to release.
            </p>

            {/* Workflow Selectors */}
            <div className="workflow-select-grid">
              <div className="form-group">
                <label className="form-label">Source Database (Primary)</label>
                <select
                  className="form-select"
                  value={migrationState.sourceConnectorId}
                  onChange={(e) => setMigrationState((p) => ({ ...p, sourceConnectorId: e.target.value }))}
                >
                  <option value="conn-neon-primary">Neon PostgreSQL (Application Primary)</option>
                  <option value="conn-mongo-analytics">MongoDB Plant Telemetry</option>
                </select>
                <span className="form-help">Entity: <code>fact_energy_meter_hourly</code></span>
              </div>

              <div className="arrow-divider">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12"/>
                  <polyline points="12 5 19 12 12 19"/>
                </svg>
              </div>

              <div className="form-group">
                <label className="form-label">Destination Database</label>
                <select
                  className="form-select"
                  value={migrationState.destConnectorId}
                  onChange={(e) => setMigrationState((p) => ({ ...p, destConnectorId: e.target.value }))}
                >
                  <option value="conn-mongo-analytics">MongoDB Plant Telemetry & Time-Series</option>
                  <option value="conn-neon-primary">Neon PostgreSQL (Application Primary)</option>
                </select>
                <span className="form-help">Collection: <code>meter_raw_events</code></span>
              </div>
            </div>

            {/* Field Mappings Table */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>Field & Data Type Mappings (7 fields)</span>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={handleRunMigrationPreview}
                  disabled={migrationState.loading}
                >
                  {migrationState.loading ? 'Analyzing...' : 'Generate Migration Preview & Conflicts'}
                </button>
              </div>

              <div className="data-table-container">
                <table className="mapping-table">
                  <thead>
                    <tr>
                      <th>Source Field (Neon SQL)</th>
                      <th>Source Type</th>
                      <th>Destination Field (MongoDB BSON)</th>
                      <th>Destination Type</th>
                      <th>Compatibility</th>
                    </tr>
                  </thead>
                  <tbody>
                    {migrationState.fieldMappings.map((m) => (
                      <tr key={m.source_field}>
                        <td><strong>{m.source_field}</strong></td>
                        <td><code>{m.source_type}</code></td>
                        <td><strong>{m.destination_field}</strong></td>
                        <td><code>{m.destination_type}</code></td>
                        <td>
                          <span className="badge badge-success">Direct Compatible</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Preview & Conflicts Panel */}
            {migrationState.previewResult && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', background: 'var(--bg-surface-subtle)', padding: '20px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ margin: 0, color: 'var(--text-primary)' }}>
                    Migration Conflict Analysis ({migrationState.previewResult.conflicts.length} Identified)
                  </h4>
                  <span className="badge badge-warning">Status: {migrationState.previewResult.approval_status}</span>
                </div>

                {migrationState.previewResult.conflicts.map((c, i) => (
                  <div key={i} className={`conflict-card ${c.severity === 'HIGH' ? 'high' : ''}`}>
                    <div className="conflict-icon">
                      {c.severity === 'HIGH' ? '🚨' : '⚠️'}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                        [{c.severity}] {c.conflict_type}: {c.message}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        <strong>Recommendation:</strong> {c.recommendation}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Explicit Approval Gate */}
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--status-warning)' }}>
                      🔒 Execution Approval Gate Active
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {migrationState.previewResult.execution_notice}
                    </div>
                  </div>

                  <button
                    className="btn btn-primary"
                    disabled={true}
                    title="Bulk execution is guarded and requires release in a future task"
                  >
                    Approve & Execute (Gated)
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Section 2: SharePoint Ingestion Workflow */}
          <div className="migration-workflow-card">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div className="section-title">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <path d="M12 18v-6"/>
                  <path d="m9 15 3-3 3 3"/>
                </svg>
                SharePoint Cloud Ingestion Pipeline
              </div>
              <span className="badge badge-success">Pipeline Ready</span>
            </div>

            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
              Discovered manufacturing report files from SharePoint document libraries ready for platform ingestion staging.
            </p>

            <div className="data-table-container">
              <table className="connectors-table">
                <thead>
                  <tr>
                    <th>File Name</th>
                    <th>Library</th>
                    <th>Size</th>
                    <th>Report Type Hint</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>daily_energy_consumption_nov2026.xlsx</strong></td>
                    <td>Energy & Production Reports</td>
                    <td>1.4 MB</td>
                    <td>Daily Energy Meter Consumption Report</td>
                    <td><span className="badge badge-success">Compatible</span></td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleStageSharePointFile('conn-sp-mfg', 'sp-file-001')}
                        disabled={stagingState.loading}
                      >
                        Queue for Platform Ingestion
                      </button>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>daily_production_summary_nov2026.csv</strong></td>
                    <td>Energy & Production Reports</td>
                    <td>842 KB</td>
                    <td>Daily Production & Scrap Summary</td>
                    <td><span className="badge badge-success">Compatible</span></td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleStageSharePointFile('conn-sp-mfg', 'sp-file-002')}
                        disabled={stagingState.loading}
                      >
                        Queue for Platform Ingestion
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {stagingState.result && (
              <div className="safety-banner" style={{ borderLeft: '4px solid var(--status-success)', background: 'var(--bg-surface)' }}>
                <div className="safety-banner-content">
                  <div style={{ fontWeight: 600, color: 'var(--status-success)', fontSize: '13px' }}>
                    ✅ File Staged for Pipeline Ingestion (ID: {stagingState.result.staging_id})
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {stagingState.result.message} | Columns matched: {stagingState.result.columns_matched.length}/11 approved schema columns.
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* TAB 5: SYNCHRONIZATION HISTORY */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'history' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="section-header">
            <div className="section-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              Synchronization & Operation History
            </div>
            <button className="btn btn-secondary btn-sm" onClick={fetchHistory} disabled={loadingHistory}>
              Refresh Logs
            </button>
          </div>

          <div className="data-table-container">
            <table className="connectors-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Connector</th>
                  <th>Sync Operation</th>
                  <th>Status</th>
                  <th>Items Processed</th>
                  <th>Duration</th>
                  <th>Details / Diagnostics</th>
                </tr>
              </thead>
              <tbody>
                {syncHistory.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                      No synchronization events recorded.
                    </td>
                  </tr>
                ) : (
                  syncHistory.map((item) => (
                    <tr key={item.id}>
                      <td><span style={{ fontSize: '12px' }}>{formatDateTime(item.timestamp)}</span></td>
                      <td>
                        <strong>{item.connector_name}</strong>
                        <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)' }}>{item.connector_type}</span>
                      </td>
                      <td>
                        <span className="badge badge-neutral">{item.sync_type}</span>
                      </td>
                      <td>
                        <span className="status-indicator">
                          <span className={`status-dot ${item.status.toLowerCase()}`}></span>
                          {item.status}
                        </span>
                      </td>
                      <td>{item.items_processed}</td>
                      <td><code>{item.duration_ms} ms</code></td>
                      <td>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {item.error_details ? (
                            <span style={{ color: 'var(--status-danger)' }}>{item.error_details}</span>
                          ) : item.details ? (
                            Object.entries(item.details).map(([k, v]) => `${k}: ${v}`).slice(0, 2).join(' | ')
                          ) : (
                            'Normal operation'
                          )}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* MODAL: CONNECTION CONFIGURATION (MONGODB / SHAREPOINT) */}
      {/* ------------------------------------------------------------------ */}
      {configModal.open && (
        <div className="modal-overlay">
          <div className="modal-container">
            <div className="modal-header">
              <h2>
                {configModal.mode === 'create' ? 'Register' : 'Edit'}{' '}
                {configModal.type === 'mongodb' ? 'MongoDB Connector' : 'SharePoint Integration'}
              </h2>
              <button
                className="modal-close-btn"
                onClick={() => setConfigModal((p) => ({ ...p, open: false }))}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmitConfig}>
              <div className="modal-body">
                {configModal.error && (
                  <div className="conflict-card high">
                    <div className="conflict-icon">⚠️</div>
                    <div>{configModal.error}</div>
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label">Connector Display Name</label>
                  <input
                    type="text"
                    className="form-input"
                    required
                    value={configModal.formData.name}
                    onChange={(e) => setConfigModal((p) => ({
                      ...p,
                      formData: { ...p.formData, name: e.target.value },
                    }))}
                  />
                </div>

                {configModal.type === 'mongodb' ? (
                  <>
                    <div className="form-group">
                      <label className="form-label">
                        Connection URI
                        <span className="form-help">Credentials are masked upon return</span>
                      </label>
                      <input
                        type="password"
                        className="form-input"
                        placeholder="mongodb+srv://username:password@cluster.mongodb.net/dbname"
                        required
                        value={configModal.formData.uri}
                        onChange={(e) => setConfigModal((p) => ({
                          ...p,
                          formData: { ...p.formData, uri: e.target.value },
                        }))}
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Target Database Name</label>
                      <input
                        type="text"
                        className="form-input"
                        required
                        value={configModal.formData.database_name}
                        onChange={(e) => setConfigModal((p) => ({
                          ...p,
                          formData: { ...p.formData, database_name: e.target.value },
                        }))}
                      />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                      <div className="form-group">
                        <label className="form-label">Auth Database</label>
                        <input
                          type="text"
                          className="form-input"
                          value={configModal.formData.auth_database}
                          onChange={(e) => setConfigModal((p) => ({
                            ...p,
                            formData: { ...p.formData, auth_database: e.target.value },
                          }))}
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Replica Set (Optional)</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. atlas-rs0"
                          value={configModal.formData.replica_set}
                          onChange={(e) => setConfigModal((p) => ({
                            ...p,
                            formData: { ...p.formData, replica_set: e.target.value },
                          }))}
                        />
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="form-group">
                      <label className="form-label">SharePoint Site URL</label>
                      <input
                        type="url"
                        className="form-input"
                        required
                        placeholder="https://company.sharepoint.com/sites/plant-operations"
                        value={configModal.formData.site_url}
                        onChange={(e) => setConfigModal((p) => ({
                          ...p,
                          formData: { ...p.formData, site_url: e.target.value },
                        }))}
                      />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                      <div className="form-group">
                        <label className="form-label">Azure Tenant ID</label>
                        <input
                          type="text"
                          className="form-input"
                          required
                          value={configModal.formData.tenant_id}
                          onChange={(e) => setConfigModal((p) => ({
                            ...p,
                            formData: { ...p.formData, tenant_id: e.target.value },
                          }))}
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Application (Client) ID</label>
                        <input
                          type="text"
                          className="form-input"
                          required
                          value={configModal.formData.client_id}
                          onChange={(e) => setConfigModal((p) => ({
                            ...p,
                            formData: { ...p.formData, client_id: e.target.value },
                          }))}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">
                        Client Secret
                        <span className="form-help">Stored securely; never returned to UI</span>
                      </label>
                      <input
                        type="password"
                        className="form-input"
                        placeholder="••••••••••••••••"
                        required={configModal.mode === 'create'}
                        value={configModal.formData.client_secret}
                        onChange={(e) => setConfigModal((p) => ({
                          ...p,
                          formData: { ...p.formData, client_secret: e.target.value },
                        }))}
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Default Document Library</label>
                      <input
                        type="text"
                        className="form-input"
                        value={configModal.formData.default_library}
                        onChange={(e) => setConfigModal((p) => ({
                          ...p,
                          formData: { ...p.formData, default_library: e.target.value },
                        }))}
                      />
                    </div>
                  </>
                )}
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setConfigModal((p) => ({ ...p, open: false }))}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={configModal.submitting}>
                  {configModal.submitting ? 'Verifying & Saving...' : 'Save Connector'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* MODAL: CONNECTION TESTING & DIAGNOSTICS */}
      {/* ------------------------------------------------------------------ */}
      {testModal.open && (
        <div className="modal-overlay">
          <div className="modal-container">
            <div className="modal-header">
              <h2>Connectivity Diagnostics: {testModal.connector?.name}</h2>
              <button
                className="modal-close-btn"
                onClick={() => setTestModal((p) => ({ ...p, open: false }))}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {testModal.loading ? (
                <div style={{ textAlign: 'center', padding: '30px' }}>
                  <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Testing live connection handshake...
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '8px' }}>
                    Checking DNS, TLS negotiation, and authentication.
                  </div>
                </div>
              ) : testModal.result ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className="status-indicator">
                      <span className={`status-dot ${testModal.result.status}`}></span>
                      <strong style={{ fontSize: '14px' }}>
                        {testModal.result.success ? 'Handshake Successful' : 'Connection Failed'}
                      </strong>
                    </span>
                    <span className="badge badge-primary">
                      Latency: {testModal.result.latency_ms} ms
                    </span>
                  </div>

                  <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {testModal.result.message}
                  </p>

                  <div className="diagnostics-box">
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                      Diagnostic Inspection:
                    </div>
                    {Object.entries(testModal.result.diagnostics).map(([k, v]) => (
                      <div key={k} className="diag-item">
                        <span className="diag-key">{k}</span>
                        <span className="diag-val success">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setTestModal((p) => ({ ...p, open: false }))}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* MODAL: SAMPLE DATA PREVIEW */}
      {/* ------------------------------------------------------------------ */}
      {previewModal.open && (
        <div className="modal-overlay">
          <div className="modal-container" style={{ maxWidth: '850px' }}>
            <div className="modal-header">
              <h2>Sample Data Preview: {previewModal.data?.entity_name}</h2>
              <button
                className="modal-close-btn"
                onClick={() => setPreviewModal((p) => ({ ...p, open: false }))}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {previewModal.loading ? (
                <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                  Loading sample records...
                </div>
              ) : previewModal.error ? (
                <div className="conflict-card high">{previewModal.error}</div>
              ) : previewModal.data ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      Entity Type: <code>{previewModal.data.entity_type}</code> | Total Estimated: {previewModal.data.total_records.toLocaleString()} records
                    </span>
                    <span className="badge badge-success">Loaded Sample</span>
                  </div>

                  <div className="data-table-container" style={{ maxHeight: '350px', overflowY: 'auto' }}>
                    <table className="connectors-table">
                      <thead>
                        <tr>
                          {previewModal.data.columns.map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewModal.data.rows.map((row, idx) => (
                          <tr key={idx}>
                            {previewModal.data.columns.map((col) => (
                              <td key={col} style={{ whiteSpace: 'nowrap' }}>
                                <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                                  {row[col] !== null && row[col] !== undefined ? String(row[col]) : '-'}
                                </span>
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {previewModal.data.validation_notes?.length > 0 && (
                    <div style={{ background: 'var(--bg-surface-subtle)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', fontSize: '12px', color: 'var(--text-secondary)' }}>
                      <strong>Validation Notes:</strong>
                      <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                        {previewModal.data.validation_notes.map((note, i) => (
                          <li key={i}>{note}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setPreviewModal((p) => ({ ...p, open: false }))}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

