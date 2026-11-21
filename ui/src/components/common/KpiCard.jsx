import React, { useState, useEffect, useMemo } from 'react';
import './kpi-card.css';

/**
 * Universal KPI Card component for the Industrial Energy Intelligence platform.
 * Replicates the executive design system from the reference image:
 * - Clean white card with soft rounded corners (border-radius: 18px)
 * - Header row: compact title at top-left, soft lavender icon badge at top-right
 * - Metric row: large, bold numeric value in dark navy
 * - Bottom row: full-width animated sparkline with lavender gradient area fill
 * - Animatic draw effect: line draws from left to right on page load or reload
 */

const ACCENT_COLOR_MAP = {
  purple: '#7c3aed',
  blue: '#4d8eeb',
  cyan: '#31b7c3',
  teal: '#31b7c3',
  green: '#10b981',
  success: '#10b981',
  orange: '#f58a3a',
  warning: '#f58a3a',
  red: '#ef4444',
  danger: '#ef4444',
  navy: '#1f2f59',
};

/**
 * Deterministic aesthetic series for cards without explicit historical sparkline series.
 * Produces smooth wavy or linear upward trends matching the reference design:
 * - Card 1 (Total Energy Consumption): rhythmic gentle oscillation trending upward
 * - Card 2 (Energy Cost): smooth upward linear diagonal slope
 */
function getAestheticFallbackSeries(idOrTitle = '') {
  const str = String(idOrTitle).toLowerCase();
  if (str.includes('cost') || str.includes('spend') || str.includes('target') || str.includes('achievement')) {
    // Smooth upward linear slope matching Reference Card 2 (Energy Cost)
    return [10, 12, 14, 16, 18, 20, 22, 24, 26];
  }
  if (str.includes('co2') || str.includes('emission') || str.includes('pf') || str.includes('factor')) {
    // Progressive gentle slope
    return [9, 11, 10, 14, 13, 17, 16, 21, 20, 25];
  }
  if (str.includes('prod') || str.includes('unit') || str.includes('actual') || str.includes('good') || str.includes('valid')) {
    // Stepped industrial output trend
    return [10, 13, 12, 16, 15, 19, 18, 22, 21, 26];
  }
  // Default: gentle upward fluctuation matching Reference Card 1 (Total Energy Consumption)
  return [10, 14, 13, 18, 16, 22, 20, 26];
}

/**
 * Generate smooth SVG path coordinates spanning the full card width (0 to width)
 * leaving an area fill underneath that bleeds into the bottom corners.
 * Also calculates exact mathematical path arc length for smooth left-to-right drawing animation.
 */
export function generateSparklinePaths(series, width = 300, height = 48, paddingBottom = 4, paddingTop = 8) {
  if (!Array.isArray(series) || series.length < 2) return null;
  const validNums = series.map(Number).filter((n) => Number.isFinite(n));
  if (validNums.length < 2) return null;

  const min = Math.min(...validNums);
  const max = Math.max(...validNums);
  const range = max - min || 1;
  const effectiveHeight = height - paddingBottom - paddingTop;

  const points = validNums.map((val, idx) => {
    const x = Number(((idx / (validNums.length - 1)) * width).toFixed(2));
    const normalizedY = (val - min) / range;
    const y = Number((height - paddingBottom - normalizedY * effectiveHeight).toFixed(2));
    return { x, y };
  });

  let linePath = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    linePath += ` L ${points[i].x} ${points[i].y}`;
  }

  const areaPath = `${linePath} L ${width} ${height} L 0 ${height} Z`;

  let totalLength = 0;
  for (let i = 1; i < points.length; i++) {
    totalLength += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
  }
  const pathLength = Math.ceil(totalLength) + 15;

  return { linePath, areaPath, pathLength };
}

export default function KpiCard({
  title,
  value,
  unit,
  icon,
  accent = 'purple',
  secondary,
  loading = false,
  unavailable = false,
  badge,
  tooltip,
  onClick,
  isActive = false,
  active = false,
  className = '',
  style = {},
  id,
  minimal = false,
  trendLabel = 'Cumulative',
  trendPeriod,
  sparklineData = null,
}) {
  const isSelected = isActive || active;
  const isClickable = Boolean(onClick);

  // Animation trigger key on mount or value change
  const [animKey, setAnimKey] = useState(0);
  useEffect(() => {
    setAnimKey((prev) => prev + 1);
  }, [value, title]);

  // Normalize accent class
  const accentClass = `accent-${accent || 'purple'}`;
  const iconAccentClass = accent || 'purple';
  const accentHex = ACCENT_COLOR_MAP[accent] || '#7c3aed';

  // Determine if the value is deemed unavailable
  const isUnavailable =
    unavailable ||
    value === null ||
    value === undefined ||
    value === '' ||
    value === 'Unavailable' ||
    value === '—';

  // Compute sparkline path: use actual data if provided, otherwise use aesthetic fallback
  const sparkPaths = useMemo(() => {
    const dataToUse =
      Array.isArray(sparklineData) && sparklineData.length >= 2
        ? sparklineData
        : getAestheticFallbackSeries(id || title);

    return generateSparklinePaths(dataToUse, 300, 32, 2, 5);
  }, [sparklineData, id, title]);

  const gradientId = id ? `spark-grad-${id}` : `spark-grad-${(title || 'kpi').replace(/\s+/g, '-').toLowerCase()}`;

  return (
    <div
      id={id}
      className={`kpi-card ${accentClass} ${minimal ? 'kpi-card-minimal' : ''} ${isSelected ? 'active-filter' : ''} ${isClickable ? 'clickable' : ''} ${className}`}
      onClick={onClick}
      title={tooltip || (typeof title === 'string' ? title : undefined)}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick(e);
              }
            }
          : undefined
      }
      style={style}
    >
      <div className="kpi-card-content">
        {/* Top Header Row: Title on Left, Icon Badge on Right */}
        <div className="kpi-card-header">
          {loading ? (
            <div className="kpi-skeleton-title" />
          ) : (
            <span className="kpi-title">{title}</span>
          )}

          {icon && (
            <div className={`kpi-icon-badge ${iconAccentClass}`} aria-hidden="true">
              {icon}
            </div>
          )}
        </div>

        {/* Primary Metric Value Row */}
        <div className="kpi-value-row">
          {loading ? (
            <div className="kpi-skeleton-value" />
          ) : (
            <>
              <span className={`kpi-value ${isUnavailable ? 'unavailable' : ''}`}>
                {value ?? 'Unavailable'}
              </span>
              {unit && !isUnavailable && <span className="kpi-unit">{unit}</span>}
              {badge && (
                <span
                  className={`kpi-badge ${
                    typeof badge === 'object' ? badge.variant || 'info' : 'info'
                  }`}
                >
                  {typeof badge === 'object' ? badge.text : badge}
                </span>
              )}
            </>
          )}
        </div>

        {/* Supporting subtitle/secondary text if present and not minimal */}
        {!minimal && secondary && (
          <div className="kpi-sublabel">
            <span title={typeof secondary === 'string' ? secondary : undefined}>
              {secondary}
            </span>
          </div>
        )}
      </div>

      {/* Bottom Animated Sparkline with Lavender Area Fill */}
      {sparkPaths && !loading && (
        <div className="kpi-sparkline-wrap" aria-hidden="true">
          <svg
            viewBox="0 0 300 32"
            preserveAspectRatio="none"
            className="kpi-sparkline-svg"
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.14" />
                <stop offset="100%" stopColor="#7c3aed" stopOpacity="0.01" />
              </linearGradient>
            </defs>
            <path
              key={`area-${animKey}`}
              d={sparkPaths.areaPath}
              fill={`url(#${gradientId})`}
              className="kpi-sparkline-area"
            />
            <path
              key={`line-${animKey}`}
              d={sparkPaths.linePath}
              fill="none"
              stroke="#7c3aed"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{
                '--path-len': sparkPaths.pathLength,
                strokeDasharray: sparkPaths.pathLength,
                strokeDashoffset: sparkPaths.pathLength,
              }}
              className="kpi-sparkline-line"
            />
          </svg>
        </div>
      )}
    </div>
  );
}

/**
 * Responsive grid container for KPI cards.
 * Defaults to 4 columns on desktop, 2 on tablet, and 1 on mobile.
 */
export function KpiGrid({ children, columns, className = '', style = {} }) {
  const customStyle = columns
    ? { gridTemplateColumns: `repeat(${columns}, 1fr)`, ...style }
    : style;

  return (
    <div className={`kpi-grid ${className}`} style={customStyle}>
      {children}
    </div>
  );
}
