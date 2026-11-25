/**
 * Formatting utilities for Industrial Energy Intelligence Platform.
 */

/**
 * Format a numeric value with comma separators and optional fixed decimals.
 * @param {number|string|null|undefined} val
 * @param {number} [decimals=0]
 * @returns {string}
 */
export function formatNumber(val, decimals = 0) {
  if (val === null || val === undefined || isNaN(Number(val))) return '—';
  const num = Number(val);
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format an Indian Rupee currency value.
 * @param {number|string|null|undefined} val
 * @returns {string}
 */
export function formatCurrency(val) {
  if (val === null || val === undefined || isNaN(Number(val))) return '—';
  const num = Number(val);
  return '₹' + num.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Format a percentage value.
 * @param {number|string|null|undefined} val
 * @param {number} [decimals=2]
 * @returns {string}
 */
export function formatPercent(val, decimals = 2) {
  if (val === null || val === undefined || isNaN(Number(val))) return '—';
  const num = Number(val);
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }) + '%';
}

/**
 * Format date string (YYYY-MM-DD) into readable format.
 * @param {string|null|undefined} dateStr
 * @returns {string}
 */
export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const parts = dateStr.split('-');
  if (parts.length === 3) {
    const d = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  }
  return dateStr;
}

/**
 * Format ISO datetime string into readable timestamp.
 * @param {string|null|undefined} dtStr
 * @returns {string}
 */
export function formatDateTime(dtStr) {
  if (!dtStr) return '—';
  try {
    // Preserve timezone-naive representation from backend
    const [datePart, timePart] = dtStr.split('T');
    if (datePart && timePart) {
      const timeClean = timePart.substring(0, 5);
      return `${datePart} ${timeClean}`;
    }
    return dtStr;
  } catch {
    return dtStr;
  }
}

const DETECTOR_TITLE_MAP = {
  LOW_POWER_FACTOR: 'Low power factor',
  ROLLING_BASELINE_SPIKE: 'Rolling baseline spike',
  ROLLING_BASELINE_DROP: 'Rolling baseline drop',
  ENERGY_STATISTICAL_SPIKE: 'Energy statistical spike',
  ENERGY_STATISTICAL_DROP: 'Energy statistical drop',
  UNUSUALLY_LONG_STOPPAGE: 'Unusually long stoppage',
  HIGH_STOPPAGE_ENERGY_RATE: 'High stoppage energy rate',
  PERSISTENT_BASELOAD_INCREASE: 'Persistent baseload increase',
  UNUSUAL_RESTART_BEHAVIOR: 'Unusual restart behavior',
  ZERO_PRODUCTION_STANDBY_ENERGY: 'Zero production standby waste',
  COMPARABLE_PERIOD_ELECTRICITY_INCREASE: 'Comparable period electricity increase',
  COMPARABLE_PERIOD_ELECTRICITY_DECREASE: 'Comparable period electricity decrease',
};

/**
 * Format raw anomaly / detector code into clean sentence-case readable title.
 * e.g. "COMPARABLE_PERIOD_ELECTRICITY_DECREASE" -> "Comparable period electricity decrease"
 * Never defaults to "Low power factor" - uses each record's actual detector or a neutral fallback.
 * @param {string|null|undefined} titleOrType
 * @returns {string}
 */
export function formatFindingTitle(titleOrType) {
  if (!titleOrType) return 'Operational finding';
  // If an object is passed, extract its display field
  if (typeof titleOrType === 'object' && titleOrType !== null) {
    titleOrType =
      titleOrType.title ||
      titleOrType.display_title ||
      titleOrType.finding_title ||
      titleOrType.name ||
      titleOrType.anomaly_type;
  }
  if (!titleOrType || typeof titleOrType !== 'string') return 'Operational finding';
  const text = titleOrType.trim();
  if (!text || text === '[object Object]') return 'Operational finding';

  const normalized = text.toUpperCase().replace(/\s+/g, '_');
  if (DETECTOR_TITLE_MAP[normalized]) {
    return DETECTOR_TITLE_MAP[normalized];
  }

  if (text.includes('_') || text === text.toUpperCase()) {
    const readable = text.replace(/_/g, ' ').toLowerCase();
    return readable.charAt(0).toUpperCase() + readable.slice(1);
  }
  return text;
}


