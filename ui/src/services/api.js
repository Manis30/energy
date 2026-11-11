/**
 * Frontend API client service for Industrial Energy Intelligence Platform.
 * Communicates with FastAPI backend through the Vite proxy (/api).
 */

export async function checkBackendHealth() {
  try {
    const response = await fetch('/api/health');
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return { success: true, data };
  } catch (err) {
    return { success: false, error: err.message || 'Unable to connect to backend' };
  }
}
