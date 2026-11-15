/**
 * API service client for Data Connectors.
 * Routes all connector management, testing, schema discovery, migration preview,
 * and sync history through the centralized apiRequest client.
 */

import { apiRequest } from './apiClient';

export const connectorsApi = {
  /**
   * List all registered and predefined connectors with masked credentials.
   * @returns {Promise<Array<object>>}
   */
  async getConnectors() {
    return apiRequest('/api/connectors');
  },

  /**
   * Get single connector details.
   * @param {string} connectorId
   * @returns {Promise<object>}
   */
  async getConnector(connectorId) {
    return apiRequest(`/api/connectors/${connectorId}`);
  },

  /**
   * Register a new MongoDB connector.
   * @param {object} payload
   * @returns {Promise<object>}
   */
  async createMongoDBConnector(payload) {
    return apiRequest('/api/connectors/mongodb', {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    });
  },

  /**
   * Update MongoDB connector.
   * @param {string} connectorId
   * @param {object} payload
   * @returns {Promise<object>}
   */
  async updateMongoDBConnector(connectorId, payload) {
    return apiRequest(`/api/connectors/mongodb/${connectorId}`, {
      init: {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    });
  },

  /**
   * Register a new SharePoint connector.
   * @param {object} payload
   * @returns {Promise<object>}
   */
  async createSharePointConnector(payload) {
    return apiRequest('/api/connectors/sharepoint', {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    });
  },

  /**
   * Update SharePoint connector.
   * @param {string} connectorId
   * @param {object} payload
   * @returns {Promise<object>}
   */
  async updateSharePointConnector(connectorId, payload) {
    return apiRequest(`/api/connectors/sharepoint/${connectorId}`, {
      init: {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    });
  },

  /**
   * Delete a registered custom connector.
   * @param {string} connectorId
   * @returns {Promise<object>}
   */
  async deleteConnector(connectorId) {
    return apiRequest(`/api/connectors/${connectorId}`, {
      init: {
        method: 'DELETE',
      },
    });
  },

  /**
   * Test connector connectivity with latency and diagnostic metrics.
   * @param {string} connectorId
   * @returns {Promise<object>}
   */
  async testConnection(connectorId) {
    return apiRequest(`/api/connectors/${connectorId}/test`, {
      init: {
        method: 'POST',
      },
    });
  },

  /**
   * Discover schemas/tables (Neon), databases/collections (MongoDB), or sites/libraries/files (SharePoint).
   * @param {string} connectorId
   * @returns {Promise<object>}
   */
  async discoverResources(connectorId) {
    return apiRequest(`/api/connectors/${connectorId}/discover`);
  },

  /**
   * Preview sample data records from a table, collection, or SharePoint file.
   * @param {string} connectorId
   * @param {string} entityName
   * @param {string} entityType - 'table' | 'collection' | 'file'
   * @returns {Promise<object>}
   */
  async previewData(connectorId, entityName, entityType = 'table') {
    return apiRequest(`/api/connectors/${connectorId}/preview`, {
      params: {
        entity_name: entityName,
        entity_type: entityType,
      },
    });
  },

  /**
   * Generate migration mapping preview with data type compatibility and conflict identification.
   * Execution is strictly approval-gated.
   * @param {object} payload
   * @returns {Promise<object>}
   */
  async previewMigration(payload) {
    return apiRequest('/api/connectors/migration/preview', {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    });
  },

  /**
   * Prepare a discovered SharePoint file for platform ingestion.
   * @param {object} payload - { connector_id, file_id, target_pipeline }
   * @returns {Promise<object>}
   */
  async prepareSharePointIngestion(payload) {
    return apiRequest('/api/connectors/sharepoint/prepare-ingestion', {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    });
  },

  /**
   * Get connector synchronization, discovery, and test history.
   * @param {number} [limit=50]
   * @returns {Promise<object>}
   */
  async getSyncHistory(limit = 50) {
    return apiRequest('/api/connectors/sync-history/list', {
      params: { limit },
    });
  },
};

