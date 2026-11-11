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

