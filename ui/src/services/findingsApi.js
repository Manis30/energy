/**
 * Operational Findings Lifecycle API Client.
 * Connects frontend to persistent findings, occurrences, and lifecycle transition endpoints.
 */

import { apiRequest } from './apiClient';

export const findingsApi = {
  /**
   * List paginated operational findings with optional filters.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.meter_id]
   * @param {string} [params.line_id]
   * @param {string} [params.status] - 'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'REOPENED', 'ACTIVE'
   * @param {string} [params.severity] - 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'
   * @param {string} [params.anomaly_type]
   * @param {number} [params.limit=50]
   * @param {number} [params.offset=0]
   * @returns {Promise<{items: Array<any>, total: number, limit: number, offset: number}>}
   */
  listFindings: (params = {}) => apiRequest('/api/findings', { params }),

  /**
   * Retrieve full finding detail including occurrences and audit trail.
   * @param {string} findingId
   * @returns {Promise<any>}
   */
  getFindingDetail: (findingId) => apiRequest(`/api/findings/${encodeURIComponent(findingId)}`),

  /**
   * Retrieve end-to-end read-only provenance drill-down for a finding occurrence.
   * @param {string} findingId
   * @param {string} [occurrenceId]
   * @returns {Promise<any>}
   */
  getOccurrenceProvenance: (findingId, occurrenceId) => {
    const url = occurrenceId
      ? `/api/findings/${encodeURIComponent(findingId)}/occurrences/${encodeURIComponent(occurrenceId)}/provenance`
      : `/api/findings/${encodeURIComponent(findingId)}/provenance`;
    return apiRequest(url);
  },

  /**
   * Acknowledge an operational finding (NEW or REOPENED -> ACKNOWLEDGED).
   * @param {string} findingId
   * @param {object} data
   * @param {string} [data.comment]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  acknowledgeFinding: (findingId, data = {}) =>
    apiRequest(`/api/findings/${encodeURIComponent(findingId)}/acknowledge`, {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Start investigation on a finding (NEW, ACKNOWLEDGED, or REOPENED -> INVESTIGATING).
   * @param {string} findingId
   * @param {object} data
   * @param {string} [data.investigation_notes]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  startInvestigation: (findingId, data = {}) =>
    apiRequest(`/api/findings/${encodeURIComponent(findingId)}/investigate`, {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Append diagnostic notes to finding without altering status.
   * @param {string} findingId
   * @param {object} data
   * @param {string} data.notes
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  addInvestigationNotes: (findingId, data) =>
    apiRequest(`/api/findings/${encodeURIComponent(findingId)}/notes`, {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Resolve an operational finding with required resolution notes.
   * @param {string} findingId
   * @param {object} data
   * @param {string} data.resolution_notes
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  resolveFinding: (findingId, data) =>
    apiRequest(`/api/findings/${encodeURIComponent(findingId)}/resolve`, {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Manually reopen a resolved finding with required justification reason.
   * @param {string} findingId
   * @param {object} data
   * @param {string} data.reason
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  reopenFinding: (findingId, data) =>
    apiRequest(`/api/findings/${encodeURIComponent(findingId)}/reopen`, {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Run deterministic anomaly detection suite and synchronize persistent findings.
   * @param {object} [data]
   * @param {string} [data.plant_id]
   * @param {string} [data.meter_id]
   * @param {string} [data.start_time]
   * @param {string} [data.end_time]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  syncFindings: (data = {}) =>
    apiRequest('/api/findings/sync', {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),
};

