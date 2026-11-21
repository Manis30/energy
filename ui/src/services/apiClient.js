/**
 * Core API Client for Industrial Energy Intelligence Platform.
 * Centralized fetch handler routing all requests through the Vite reverse proxy (/api).
 */

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status
   * @param {any} [data]
   */
  constructor(message, status, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

/**
 * Builds a valid query string from a parameters dictionary.
 * Filters out null, undefined, and empty string values.
 *
 * @param {Record<string, any>} [params={}]
 * @returns {string} Query string with leading '?' or empty string.
 */
export function buildQueryString(params = {}) {
  if (!params || typeof params !== 'object') return '';
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      searchParams.append(key, String(value));
    }
  }

  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

/**
 * Centralized fetch request wrapper.
 *
 * @param {string} endpoint - Path, e.g. '/api/energy/summary' or '/energy/summary'
 * @param {object} [config={}]
 * @param {Record<string, any>} [config.params] - Optional query parameters
 * @param {RequestInit} [config.init] - Fetch options (method, headers, body, etc.)
 * @returns {Promise<any>}
 */
export async function apiRequest(endpoint, { params = {}, init = {} } = {}) {
  const normalizedEndpoint = endpoint.startsWith('/api')
    ? endpoint
    : `/api${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const queryString = buildQueryString(params);
  const url = `${normalizedEndpoint}${queryString}`;

  let response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: 'application/json',
        ...(init.headers || {}),
      },
      ...init,
    });
  } catch (networkError) {
    throw new ApiError(
      networkError.message || 'Network error: Failed to connect to server via Vite proxy.',
      0,
      { originalError: networkError }
    );
  }

  let data = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (parseError) {
      throw new ApiError(
        `Failed to parse JSON response from ${url}: ${parseError.message}`,
        response.status
      );
    }
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    if (data && typeof data === 'object') {
      if (Array.isArray(data.detail)) {
        message = data.detail.map((d) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d))).join('; ');
      } else if (typeof data.detail === 'object' && data.detail !== null) {
        message = JSON.stringify(data.detail);
      } else {
        message = data.detail || data.message || data.error || message;
      }
    } else if (typeof data === 'string' && data.trim()) {
      message = data.trim();
    }

    throw new ApiError(message, response.status, data);
  }

  return data;
}

