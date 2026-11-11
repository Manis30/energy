/**
 * Energy Analytics API Service.
 */

import { apiRequest } from './apiClient';

export const energyApi = {
  /**
   * Get overall factory energy consumption, cost, and emission totals.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date] - YYYY-MM-DD
   * @param {string} [params.end_date] - YYYY-MM-DD
   */
  getSummary: (params = {}) => apiRequest('/api/energy/summary', { params }),

  /**
   * Get energy consumption breakdown by individual meter.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getByMeter: (params = {}) => apiRequest('/api/energy/by-meter', { params }),

  /**
   * Get energy consumption breakdown by factory area.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getByArea: (params = {}) => apiRequest('/api/energy/by-area', { params }),

  /**
   * Get daily energy consumption trend time-series.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getDailyTrend: (params = {}) => apiRequest('/api/energy/daily-trend', { params }),

  /**
   * Get power factor summary and compliance monitoring.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {number} [params.threshold] - Default 0.90
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getPowerFactorSummary: (params = {}) => apiRequest('/api/energy/power-factor', { params }),
};

