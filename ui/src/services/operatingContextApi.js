/**
 * Operating Context & Energy Analysis API Service.
 */

import { apiRequest } from './apiClient';

export const operatingContextApi = {
  /**
   * Get operating context summary statistics (coverage, observations, stoppage counts).
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.start_date] - YYYY-MM-DD
   * @param {string} [params.end_date] - YYYY-MM-DD
   */
  getSummary: (params = {}) => apiRequest('/api/operating-context/summary', { params }),

  /**
   * Get hourly operating observations joining production, energy, telemetry, calendar.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   * @param {number} [params.limit]
   */
  getObservations: (params = {}) => apiRequest('/api/operating-context/observations', { params }),

  /**
   * List detected stoppage episodes with restart status and energy consumed.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   * @param {number} [params.min_duration_hours]
   * @param {string} [params.downtime_reason]
   */
  getStoppages: (params = {}) => apiRequest('/api/operating-context/stoppages', { params }),

  /**
   * Get stoppage episode details including constituent hours and historical baseline comparison.
   * @param {string} episodeId
   */
  getStoppageDetail: (episodeId) => apiRequest(`/api/operating-context/stoppages/${encodeURIComponent(episodeId)}`),

  /**
   * Get qualified utility telemetry observations (compressed air, chilled water, etc.).
   * Distinguishes compressor electrical consumption from delivery flow and pressure.
   * @param {object} [params]
   */
  getUtilities: (params = {}) => apiRequest('/api/operating-context/utilities', { params }),
};
