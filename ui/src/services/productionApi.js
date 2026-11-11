/**
 * Production Analytics API Service.
 */

import { apiRequest } from './apiClient';

export const productionApi = {
  /**
   * Get overall factory production output, scrap rates, downtime, and OEE evaluation.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.product_id]
   * @param {string} [params.shift_id]
   * @param {string} [params.start_date] - YYYY-MM-DD
   * @param {string} [params.end_date] - YYYY-MM-DD
   */
  getSummary: (params = {}) => apiRequest('/api/production/summary', { params }),

  /**
   * Get production volume and performance metrics by line.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getByLine: (params = {}) => apiRequest('/api/production/by-line', { params }),

  /**
   * Get production output and scrap metrics grouped by product SKU.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getByProduct: (params = {}) => apiRequest('/api/production/by-product', { params }),

  /**
   * Get production output grouped by shift (Shift A, Shift B, Shift C).
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getByShift: (params = {}) => apiRequest('/api/production/by-shift', { params }),

  /**
   * Get factory downtime minutes and occurrences by stoppage reason.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getDowntimeByReason: (params = {}) => apiRequest('/api/production/downtime-by-reason', { params }),

  /**
   * Get daily production output and scrap time series.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getDailyTrend: (params = {}) => apiRequest('/api/production/daily-trend', { params }),
};

