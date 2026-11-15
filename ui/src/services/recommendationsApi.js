/**
 * Operational Recommendations and Corrective Actions API Client.
 * Connects frontend to persistent recommendations, actions, and audit trail endpoints.
 */

import { apiRequest } from './apiClient';

export const recommendationsApi = {
  /**
   * List paginated operational recommendations with optional filters.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.finding_id]
   * @param {string} [params.status] - 'OPEN', 'IN_PROGRESS', 'IMPLEMENTED', 'DISMISSED'
   * @param {string} [params.priority] - 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'
   * @param {string} [params.category]
   * @param {number} [params.limit=50]
   * @param {number} [params.offset=0]
   * @returns {Promise<{items: Array<any>, total: number, limit: number, offset: number}>}
   */
  listRecommendations: (params = {}) => apiRequest('/api/recommendations', { params }),

  /**
   * Retrieve full recommendation detail including actions, evidence, and audit trail.
   * @param {string} recommendationId
   * @returns {Promise<any>}
   */
  getRecommendationDetail: (recommendationId) =>
    apiRequest(`/api/recommendations/${encodeURIComponent(recommendationId)}`),

  /**
   * Manually create a persistent operational recommendation.
   * @param {object} data
   * @param {string} data.plant_id
   * @param {string} data.title
   * @param {string} data.description
   * @param {string} data.category
   * @param {string} [data.priority='MEDIUM']
   * @param {string} [data.finding_id]
   * @param {string} [data.occurrence_id]
   * @param {object} [data.evidence_context]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  createRecommendation: (data) =>
    apiRequest('/api/recommendations', {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Deterministically generate actionable recommendations from an existing energy finding.
   * @param {string} findingId
   * @param {object} [params]
   * @param {string} [params.caller_attribution]
   * @returns {Promise<{generated_count: number, recommendations: Array<any>, message: string}>}
   */
  generateFromFinding: (findingId, params = {}) =>
    apiRequest(`/api/recommendations/generate/${encodeURIComponent(findingId)}`, {
      params,
      init: {
        method: 'POST',
      },
    }),

  /**
   * Transition recommendation lifecycle status (OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED).
   * @param {string} recommendationId
   * @param {object} data
   * @param {string} data.status
   * @param {string} [data.reason]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  updateRecommendationStatus: (recommendationId, data) =>
    apiRequest(`/api/recommendations/${encodeURIComponent(recommendationId)}/status`, {
      init: {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Create a persistent corrective action linked to a recommendation.
   * @param {string} recommendationId
   * @param {object} data
   * @param {string} data.title
   * @param {string} data.description
   * @param {string} [data.owner]
   * @param {string} [data.due_date]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  createAction: (recommendationId, data) =>
    apiRequest(`/api/recommendations/${encodeURIComponent(recommendationId)}/actions`, {
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * List paginated corrective actions with optional filters.
   * @param {object} [params]
   * @param {string} [params.recommendation_id]
   * @param {string} [params.status] - 'OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'
   * @param {string} [params.owner]
   * @param {number} [params.limit=50]
   * @param {number} [params.offset=0]
   * @returns {Promise<{items: Array<any>, total: number, limit: number, offset: number}>}
   */
  listActions: (params = {}) => apiRequest('/api/actions', { params }),

  /**
   * Retrieve single corrective action detail including its audit trail.
   * @param {string} actionId
   * @returns {Promise<any>}
   */
  getActionDetail: (actionId) =>
    apiRequest(`/api/actions/${encodeURIComponent(actionId)}`),

  /**
   * Update corrective action status, ownership, due date, or resolution notes.
   * @param {string} actionId
   * @param {object} data
   * @param {string} [data.title]
   * @param {string} [data.description]
   * @param {string} [data.status]
   * @param {string} [data.owner]
   * @param {boolean} [data.clear_owner]
   * @param {string} [data.due_date]
   * @param {boolean} [data.clear_due_date]
   * @param {string} [data.resolution_notes]
   * @param {string} [data.caller_attribution]
   * @returns {Promise<any>}
   */
  updateAction: (actionId, data) =>
    apiRequest(`/api/actions/${encodeURIComponent(actionId)}`, {
      init: {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    }),

  /**
   * Retrieve append-only audit trail for an operational recommendation.
   * @param {string} recommendationId
   * @param {object} [params]
   * @param {number} [params.limit=100]
   * @returns {Promise<Array<any>>}
   */
  getRecommendationAudit: (recommendationId, params = {}) =>
    apiRequest(`/api/v1/recommendations/${encodeURIComponent(recommendationId)}/audit`, { params }),

  /**
   * Retrieve append-only audit trail for a corrective action.
   * @param {string} actionId
   * @param {object} [params]
   * @param {number} [params.limit=100]
   * @returns {Promise<Array<any>>}
   */
  getActionAudit: (actionId, params = {}) =>
    apiRequest(`/api/v1/actions/${encodeURIComponent(actionId)}/audit`, { params }),
};

