import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { energyIntensityApi } from '../../services';
import { formatCurrency, formatDate, formatNumber } from '../../utils/formatters';
import './EnergyIntensityTrendsSection.css';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

const formatCoverageBadge = (cov) => {
  if (!cov) return { text: 'Unknown', statusClass: 'cov-unknown' };
  const rawStatus = cov.coverage_status || 'UNKNOWN';
  const statusLabel = rawStatus.charAt(0).toUpperCase() + rawStatus.slice(1).toLowerCase();
  const pct = cov.coverage_percentage != null ? `${Math.round(Number(cov.coverage_percentage))}%` : '';
  const text = pct ? `${statusLabel} · ${pct}` : statusLabel;

  const isFull = rawStatus === 'FULL' || Number(cov.coverage_percentage) >= 99.5;
  const isPartial = rawStatus === 'PARTIAL' || (Number(cov.coverage_percentage) >= 80 && !isFull);
  const statusClass = isFull ? 'cov-full' : isPartial ? 'cov-partial' : 'cov-low';

  return { text, statusClass };
};

function CustomIntensityTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip" style={{ backgroundColor: 'var(--chart-tooltip-bg, #ffffff)', border: '1px solid var(--chart-tooltip-border, #e2e8f0)', borderRadius: '6px', padding: '0.65rem 0.85rem', color: 'var(--chart-tooltip-text, #1f2f59)', fontSize: '0.78rem', boxShadow: 'var(--shadow-md)' }}>
        <div style={{ fontWeight: 700, marginBottom: '0.35rem', borderBottom: '1px solid var(--border-color, #e2e8f0)', paddingBottom: '0.25rem', color: 'var(--text-primary)' }}>
          {data.period_start === data.period_end ? formatDate(data.period_start) : `${data.period_start} – ${data.period_end}`} ({data.plant_id})
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', margin: '0.2rem 0' }}>
          <span style={{ color: 'var(--brand-purple)' }}>● Electricity Intensity:</span>
          <strong style={{ color: 'var(--text-primary)' }}>{hasNumber(data.electricity_intensity_kwh_per_good_unit) ? `${formatNumber(data.electricity_intensity_kwh_per_good_unit, 4)} kWh/good unit` : 'Unavailable'}</strong>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', margin: '0.2rem 0' }}>
          <span style={{ color: 'var(--brand-blue)' }}>● Cost Intensity:</span>
          <strong style={{ color: 'var(--text-primary)' }}>{hasNumber(data.cost_intensity_inr_per_good_unit) ? `${formatCurrency(data.cost_intensity_inr_per_good_unit)}/good unit` : 'Unavailable'}</strong>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', margin: '0.2rem 0' }}>
          <span style={{ color: 'var(--brand-cyan)' }}>● Emissions Intensity:</span>
          <strong style={{ color: 'var(--text-primary)' }}>{hasNumber(data.emissions_intensity_co2e_per_good_unit) ? `${formatNumber(data.emissions_intensity_co2e_per_good_unit, 4)} kg CO₂e/good unit` : 'Unavailable'}</strong>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', margin: '0.2rem 0', paddingTop: '0.25rem', borderTop: '1px dashed var(--border-color, #e2e8f0)' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Numerator (Energy):</span>
          <span style={{ color: 'var(--text-primary)' }}>{hasNumber(data.eligible_energy_kwh) ? `${formatNumber(data.eligible_energy_kwh, 2)} kWh` : 'Unavailable'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', margin: '0.2rem 0' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Denominator (Good FAL):</span>
          <span style={{ color: 'var(--text-primary)' }}>{hasNumber(data.matched_good_qty) ? `${formatNumber(data.matched_good_qty, 0)} units` : 'Unavailable'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', margin: '0.2rem 0' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Coverage:</span>
          <span style={{ color: data.coverage?.coverage_status === 'FULL' ? 'var(--status-success, #10b981)' : 'var(--status-warning, #f58a3a)' }}>
            {data.coverage?.coverage_status} ({data.coverage?.coverage_percentage}% • {data.coverage?.complete_matched_hours}/{data.coverage?.expected_plant_hours} hrs)
          </span>
        </div>
      </div>
    );
  }
  return null;
}

export default function EnergyIntensityTrendsSection({
  selectedPlant = null,
  dateRange,
  selectedShift = 'ALL',
}) {
  const [grain, setGrain] = useState('daily');
  const [groupByPlant, setGroupByPlant] = useState(false);
  const [activeMetric, setActiveMetric] = useState('electricity'); // 'electricity', 'cost', 'emissions'
  const [expandedBucketKey, setExpandedBucketKey] = useState(null);

  // Pagination state (client-side, 5 rows default)
  const [pageSize, setPageSize] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);

  // Sorting state (applied before pagination)
  const [sortField, setSortField] = useState('period_start');
  const [sortDirection, setSortDirection] = useState('asc'); // 'asc' | 'desc'

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [trendData, setTrendData] = useState(null);

  const loadTrends = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const startDate = dateRange?.startDate || dateRange?.start_date;
      const endDate = dateRange?.endDate || dateRange?.end_date;
      const params = {
        grain,
        group_by_plant: groupByPlant,
        ...(selectedPlant ? { plant_id: selectedPlant } : {}),
        ...(startDate ? { start_date: startDate } : {}),
        ...(endDate ? { end_date: endDate } : {}),
      };
      const res = await energyIntensityApi.getTrends(params);
      setTrendData(res);
    } catch (err) {
      console.error('Failed to load energy intensity trends:', err);
      setError(err?.message || 'Failed to retrieve energy intensity trends.');
    } finally {
      setLoading(false);
    }
  }, [selectedPlant, dateRange, grain, groupByPlant]);

  useEffect(() => {
    loadTrends();
  }, [loadTrends]);

  const buckets = trendData?.buckets || [];

  // Reset to page 1 whenever filters, date range, plant, grain, or page size change
  useEffect(() => {
    setCurrentPage(1);
    setExpandedBucketKey(null);
  }, [dateRange, selectedPlant, grain, groupByPlant, pageSize]);

  // Handle column sort toggling
  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
    setCurrentPage(1);
  };

  // Compare helper putting null/unavailable values at the end
  const compareNumeric = (aRaw, bRaw, dir) => {
    const aValid = hasNumber(aRaw);
    const bValid = hasNumber(bRaw);
    if (!aValid && !bValid) return 0;
    if (!aValid) return 1;
    if (!bValid) return -1;
    const aNum = Number(aRaw);
    const bNum = Number(bRaw);
    return dir === 'asc' ? aNum - bNum : bNum - aNum;
  };

  const compareString = (aStr, bStr, dir) => {
    const aVal = (aStr || '').toString();
    const bVal = (bStr || '').toString();
    return dir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  };

  // Apply sorting to the full filtered dataset BEFORE pagination
  const sortedBuckets = useMemo(() => {
    if (!sortField) return buckets;
    return [...buckets].sort((a, b) => {
      switch (sortField) {
        case 'period_start':
          return compareString(a.period_start, b.period_start, sortDirection);
        case 'plant_id':
          return compareString(a.plant_id, b.plant_id, sortDirection);
        case 'electricity_intensity':
          return compareNumeric(a.electricity_intensity_kwh_per_good_unit, b.electricity_intensity_kwh_per_good_unit, sortDirection);
        case 'cost_intensity':
          return compareNumeric(a.cost_intensity_inr_per_good_unit, b.cost_intensity_inr_per_good_unit, sortDirection);
        case 'emissions_intensity':
          return compareNumeric(a.emissions_intensity_co2e_per_good_unit, b.emissions_intensity_co2e_per_good_unit, sortDirection);
        case 'good_qty':
          return compareNumeric(a.matched_good_qty, b.matched_good_qty, sortDirection);
        case 'coverage':
          return compareNumeric(a.coverage?.coverage_percentage, b.coverage?.coverage_percentage, sortDirection);
        default:
          return 0;
      }
    });
  }, [buckets, sortField, sortDirection]);

  // Pagination metrics
  const totalRecords = sortedBuckets.length;
  const totalPages = Math.max(1, Math.ceil(totalRecords / pageSize));
  const startRecord = totalRecords > 0 ? (currentPage - 1) * pageSize + 1 : 0;
  const endRecord = Math.min(currentPage * pageSize, totalRecords);

  // Clamp current page if totalPages shrinks
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  // Paginated rows for the table only
  const paginatedBuckets = useMemo(() => {
    const startIdx = (currentPage - 1) * pageSize;
    return sortedBuckets.slice(startIdx, startIdx + pageSize);
  }, [sortedBuckets, currentPage, pageSize]);

  // Chart data preparation - Uses the full buckets dataset (unpaginated)
  const chartData = useMemo(() => {
    return buckets.map((b, idx) => ({
      ...b,
      index: idx,
      date_label: b.grain === 'monthly' ? b.period_start.substring(0, 7) : b.period_start,
      elec_intensity_num: hasNumber(b.electricity_intensity_kwh_per_good_unit) ? Number(b.electricity_intensity_kwh_per_good_unit) : null,
      cost_intensity_num: hasNumber(b.cost_intensity_inr_per_good_unit) ? Number(b.cost_intensity_inr_per_good_unit) : null,
      emissions_intensity_num: hasNumber(b.emissions_intensity_co2e_per_good_unit) ? Number(b.emissions_intensity_co2e_per_good_unit) : null,
    }));
  }, [buckets]);

  const metricConfig = {
    electricity: {
      key: 'elec_intensity_num',
      name: 'Electricity Intensity',
      unit: 'kWh / good finished unit',
      color: '#a855f7',
    },
    cost: {
      key: 'cost_intensity_num',
      name: 'Estimated Cost Intensity',
      unit: '₹ / good finished unit',
      color: '#38bdf8',
    },
    emissions: {
      key: 'emissions_intensity_num',
      name: 'Estimated Emissions Intensity',
      unit: 'kg CO₂e / good finished unit',
      color: '#2dd4bf',
    },
  };

  const currentConfig = metricConfig[activeMetric] || metricConfig.electricity;

  const renderSortTh = (label, field, unit = null, align = 'left') => {
    const isSorted = sortField === field;
    return (
      <th
        className={`intensity-th intensity-th-${align}`}
        onClick={() => handleSort(field)}
        title={`Sort by ${label}`}
        role="columnheader"
        aria-sort={isSorted ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleSort(field);
          }
        }}
      >
        <div className={`intensity-th-content intensity-th-align-${align}`}>
          <span className="intensity-th-label">{label}</span>
          <span className={`intensity-sort-arrow ${isSorted ? 'is-sorted' : ''}`}>
            {isSorted ? (sortDirection === 'asc' ? '▲' : '▼') : '↕'}
          </span>
        </div>
        {unit && <div className="intensity-th-unit">{unit}</div>}
      </th>
    );
  };

  return (
    <div className="energy-trend-chart-card chart-card" style={{ marginBottom: '1.5rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius-md, 8px)', padding: '1.25rem', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-sm)' }}>
      {/* Header and Controls Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Energy Intelligence Intensity Trends
            </h3>
            <span
              style={{
                fontSize: '0.72rem',
                padding: '0.15rem 0.5rem',
                borderRadius: '9999px',
                fontWeight: 600,
                backgroundColor: 'rgba(111, 61, 186, 0.12)',
                color: 'var(--brand-purple)',
                border: '1px solid rgba(111, 61, 186, 0.25)',
              }}
            >
              Denominator: Good Finished Units
            </span>
            {selectedShift && selectedShift !== 'ALL' && (
              <span
                style={{
                  fontSize: '0.72rem',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '9999px',
                  fontWeight: 600,
                  backgroundColor: 'rgba(245, 158, 11, 0.12)',
                  color: '#b45309',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                }}
                title="Intensity ratios require total facility finished output and are available for all shifts combined"
              >
                Facility-wide metric (available only for all shifts)
              </span>
            )}
          </div>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Strict ratio of sums across buckets (never averaged daily ratios). Segregates facility utilities to plant boundary.
          </p>
        </div>

        {/* Toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Metric Selector */}
          <div style={{ display: 'flex', background: 'var(--bg-surface-subtle)', borderRadius: '6px', padding: '2px', border: '1px solid var(--border-color)' }}>
            <button
              type="button"
              onClick={() => setActiveMetric('electricity')}
              style={{
                padding: '0.3rem 0.65rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: activeMetric === 'electricity' ? 'var(--brand-purple)' : 'transparent',
                color: activeMetric === 'electricity' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              Electricity (kWh)
            </button>
            <button
              type="button"
              onClick={() => setActiveMetric('cost')}
              style={{
                padding: '0.3rem 0.65rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: activeMetric === 'cost' ? 'var(--brand-blue)' : 'transparent',
                color: activeMetric === 'cost' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              Cost (₹)
            </button>
            <button
              type="button"
              onClick={() => setActiveMetric('emissions')}
              style={{
                padding: '0.3rem 0.65rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: activeMetric === 'emissions' ? 'var(--brand-cyan)' : 'transparent',
                color: activeMetric === 'emissions' ? '#1f2f59' : 'var(--text-secondary)',
              }}
            >
              Emissions (kg CO₂e)
            </button>
          </div>

          {/* Grain Selector: Daily / Monthly */}
          <div style={{ display: 'flex', background: 'var(--bg-surface-subtle)', borderRadius: '6px', padding: '2px', border: '1px solid var(--border-color)' }}>
            <button
              type="button"
              onClick={() => setGrain('daily')}
              style={{
                padding: '0.3rem 0.65rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: grain === 'daily' ? 'var(--brand-purple)' : 'transparent',
                color: grain === 'daily' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              Daily
            </button>
            <button
              type="button"
              onClick={() => setGrain('monthly')}
              style={{
                padding: '0.3rem 0.65rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: grain === 'monthly' ? 'var(--brand-purple)' : 'transparent',
                color: grain === 'monthly' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              Monthly
            </button>
          </div>

          {/* Group by plant toggle */}
          {!selectedPlant && (
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={groupByPlant}
                onChange={(e) => setGroupByPlant(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              Breakdown by plant
            </label>
          )}
        </div>
      </div>

      {loading && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Loading energy intensity trends…
        </div>
      )}

      {error && (
        <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '6px', color: 'var(--status-danger, #ef4444)', fontSize: '0.82rem', marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {!loading && !error && buckets.length === 0 && (
        <div style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No telemetry records available for the selected trend scope.
        </div>
      )}

      {!loading && !error && buckets.length > 0 && (
        <>
          {/* Trend Chart */}
          <div style={{ width: '100%', height: 260, marginBottom: '1.25rem' }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, #e2e8f0)" />
                <XAxis
                  dataKey="date_label"
                  stroke="var(--chart-axis, #718096)"
                  fontSize={11}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--chart-axis, #718096)"
                  fontSize={11}
                  tickLine={false}
                  label={{
                    value: currentConfig.unit,
                    angle: -90,
                    position: 'insideLeft',
                    style: { fill: 'var(--chart-axis, #718096)', fontSize: 11 },
                  }}
                  domain={['auto', 'auto']}
                />
                <Tooltip content={<CustomIntensityTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: '0.75rem', paddingTop: '0.5rem', color: 'var(--text-secondary)' }}
                />
                <Line
                  type="monotone"
                  dataKey={currentConfig.key}
                  name={`${currentConfig.name} (${currentConfig.unit})`}
                  stroke={currentConfig.color}
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: currentConfig.color }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Bucket Table & Inspection Container with Compact Pagination Footer */}
          <div className="intensity-table-container">
            {/* Scrollable Table Area (Horizontal scroll only wraps table rows) */}
            <div className="intensity-table-scroll">
              <table className="intensity-table">
                <thead>
                  <tr>
                    {renderSortTh('Date', 'period_start', null, 'left')}
                    {renderSortTh('Plant', 'plant_id', null, 'left')}
                    {renderSortTh('Electricity intensity', 'electricity_intensity', 'kWh/good unit', 'right')}
                    {renderSortTh('Cost intensity', 'cost_intensity', '₹/good unit', 'right')}
                    {renderSortTh('Emissions intensity', 'emissions_intensity', 'kg CO₂e/good unit', 'right')}
                    {renderSortTh('Good finished output', 'good_qty', 'units', 'right')}
                    {renderSortTh('Coverage', 'coverage', null, 'center')}
                    <th className="intensity-th intensity-th-right" style={{ cursor: 'default' }}>
                      <div className="intensity-th-content intensity-th-align-right">
                        <span className="intensity-th-label">Details</span>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedBuckets.map((b, idx) => {
                    const bucketKey = `${b.period_start}_${b.plant_id || 'ALL'}_${b.grain || grain}`;
                    const isExpanded = expandedBucketKey === bucketKey;
                    const covBadge = formatCoverageBadge(b.coverage);
                    return (
                      <React.Fragment key={bucketKey}>
                        <tr className={`intensity-table-row ${isExpanded ? 'is-expanded-row' : ''}`}>
                          <td className="intensity-td intensity-td-date">
                            {b.grain === 'monthly' ? b.period_start.substring(0, 7) : formatDate(b.period_start)}
                          </td>
                          <td className="intensity-td intensity-td-plant">{b.plant_id}</td>
                          <td className="intensity-td intensity-td-num">
                            {hasNumber(b.electricity_intensity_kwh_per_good_unit)
                              ? formatNumber(b.electricity_intensity_kwh_per_good_unit, 4)
                              : '—'}
                          </td>
                          <td className="intensity-td intensity-td-num">
                            {hasNumber(b.cost_intensity_inr_per_good_unit)
                              ? formatNumber(b.cost_intensity_inr_per_good_unit, 2)
                              : '—'}
                          </td>
                          <td className="intensity-td intensity-td-num">
                            {hasNumber(b.emissions_intensity_co2e_per_good_unit)
                              ? formatNumber(b.emissions_intensity_co2e_per_good_unit, 4)
                              : '—'}
                          </td>
                          <td className="intensity-td intensity-td-num">
                            {hasNumber(b.matched_good_qty)
                              ? formatNumber(b.matched_good_qty, 0)
                              : '—'}
                          </td>
                          <td className="intensity-td intensity-td-center">
                            <span className={`intensity-cov-badge ${covBadge.statusClass}`}>
                              {covBadge.text}
                            </span>
                          </td>
                          <td className="intensity-td intensity-td-action">
                            <button
                              type="button"
                              className={`intensity-inspect-btn ${isExpanded ? 'is-active' : ''}`}
                              onClick={() => setExpandedBucketKey(isExpanded ? null : bucketKey)}
                              aria-expanded={isExpanded}
                              aria-controls={`intensity-detail-${bucketKey}`}
                              title={isExpanded ? 'Hide row details' : 'Inspect row details'}
                            >
                              <span>{isExpanded ? 'Hide details' : 'Inspect'}</span>
                              <svg
                                className={`intensity-chevron ${isExpanded ? 'is-expanded' : ''}`}
                                width="12"
                                height="12"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2.5"
                                aria-hidden="true"
                              >
                                <polyline points="6 9 12 15 18 9" />
                              </svg>
                            </button>
                          </td>
                        </tr>

                        {/* Expanded Inspection Drawer */}
                        {isExpanded && (
                          <tr
                            id={`intensity-detail-${bucketKey}`}
                            className="intensity-inspect-row"
                          >
                            <td colSpan={8} className="intensity-inspect-cell">
                              <div className="intensity-inspect-grid">
                                {/* Group 1: Energy, cost & emissions */}
                                <div className="intensity-inspect-group">
                                  <h4 className="intensity-inspect-group-title">Energy, cost &amp; emissions</h4>
                                  <dl className="intensity-inspect-dl">
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Eligible energy</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {hasNumber(b.eligible_energy_kwh) ? `${formatNumber(b.eligible_energy_kwh, 2)} kWh` : 'Unavailable'}
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Estimated cost</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {hasNumber(b.eligible_cost_inr) ? formatCurrency(b.eligible_cost_inr) : 'Unavailable'}
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Estimated emissions</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {hasNumber(b.eligible_co2e_kg) ? `${formatNumber(b.eligible_co2e_kg, 2)} kg CO₂e` : 'Unavailable'}
                                        </span>
                                      </dd>
                                    </div>
                                  </dl>
                                </div>

                                {/* Group 2: Production */}
                                <div className="intensity-inspect-group">
                                  <h4 className="intensity-inspect-group-title">Production</h4>
                                  <dl className="intensity-inspect-dl">
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Matched good output</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {hasNumber(b.matched_good_qty) ? `${formatNumber(b.matched_good_qty, 0)} units` : 'Unavailable'}
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Actual output</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {hasNumber(b.matched_actual_qty) ? `${formatNumber(b.matched_actual_qty, 0)} units` : 'Unavailable'}
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Yield</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {b.production_context?.fal_yield_pct != null ? `${b.production_context.fal_yield_pct}%` : 'N/A'}
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Scrap</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {formatNumber(b.production_context?.fal_reject_qty || 0, 0)} units
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">FAL downtime</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {formatNumber(b.production_context?.fal_downtime_line_minutes || 0, 0)} min
                                        </span>
                                      </dd>
                                    </div>
                                  </dl>
                                </div>

                                {/* Group 3: Coverage & assumptions */}
                                <div className="intensity-inspect-group">
                                  <h4 className="intensity-inspect-group-title">Coverage &amp; assumptions</h4>
                                  <dl className="intensity-inspect-dl">
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Observed vs expected hours</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {b.coverage?.complete_matched_hours ?? 0} / {b.coverage?.expected_plant_hours ?? 24} hrs
                                        </span>
                                        <span className="intensity-inspect-source">
                                          {b.coverage?.coverage_status === 'FULL' ? 'Full coverage' : `${b.coverage?.coverage_status || 'Partial coverage'} (${b.coverage?.coverage_percentage ?? 0}%)`}
                                        </span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Tariff</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">₹8.25 / kWh</span>
                                        <span className="intensity-inspect-source">Dataset-derived</span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Emissions factor</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">0.716 kg CO₂e / kWh</span>
                                        <span className="intensity-inspect-source">Estimated · Source unknown</span>
                                      </dd>
                                    </div>
                                    <div className="intensity-inspect-field">
                                      <dt className="intensity-inspect-label">Energy per actual output unit</dt>
                                      <dd className="intensity-inspect-data">
                                        <span className="intensity-inspect-val">
                                          {b.factory_sec_actual_kwh_per_unit != null
                                            ? `${formatNumber(b.factory_sec_actual_kwh_per_unit, 4)} kWh/unit`
                                            : 'Unavailable'}
                                        </span>
                                      </dd>
                                    </div>
                                  </dl>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Compact Footer (outside table's horizontal scroll area) */}
            <div
              className="intensity-table-footer"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.65rem 0.85rem',
                background: 'var(--bg-surface-subtle)',
                borderTop: '1px solid var(--border-color)',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
                flexWrap: 'wrap',
                gap: '0.75rem',
              }}
            >
              {/* Left: Showing Range & Rows per page selector */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  Showing {startRecord}–{endRecord} of {totalRecords}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <label htmlFor="intensity-page-size-select" style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Rows per page:
                  </label>
                  <select
                    id="intensity-page-size-select"
                    value={pageSize}
                    onChange={(e) => setPageSize(Number(e.target.value))}
                    style={{
                      padding: '0.2rem 0.45rem',
                      fontSize: '0.75rem',
                      borderRadius: '4px',
                      border: '1px solid var(--border-color)',
                      background: 'var(--bg-surface)',
                      color: 'var(--text-primary)',
                      cursor: 'pointer',
                    }}
                  >
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                  </select>
                </div>
              </div>

              {/* Right: Page Navigation Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  style={{
                    padding: '0.25rem 0.65rem',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    borderRadius: '4px',
                    border: '1px solid var(--border-color)',
                    background: currentPage <= 1 ? 'transparent' : 'var(--bg-surface)',
                    color: currentPage <= 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                    cursor: currentPage <= 1 ? 'not-allowed' : 'pointer',
                    opacity: currentPage <= 1 ? 0.5 : 1,
                    transition: 'all 0.15s ease',
                  }}
                  aria-label="Previous Page"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  style={{
                    padding: '0.25rem 0.65rem',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    borderRadius: '4px',
                    border: '1px solid var(--border-color)',
                    background: currentPage >= totalPages ? 'transparent' : 'var(--bg-surface)',
                    color: currentPage >= totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                    cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer',
                    opacity: currentPage >= totalPages ? 0.5 : 1,
                    transition: 'all 0.15s ease',
                  }}
                  aria-label="Next Page"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}