/**
 * Deterministic Anomaly Detection API Service.
 */

import { apiRequest } from './apiClient';

export const anomalyApi = {
  /**
   * Detect energy statistical anomalies using sample Z-score.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.meter_id]
   * @param {string} [params.start_time] - ISO 8601
   * @param {string} [params.end_time] - ISO 8601
   * @param {number} [params.threshold_z] - Default 3.0
   * @param {number} [params.min_observations] - Default 10
   */
  getStatisticalAnomalies: (params = {}) => apiRequest('/api/anomalies/statistical', { params }),

  /**
   * Detect energy deviations against dynamic historical rolling baselines.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.meter_id]
   * @param {string} [params.start_time]
   * @param {string} [params.end_time]
   * @param {number} [params.window_size] - Default 24
   * @param {number} [params.min_observations] - Default 12
   * @param {number} [params.threshold_z] - Default 3.0
   */
  getRollingAnomalies: (params = {}) => apiRequest('/api/anomalies/rolling', { params }),

  /**
   * Detect readings below power factor compliance threshold.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.meter_id]
   * @param {number} [params.threshold] - Default 0.90
   * @param {string} [params.start_time]
   * @param {string} [params.end_time]
   */
  getLowPowerFactorAnomalies: (params = {}) => apiRequest('/api/anomalies/low-power-factor', { params }),

  /**
   * Detect process meter standby power during zero-output line downtime.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.line_id]
   * @param {string} [params.start_time]
   * @param {string} [params.end_time]
   */
  getZeroProductionStandbyAnomalies: (params = {}) => apiRequest('/api/anomalies/zero-production', { params }),

  /**
   * Run unified anomaly suite returning all 4 detection categories.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_time]
   * @param {string} [params.end_time]
   * @param {number} [params.z_threshold] - Default 3.0
   * @param {number} [params.rolling_window_hours] - Default 24
   * @param {number} [params.pf_threshold] - Default 0.90
   */
  getAllAnomalies: (params = {}) => apiRequest('/api/anomalies/all', { params }),
};
