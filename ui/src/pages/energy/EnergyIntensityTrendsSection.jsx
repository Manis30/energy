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

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

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

  const renderSortTh = (label, field, align = 'left') => {
    const isSorted = sortField === field;
    return (
      <th
        style={{
          padding: '0.5rem 0.75rem',
          fontWeight: 600,
          textAlign: align,
          cursor: 'pointer',
          userSelect: 'none',
        }}
        onClick={() => handleSort(field)}
        title={`Sort by ${label}`}
        role="columnheader"
        aria-sort={isSorted ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
          <span>{label}</span>
          <span style={{ fontSize: '0.68rem', color: isSorted ? 'var(--brand-purple)' : 'var(--text-muted)' }}>
            {isSorted ? (sortDirection === 'asc' ? '▲' : '▼') : '↕'}
          </span>
        </span>
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
          <div
            style={{
              border: '1px solid var(--border-color)',
              borderRadius: '6px',
              background: 'var(--bg-surface)',
              overflow: 'hidden',
            }}
          >
            {/* Scrollable Table Area (Horizontal scroll only wraps table rows) */}
            <div style={{ overflowX: 'auto', width: '100%' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem', textAlign: 'left', color: 'var(--text-secondary)' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    {renderSortTh('Period', 'period_start')}
                    {renderSortTh('Plant', 'plant_id')}
                    {renderSortTh('Electricity Intensity', 'electricity_intensity')}
                    {renderSortTh('Cost Intensity', 'cost_intensity')}
                    {renderSortTh('Emissions Intensity', 'emissions_intensity')}
                    {renderSortTh('Good FAL Output', 'good_qty')}
                    {renderSortTh('Coverage', 'coverage')}
                    <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontWeight: 600 }}>Inspection</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedBuckets.map((b, idx) => {
                    const bucketKey = `${b.period_start}_${b.plant_id || 'ALL'}_${b.grain || grain}`;
                    const isExpanded = expandedBucketKey === bucketKey;
                    const hasCoverage = b.coverage?.coverage_status === 'FULL';
                    return (
                      <React.Fragment key={bucketKey}>
                        <tr
                          style={{
                            borderBottom: '1px solid var(--border-color)',
                            background: isExpanded ? 'var(--bg-surface-subtle)' : (idx % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-surface-subtle)'),
                          }}
                        >
                          <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            {b.grain === 'monthly' ? b.period_start.substring(0, 7) : formatDate(b.period_start)}
                          </td>
                          <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{b.plant_id}</td>
                          <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: 'var(--brand-purple)' }}>
                            {hasNumber(b.electricity_intensity_kwh_per_good_unit)
                              ? `${formatNumber(b.electricity_intensity_kwh_per_good_unit, 4)} kWh/good`
                              : 'Unavailable'}
                          </td>
                          <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: 'var(--brand-blue)' }}>
                            {hasNumber(b.cost_intensity_inr_per_good_unit)
                              ? `${formatCurrency(b.cost_intensity_inr_per_good_unit)}/good`
                              : 'Unavailable'}
                          </td>
                          <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: 'var(--brand-cyan)' }}>
                            {hasNumber(b.emissions_intensity_co2e_per_good_unit)
                              ? `${formatNumber(b.emissions_intensity_co2e_per_good_unit, 4)} kg CO₂e`
                              : 'Unavailable'}
                          </td>
                          <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)' }}>
                            {hasNumber(b.matched_good_qty) ? `${formatNumber(b.matched_good_qty, 0)} units` : 'Unavailable'}
                          </td>
                          <td style={{ padding: '0.5rem 0.75rem' }}>
                            <span
                              style={{
                                display: 'inline-block',
                                padding: '0.1rem 0.4rem',
                                borderRadius: '4px',
                                fontSize: '0.7rem',
                                fontWeight: 600,
                                backgroundColor: hasCoverage ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 138, 58, 0.15)',
                                color: hasCoverage ? 'var(--status-success, #10b981)' : 'var(--status-warning, #f58a3a)',
                              }}
                            >
                              {b.coverage?.coverage_status} ({b.coverage?.coverage_percentage}%)
                            </span>
                          </td>
                          <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>
                            <button
                              type="button"
                              onClick={() => setExpandedBucketKey(isExpanded ? null : bucketKey)}
                              style={{
                                padding: '0.2rem 0.5rem',
                                fontSize: '0.72rem',
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border-color)',
                                borderRadius: '4px',
                                color: 'var(--text-secondary)',
                                cursor: 'pointer',
                              }}
                            >
                              {isExpanded ? 'Hide' : 'Inspect'}
                            </button>
                          </td>
                        </tr>

                        {/* Expanded Inspection Drawer */}
                        {isExpanded && (
                          <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-color)' }}>
                            <td colSpan={8} style={{ padding: '0.85rem 1rem' }}>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', fontSize: '0.76rem' }}>
                                <div>
                                  <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Numerator Inspection</div>
                                  <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                    Eligible Energy: <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(b.eligible_energy_kwh, 2)} kWh</strong><br />
                                    Estimated Cost: <strong style={{ color: 'var(--text-primary)' }}>{formatCurrency(b.eligible_cost_inr)}</strong><br />
                                    Estimated CO₂e: <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(b.eligible_co2e_kg, 2)} kg</strong>
                                  </div>
                                </div>
                                <div>
                                  <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Denominator &amp; Production</div>
                                  <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                    Matched Good Output: <strong style={{ color: 'var(--status-success, #10b981)' }}>{formatNumber(b.matched_good_qty, 0)} units</strong><br />
                                    Total Actual Output: <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(b.matched_actual_qty, 0)} units</strong><br />
                                    Yield Rate: <strong style={{ color: 'var(--text-primary)' }}>{b.production_context?.fal_yield_pct != null ? `${b.production_context.fal_yield_pct}%` : 'N/A'}</strong> (Scrap: {b.production_context?.fal_reject_qty || 0})<br />
                                    FAL Downtime: <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(b.production_context?.fal_downtime_line_minutes || 0, 0)} min</strong>
                                  </div>
                                </div>
                                <div>
                                  <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Coverage &amp; Assumptions</div>
                                  <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                    Plant-Hours: <strong style={{ color: 'var(--text-primary)' }}>{b.coverage?.complete_matched_hours} / {b.coverage?.expected_plant_hours} hrs</strong> ({b.coverage?.coverage_status})<br />
                                    Tariff Lineage: <span style={{ color: 'var(--status-warning, #f58a3a)' }}>₹8.25/kWh (dataset-derived, UNKNOWN)</span><br />
                                    Emissions Factor: <span style={{ color: 'var(--status-warning, #f58a3a)' }}>0.716 kg/kWh (estimated, UNKNOWN)</span><br />
                                    Actual-Output SEC: <strong style={{ color: 'var(--text-primary)' }}>{b.factory_sec_actual_kwh_per_unit != null ? `${formatNumber(b.factory_sec_actual_kwh_per_unit, 4)} kWh/unit` : 'Unavailable'}</strong>
                                  </div>
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