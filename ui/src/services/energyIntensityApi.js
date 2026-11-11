/**
 * Energy Intensity and Specific Energy Consumption (SEC) API Service.
 */

import { apiRequest } from './apiClient';

export const energyIntensityApi = {
  /**
   * Get direct process energy and SEC by line without Cartesian inflation.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date] - YYYY-MM-DD
   * @param {string} [params.end_date] - YYYY-MM-DD
   */
  getProcessEnergy: (params = {}) => apiRequest('/api/energy-intensity/process', { params }),

  /**
   * Get total factory SEC and facility utility segregation.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getFactoryEnergy: (params = {}) => apiRequest('/api/energy-intensity/factory', { params }),

  /**
   * Get direct process energy allocated while producing each SKU.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getProductProcessEnergy: (params = {}) => apiRequest('/api/energy-intensity/product', { params }),

  /**
   * Get process standby/idle energy observed during zero-production hours.
   * @param {object} [params]
   * @param {string} [params.plant_id]
   * @param {string} [params.start_date]
   * @param {string} [params.end_date]
   */
  getZeroProductionEnergy: (params = {}) => apiRequest('/api/energy-intensity/zero-production', { params }),
};

