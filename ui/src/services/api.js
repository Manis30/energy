/**
 * Frontend API client service for Industrial Energy Intelligence Platform.
 * Communicates with FastAPI backend through the Vite proxy (/api).
 */

import { ApiError, apiRequest } from './apiClient';
import { energyApi } from './energyApi';
import { productionApi } from './productionApi';
import { energyIntensityApi } from './energyIntensityApi';
import { anomalyApi } from './anomalyApi';
import { assistantApi, sendAssistantMessage } from './assistantApi';

/**
 * Health check verification against /api/health.
 * @returns {Promise<{ success: boolean, data?: any, error?: string }>}
 */
export async function checkBackendHealth() {
  try {
    const data = await apiRequest('/api/health');
    return { success: true, data };
  } catch (err) {
    return {
      success: false,
      error: err.message || 'Unable to connect to backend',
      status: err.status || 0,
    };
  }
}

export {
  ApiError,
  apiRequest,
  energyApi,
  productionApi,
  energyIntensityApi,
  anomalyApi,
  assistantApi,
  sendAssistantMessage,
};

export default {
  checkBackendHealth,
  energy: energyApi,
  production: productionApi,
  intensity: energyIntensityApi,
  anomalies: anomalyApi,
  assistant: assistantApi,
};
