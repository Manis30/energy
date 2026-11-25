import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  energyApi,
  energyIntensityApi,
  productionApi,
  findingsApi,
  recommendationsApi,
} from '../../services';

import DashboardHeader from './DashboardHeader';
import KpiOverview from './KpiOverview';
import OperationalHealthSummary from './OperationalHealthSummary';
import ExecutiveChartsRow from './ExecutiveChartsRow';
import OperationalAttentionSection from './OperationalAttentionSection';

/**
 * Deterministic helper to format single date option e.g. "2026-10-15" -> "15 Oct 2026"
 */
export function formatOptionDate(dateStr) {
  if (!dateStr || typeof dateStr !== 'string') return '';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const [y, m, d] = parts;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthName = months[parseInt(m, 10) - 1] || m;
  return `${d} ${monthName} ${y}`;
}

/**
 * Deterministic helper to format month key e.g. "2026-10" -> "October 2026"
 */
export function formatMonthLabel(monthKey) {
  if (!monthKey || typeof monthKey !== 'string') return '';
  const parts = monthKey.split('-');
  if (parts.length !== 2) return monthKey;
  const [y, m] = parts;
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  const monthName = months[parseInt(m, 10) - 1] || m;
  return `${monthName} ${y}`;
}

/**
 * Resolves start_date, end_date, and viewMode from the Month & Date selectors.
 */
export function resolveDateRange(selectedMonth = '2026-10', selectedDate = 'ALL') {
  const [yearStr, monthStr] = selectedMonth.split('-');
  const year = parseInt(yearStr, 10);
  const month = parseInt(monthStr, 10);
  const monthName = formatMonthLabel(selectedMonth);

  // When "ALL" is selected, dashboard loads aggregated metrics for the entire month
  if (!selectedDate || selectedDate === 'ALL') {
    const lastDayNum = new Date(year, month, 0).getDate();
    const lastDayStr = String(lastDayNum).padStart(2, '0');
    return {
      startDate: `${selectedMonth}-01`,
      endDate: `${selectedMonth}-${lastDayStr}`,
      label: monthName,
      isDaily: false,
      viewMode: 'MONTHLY',
      viewLabel: `Monthly View • ${monthName} (Aggregated)`,
    };
  }

  // When a specific date is selected, dashboard loads that exact day's metrics
  return {
    startDate: selectedDate,
    endDate: selectedDate,
    label: formatOptionDate(selectedDate),
    isDaily: true,
    viewMode: 'DAILY',
    viewLabel: `Daily View • ${formatOptionDate(selectedDate)} (Single Day)`,
  };
}

// Fallback months configuration if telemetry discovery is initializing
const INITIAL_MONTHS = [
  { value: '2026-10', label: 'October 2026', year: 2026, month: 10, count: 31 },
  { value: '2026-09', label: 'September 2026', year: 2026, month: 9, count: 30 },
  { value: '2026-08', label: 'August 2026', year: 2026, month: 8, count: 31 },
  { value: '2026-11', label: 'November 2026 (No Data Test)', year: 2026, month: 11, count: 0 },
];

const INITIAL_PLANTS = [
  { value: 'IN-TN-01', label: 'Plant IN-TN-01 (Tamil Nadu)', shortLabel: 'Plant IN-TN-01' },
  { value: 'IN-KA-01', label: 'Plant IN-KA-01 (Karnataka)', shortLabel: 'Plant IN-KA-01' },
];

const STANDARD_SHIFTS = [
  { value: 'A', label: 'Shift A (Morning • 06:00 – 14:00)' },
  { value: 'B', label: 'Shift B (Evening • 14:00 – 22:00)' },
  { value: 'C', label: 'Shift C (Night • 22:00 – 06:00)' },
];

export default function Dashboard() {
  // Filter States: Exactly four selectors (Month, Date, Plant, Shift)
  const [selectedMonth, setSelectedMonth] = useState('2026-10'); // Default to latest verified month
  const [selectedDate, setSelectedDate] = useState('ALL'); // Default to aggregated month view
  const [selectedPlant, setSelectedPlant] = useState('ALL'); // Default to All plants
  const [selectedShift, setSelectedShift] = useState('ALL'); // Default to All shifts

  // Available plants and shifts
  const [availablePlants, setAvailablePlants] = useState(INITIAL_PLANTS);

  // Dynamic date availability state derived from backend telemetry
  const [availableMonths, setAvailableMonths] = useState(INITIAL_MONTHS);
  const [datesByMonthMap, setDatesByMonthMap] = useState({});

  // Loading, refresh and error states
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [backendConnected, setBackendConnected] = useState(true);
  const [loadedPeriodKey, setLoadedPeriodKey] = useState(null);

  // Analytical data states
  const [energySummary, setEnergySummary] = useState(null);
  const [energyDailyTrend, setEnergyDailyTrend] = useState([]);
  const [productionSummary, setProductionSummary] = useState(null);
  const [productionDailyTrend, setProductionDailyTrend] = useState([]);
  const [factoryEnergy, setFactoryEnergy] = useState(null);

  // Operational Health & Exception States
  const [operationalKpis, setOperationalKpis] = useState({
    activeFindings: 0,
    criticalHigh: 0,
    openRecommendations: 0,
  });
  const [attentionFindings, setAttentionFindings] = useState([]);
  const [unavailableFeeds, setUnavailableFeeds] = useState([]);

  // Race condition protection ref: ignore responses from older requests
  const reqIdRef = useRef(0);

  // Dynamically populate available shifts for selected plant & period
  const availableShifts = useMemo(() => {
    return STANDARD_SHIFTS;
  }, [selectedPlant, selectedMonth]);

  // Handle Plant selection with validation
  const handleSelectPlant = (newPlant) => {
    setSelectedPlant(newPlant);
    // If a plant change makes the selected shift invalid, reset to "ALL"
    const validShiftValues = availableShifts.map((s) => s.value);
    if (selectedShift !== 'ALL' && !validShiftValues.includes(selectedShift)) {
      setSelectedShift('ALL');
    }
    setLoading(true);
  };

  // Handle Shift selection
  const handleSelectShift = (newShift) => {
    setSelectedShift(newShift);
    setLoading(true);
  };

  // 1. Dynamic Discovery of available months and dates from backend telemetry
  useEffect(() => {
    let isMounted = true;
    async function discoverAvailableDates() {
      try {
        const trend = await energyApi.getDailyTrend({});
        if (!isMounted) return;

        if (Array.isArray(trend) && trend.length > 0) {
          const map = {};
          const monthKeysSet = new Set();

          trend.forEach((item) => {
            if (!item.date) return;
            const monthKey = item.date.slice(0, 7); // 'YYYY-MM'
            monthKeysSet.add(monthKey);
            if (!map[monthKey]) {
              map[monthKey] = [];
            }
            map[monthKey].push({
              value: item.date,
              label: formatOptionDate(item.date),
              shortLabel: formatOptionDate(item.date),
            });
          });

          // Always add November 2026 (simulated current calendar month) for empty state test
          monthKeysSet.add('2026-11');
          if (!map['2026-11']) {
            map['2026-11'] = [];
          }

          // Sort months descending (latest month first)
          const sortedMonthKeys = Array.from(monthKeysSet).sort().reverse();
          const discoveredMonths = sortedMonthKeys.map((mk) => {
            const count = map[mk]?.length || 0;
            return {
              value: mk,
              label: count > 0 ? formatMonthLabel(mk) : `${formatMonthLabel(mk)} (No Telemetry)`,
              count,
            };
          });

          setAvailableMonths(discoveredMonths);
          setDatesByMonthMap(map);
        }
      } catch (err) {
        console.warn('Dynamic date discovery notice: using default verified date range.', err);
      }
    }

    discoverAvailableDates();
    return () => {
      isMounted = false;
    };
  }, []);

  // Compute available dates for currently selected month
  const currentMonthAvailableDates = useMemo(() => {
    if (datesByMonthMap[selectedMonth]) {
      return datesByMonthMap[selectedMonth];
    }
    // Fallback date generation for month if map not yet loaded
    const [yStr, mStr] = selectedMonth.split('-');
    const y = parseInt(yStr, 10);
    const m = parseInt(mStr, 10);
    const lastDay = new Date(y, m, 0).getDate();
    const dates = [];
    for (let d = 1; d <= lastDay; d++) {
      const dStr = String(d).padStart(2, '0');
      const val = `${selectedMonth}-${dStr}`;
      dates.push({
        value: val,
        label: `${val} (${formatOptionDate(val)})`,
      });
    }
    return dates;
  }, [datesByMonthMap, selectedMonth]);

  // Handle Month selection
  const handleSelectMonth = (newMonth) => {
    setSelectedMonth(newMonth);
    // If the currently selected day does not belong to the newly selected month, reset to ALL
    if (selectedDate !== 'ALL' && !selectedDate.startsWith(newMonth)) {
      setSelectedDate('ALL');
    }
    setLoading(true);
  };

  // Handle Date selection
  const handleSelectDate = (newDate) => {
    setSelectedDate(newDate);
    setLoading(true);
  };

  // Compute resolved date range from active Month & Date selectors
  const resolvedDateRange = useMemo(() => {
    return resolveDateRange(selectedMonth, selectedDate);
  }, [selectedMonth, selectedDate]);

  const currentPeriodKey = resolvedDateRange
    ? `${resolvedDateRange.startDate}:${resolvedDateRange.endDate}:${selectedPlant}:${selectedShift}`
    : '';

  // Determine busy, refresh, and placeholder states
  const isBusy = loading || refreshing || (loadedPeriodKey !== null && loadedPeriodKey !== currentPeriodKey);
  const isRefreshingSamePeriod = refreshing && loadedPeriodKey === currentPeriodKey;
  const showPlaceholders = isBusy && !isRefreshingSamePeriod;

  // Selected period formatting: "October 2026" for full month, or actual date(s)
  const selectedPeriodText = useMemo(() => {
    if (!resolvedDateRange) return '';
    const dateText = (!resolvedDateRange.isDaily || selectedDate === 'ALL')
      ? (formatMonthLabel(selectedMonth) || resolvedDateRange.label)
      : (resolvedDateRange.startDate === resolvedDateRange.endDate
          ? (formatOptionDate(resolvedDateRange.startDate) || resolvedDateRange.startDate)
          : `${formatOptionDate(resolvedDateRange.startDate)} – ${formatOptionDate(resolvedDateRange.endDate)}`);

    const plantLabel = selectedPlant !== 'ALL'
      ? (availablePlants.find((p) => p.value === selectedPlant)?.shortLabel || selectedPlant)
      : null;
    const shiftLabel = selectedShift !== 'ALL'
      ? (availableShifts.find((s) => s.value === selectedShift)?.label?.split(' ')[0] || `Shift ${selectedShift}`)
      : null;

    const extras = [plantLabel, shiftLabel].filter(Boolean).join(' • ');
    return extras ? `${dateText} (${extras})` : dateText;
  }, [resolvedDateRange, selectedMonth, selectedDate, selectedPlant, selectedShift, availablePlants, availableShifts]);

  // Load Dashboard analytical and operational data
  const loadDashboardData = useCallback(async (isRefresh = false) => {
    const currentReqId = ++reqIdRef.current;
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    // Filter params sent to backend
    const filterParams = {
      start_date: resolvedDateRange.startDate,
      end_date: resolvedDateRange.endDate,
      ...(selectedPlant !== 'ALL' ? { plant_id: selectedPlant } : {}),
      ...(selectedShift !== 'ALL' ? { shift_id: selectedShift } : {}),
    };

    const plantScopeParams = selectedPlant !== 'ALL' ? { plant_id: selectedPlant } : {};

    try {
      const results = await Promise.allSettled([
        energyApi.getSummary(filterParams),
        energyApi.getDailyTrend(filterParams),
        productionApi.getSummary(filterParams),
        productionApi.getDailyTrend(filterParams),
        energyIntensityApi.getFactoryEnergy(filterParams),
        findingsApi.listFindings({ status: 'ACTIVE', limit: 1, ...plantScopeParams }),
        findingsApi.listFindings({ status: 'ACTIVE', severity: 'CRITICAL', limit: 1, ...plantScopeParams }),
        findingsApi.listFindings({ status: 'ACTIVE', severity: 'HIGH', limit: 1, ...plantScopeParams }),
        recommendationsApi.listRecommendations({ status: 'OPEN', limit: 1, ...plantScopeParams }),
        recommendationsApi.listRecommendations({ status: 'IN_PROGRESS', limit: 1, ...plantScopeParams }),
        findingsApi.listFindings({ status: 'ACTIVE', limit: 10, ...plantScopeParams }),
      ]);

      // If a newer request was dispatched while this request was awaiting, ignore stale result
      if (currentReqId !== reqIdRef.current) {
        return;
      }

      const [
        eSummaryRes,
        eTrendRes,
        pSummaryRes,
        pTrendRes,
        factoryEnergyRes,
        activeFindingsRes,
        critFindingsRes,
        highFindingsRes,
        openRecRes,
        inProgRecRes,
        attentionFindingsRes,
      ] = results;

      const feedNames = [
        'Energy summary',
        'Energy trend',
        'Production summary',
        'Production trend',
        'Factory energy intensity',
        'Active findings',
        'Critical findings',
        'High-priority findings',
        'Open recommendations',
        'In-progress recommendations',
        'Operational attention findings',
      ];
      setUnavailableFeeds(feedNames.filter((_, index) => results[index].status === 'rejected'));

      setEnergySummary(eSummaryRes.status === 'fulfilled' ? eSummaryRes.value : null);
      setEnergyDailyTrend(eTrendRes.status === 'fulfilled' ? eTrendRes.value || [] : []);
      setProductionSummary(pSummaryRes.status === 'fulfilled' ? pSummaryRes.value : null);
      setProductionDailyTrend(pTrendRes.status === 'fulfilled' ? pTrendRes.value || [] : []);
      setFactoryEnergy(factoryEnergyRes.status === 'fulfilled' ? factoryEnergyRes.value : null);

      const activeCount = activeFindingsRes.status === 'fulfilled' ? activeFindingsRes.value?.total || 0 : 0;
      const critCount = critFindingsRes.status === 'fulfilled' ? critFindingsRes.value?.total || 0 : 0;
      const highCount = highFindingsRes.status === 'fulfilled' ? highFindingsRes.value?.total || 0 : 0;
      const openRecCount = openRecRes.status === 'fulfilled' ? openRecRes.value?.total || 0 : 0;
      const inProgRecCount = inProgRecRes.status === 'fulfilled' ? inProgRecRes.value?.total || 0 : 0;

      setOperationalKpis({
        activeFindings: activeCount,
        criticalHigh: critCount + highCount,
        openRecommendations: openRecCount + inProgRecCount,
      });

      setAttentionFindings(attentionFindingsRes.status === 'fulfilled' ? attentionFindingsRes.value?.items || [] : []);

      // Check if primary endpoints failed completely
      const primaryFailed = eSummaryRes.status === 'rejected' && pSummaryRes.status === 'rejected';
      if (primaryFailed) {
        setBackendConnected(false);
        throw new Error(eSummaryRes.reason?.message || pSummaryRes.reason?.message || 'Failed to load primary dashboard data.');
      } else {
        setBackendConnected(true);
        setLoadedPeriodKey(`${resolvedDateRange.startDate}:${resolvedDateRange.endDate}:${selectedPlant}:${selectedShift}`);
      }
    } catch (err) {
      console.error('Dashboard data load error:', err);
      setError(err.message || 'Unable to load dashboard analytics. Verify backend connection.');
    } finally {
      if (currentReqId === reqIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [resolvedDateRange, selectedPlant, selectedShift]);

  useEffect(() => {
    loadDashboardData(false);
  }, [loadDashboardData]);

  const handleRefresh = () => {
    loadDashboardData(true);
  };

  // Check if current date range yields 0 records or no data available
  const isDataOutOfCoverage = Boolean(
    energySummary &&
    (energySummary.total_readings === 0 || energySummary.data_available === false)
  );

  const isDataLoading = loading || refreshing;

  return (
    <div className="dashboard-container dashboard-view">
      {/* 1. Integrated Header & Modern Filter Toolbar (Month → Date → Plant → Shift → Refresh) */}
      <DashboardHeader
        selectedMonth={selectedMonth}
        onSelectMonth={handleSelectMonth}
        selectedDate={selectedDate}
        onSelectDate={handleSelectDate}
        selectedPlant={selectedPlant}
        onSelectPlant={handleSelectPlant}
        selectedShift={selectedShift}
        onSelectShift={handleSelectShift}
        availableMonths={availableMonths}
        availableDates={currentMonthAvailableDates}
        availablePlants={availablePlants}
        availableShifts={availableShifts}
        resolvedDateRange={resolvedDateRange}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        isDataOutOfCoverage={isDataOutOfCoverage}
        backendConnected={backendConnected}
      />

      {isBusy && (
        <div
          className="dashboard-loading-status-row"
          role="status"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="dashboard-loading-main">
            <span className="dashboard-loading-spinner" aria-hidden="true" />
            <span className="dashboard-loading-message">
              {isRefreshingSamePeriod ? 'Updating dashboard' : 'Loading energy and production data'}
            </span>
          </div>
          {selectedPeriodText && (
            <span className="dashboard-loading-period">
              {selectedPeriodText}
            </span>
          )}
        </div>
      )}

      {error && !isBusy ? (
        <div className="dashboard-error-state" role="alert">
          <div className="error-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div className="error-title">Unable to Load Dashboard</div>
          <div className="error-desc">{error}</div>
          <button type="button" className="error-retry-btn" onClick={() => loadDashboardData(false)}>
            Retry Connection
          </button>
        </div>
      ) : (
        <div className="dashboard-content-flow">
          {unavailableFeeds.length > 0 && (
            <div className="data-integrity-notice-box" role="status">
              <div className="integrity-content">
                <div className="integrity-title">Some Dashboard telemetry feeds are offline</div>
                <p className="integrity-text">
                  Requests not returned: {unavailableFeeds.join(', ')}. These sections are unavailable, not zero; returned values may cover only part of the Dashboard.
                </p>
              </div>
            </div>
          )}

          {/* 1. Four Primary KPI Cards */}
          <KpiOverview
            energySummary={showPlaceholders ? null : energySummary}
            productionSummary={showPlaceholders ? null : productionSummary}
            factoryEnergy={showPlaceholders ? null : factoryEnergy}
            energyTrend={showPlaceholders ? [] : energyDailyTrend}
            productionTrend={showPlaceholders ? [] : productionDailyTrend}
            resolvedDateRange={resolvedDateRange}
            selectedPlant={selectedPlant}
            selectedShift={selectedShift}
            energyAvailable={!unavailableFeeds.includes('Energy summary')}
            productionAvailable={!unavailableFeeds.includes('Production summary')}
            factoryEnergyAvailable={!unavailableFeeds.includes('Factory energy intensity')}
            loading={showPlaceholders}
          />

          {/* 2. Compact Operational Health Strip */}
          <OperationalHealthSummary
            activeFindingsCount={showPlaceholders ? 0 : operationalKpis.activeFindings}
            criticalHighCount={showPlaceholders ? 0 : operationalKpis.criticalHigh}
            openRecommendationsCount={showPlaceholders ? 0 : operationalKpis.openRecommendations}
            productionSummary={showPlaceholders ? null : productionSummary}
            loading={showPlaceholders}
          />

          {/* 3 & 4. Daily Energy Consumption & Daily Production Output */}
          <ExecutiveChartsRow
            energyTrend={showPlaceholders ? [] : energyDailyTrend}
            productionTrend={showPlaceholders ? [] : productionDailyTrend}
            energyAvailable={!unavailableFeeds.includes('Energy trend')}
            productionAvailable={!unavailableFeeds.includes('Production trend')}
            loading={showPlaceholders}
            resolvedDateRange={resolvedDateRange}
            selectedPlant={selectedPlant}
            selectedShift={selectedShift}
          />

          {/* 5. Operational Attention Required (Compact Alert List) */}
          <OperationalAttentionSection
            findings={showPlaceholders ? [] : attentionFindings}
            totalActiveCount={showPlaceholders ? 0 : operationalKpis.activeFindings}
            loading={showPlaceholders}
            selectedPlant={selectedPlant}
          />

          {/* 6. Methodology & Scope Qualifications Footer */}
          <footer className="dashboard-methodology-footer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <span>
              <strong>Estimates &amp; Scope Qualifications:</strong> Energy costs are dataset-calculated based on configured industrial tariff rates; carbon emissions reflect an estimated 0.82 kg CO₂/kWh grid intensity factor. Consumption metrics are not production-normalized. Dedicated line metrics, process SEC breakdowns, and full audit provenance are accessible via Energy Analytics, Production Analytics, and Investigation &amp; Actions Centre.
            </span>
          </footer>
        </div>
      )}
    </div>
  );
}
