import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { productionApi, energyIntensityApi } from '../services';

import ProductionPageHeader from './production/ProductionPageHeader';
import ProductionKpis from './production/ProductionKpis';
import ProductionTrendChart from './production/ProductionTrendChart';
import ProductionQualitySection from './production/ProductionQualitySection';
import ProductionEnergyTradeoffSection from './production/ProductionEnergyTradeoffSection';
import ProductionByLine from './production/ProductionByLine';
import ProductionByProductAndShift from './production/ProductionByProductAndShift';
import ProductionDowntimeSection from './production/ProductionDowntimeSection';

/**
 * Deterministic date-range resolution helper for Production Analytics.
 * Evaluates either a single specific date or full month bounds.
 */
function resolveProductionDateRange(year = 2026, month = 10, date = '') {
  const monthStr = String(month).padStart(2, '0');
  const daysInMonth = new Date(year, month, 0).getDate();
  const lastDayStr = String(daysInMonth).padStart(2, '0');

  if (date && typeof date === 'string' && date.trim() !== '') {
    return {
      startDate: date,
      endDate: date,
      label: date,
      isSingleDate: true,
    };
  }

  return {
    startDate: `${year}-${monthStr}-01`,
    endDate: `${year}-${monthStr}-${lastDayStr}`,
    label: `${year}-${monthStr}`,
    isSingleDate: false,
  };
}

export default function ProductionAnalytics() {
  // Filter States
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [selectedLine, setSelectedLine] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [selectedShift, setSelectedShift] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState(10);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedDate, setSelectedDate] = useState('');

  // Loading & status states
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [unavailableFeeds, setUnavailableFeeds] = useState([]);
  const requestId = useRef(0);

  // Analytical data states
  const [productionSummary, setProductionSummary] = useState(null);
  const [factoryEnergy, setFactoryEnergy] = useState(null);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [byLine, setByLine] = useState([]);
  const [byProduct, setByProduct] = useState([]);
  const [byShift, setByShift] = useState([]);
  const [downtimeByReason, setDowntimeByReason] = useState([]);

  // Resolve active date bounds
  const resolvedDateRange = useMemo(() => {
    return resolveProductionDateRange(selectedYear, selectedMonth, selectedDate);
  }, [selectedYear, selectedMonth, selectedDate]);

  // Telemetry coverage check (PostgreSQL table fact_hourly_production holds Aug 1 – Oct 31, 2026)
  const isDataOutOfCoverage = useMemo(() => {
    if (!resolvedDateRange?.startDate || !resolvedDateRange?.endDate) return false;
    return resolvedDateRange.startDate > '2026-10-31' || resolvedDateRange.endDate < '2026-08-01';
  }, [resolvedDateRange]);

  const loadProductionData = useCallback(async (isRefresh = false) => {
    const currentRequestId = ++requestId.current;
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    // Build query params
    const baseDateParams = {
      ...(resolvedDateRange?.startDate ? { start_date: resolvedDateRange.startDate } : {}),
      ...(resolvedDateRange?.endDate ? { end_date: resolvedDateRange.endDate } : {}),
    };

    const plantParams = {
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
      ...baseDateParams,
    };

    const summaryParams = {
      ...plantParams,
      ...(selectedLine ? { line_id: selectedLine } : {}),
      ...(selectedProduct ? { product_id: selectedProduct } : {}),
      ...(selectedShift ? { shift_id: selectedShift } : {}),
    };

    const lineFilteredParams = {
      ...plantParams,
      ...(selectedLine ? { line_id: selectedLine } : {}),
    };

    try {
      const results = await Promise.allSettled([
        productionApi.getSummary(summaryParams),
        productionApi.getDailyTrend(plantParams),
        productionApi.getByLine(plantParams),
        productionApi.getByProduct(lineFilteredParams),
        productionApi.getByShift(plantParams),
        productionApi.getDowntimeByReason(lineFilteredParams),
        energyIntensityApi.getFactoryEnergy(summaryParams),
      ]);
      if (currentRequestId !== requestId.current) return;

      const [summaryRes, trendRes, lineRes, productRes, shiftRes, downtimeRes, energyRes] = results;
      const feedNames = [
        'Production summary',
        'Daily production trend',
        'Production by line',
        'Production by product',
        'Production by shift',
        'Downtime by reason',
        'Factory energy intensity',
      ];
      setUnavailableFeeds(feedNames.filter((_, index) => results[index].status === 'rejected'));

      setProductionSummary(summaryRes.status === 'fulfilled' ? summaryRes.value : null);
      setDailyTrend(trendRes.status === 'fulfilled' ? trendRes.value || [] : []);
      setByLine(lineRes.status === 'fulfilled' ? lineRes.value || [] : []);
      setByProduct(productRes.status === 'fulfilled' ? productRes.value || [] : []);
      setByShift(shiftRes.status === 'fulfilled' ? shiftRes.value || [] : []);
      setDowntimeByReason(downtimeRes.status === 'fulfilled' ? downtimeRes.value || [] : []);
      setFactoryEnergy(energyRes.status === 'fulfilled' ? energyRes.value : null);

      if (summaryRes.status === 'rejected') {
        throw new Error(summaryRes.reason?.message || 'Failed to retrieve production summary.');
      }

      setLastRefreshed(new Date());
    } catch (err) {
      if (currentRequestId !== requestId.current) return;
      console.error('Production Analytics data load error:', err);
      setError(err.message || 'Unable to load production analytics. Verify backend connection.');
    } finally {
      if (currentRequestId === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [selectedPlant, selectedLine, selectedProduct, selectedShift, resolvedDateRange]);

  useEffect(() => {
    loadProductionData(false);
  }, [loadProductionData]);

  const handleRefresh = () => {
    loadProductionData(true);
  };

  const handleResetFilters = () => {
    setSelectedPlant(null);
    setSelectedLine(null);
    setSelectedProduct(null);
    setSelectedShift(null);
    setSelectedMonth(10);
    setSelectedYear(2026);
    setSelectedDate('');
  };

  const handleClearIncompatibleFilters = () => {
    setSelectedLine(null);
    setSelectedProduct(null);
    setSelectedShift(null);
  };

  return (
    <div className="dashboard-container">
      {/* 1. Compact Modern Filter Toolbar */}
      <ProductionPageHeader
        selectedPlant={selectedPlant}
        onSelectPlant={setSelectedPlant}
        selectedLine={selectedLine}
        onSelectLine={setSelectedLine}
        selectedProduct={selectedProduct}
        onSelectProduct={setSelectedProduct}
        selectedShift={selectedShift}
        onSelectShift={setSelectedShift}
        selectedMonth={selectedMonth}
        onSelectedMonthChange={setSelectedMonth}
        selectedYear={selectedYear}
        onSelectedYearChange={setSelectedYear}
        selectedDate={selectedDate}
        onSelectDate={setSelectedDate}
        onResetFilters={handleResetFilters}
      />

      {loading ? (
        <div className="dashboard-loading-state" role="status" aria-live="polite" aria-busy="true">
          <div className="loading-spinner"></div>
          <div className="loading-title">Retrieving Production Telemetry &amp; Quality Records...</div>
          <div className="loading-subtitle">Loading production summary, daily trend, line, product, shift, and downtime data</div>
        </div>
      ) : error ? (
        <div className="dashboard-error-state" role="alert">
          <div className="error-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div className="error-title">Unable to Load Production Analytics</div>
          <div className="error-desc">{error}</div>
          <button type="button" className="error-retry-btn" onClick={() => loadProductionData(false)}>
            Retry Connection
          </button>
        </div>
      ) : (
        <div className="dashboard-content-flow">
          {/* Out of Coverage Warning Banner */}
          {isDataOutOfCoverage && (
            <div className="coverage-notice-banner" role="status" style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem',
              padding: '0.85rem 1.15rem',
              backgroundColor: 'rgba(245, 158, 11, 0.12)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.25rem',
              color: 'var(--text-primary)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2.2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>
                  Selected filter period has no records in the PostgreSQL production dataset (coverage: Aug 1 – Oct 31, 2026). Displaying authentic zero/empty state.
                </span>
              </div>
              <button
                type="button"
                className="filter-reset-btn"
                onClick={handleResetFilters}
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem', whiteSpace: 'nowrap' }}
              >
                Return to Full Dataset
              </button>
            </div>
          )}

          {/* Feed Offline Notice */}
          {unavailableFeeds.length > 0 && (
            <div className="data-integrity-notice-box" role="status">
              <div className="integrity-content">
                <div className="integrity-title">Some production data feeds are offline</div>
                <p className="integrity-text">
                  Requests not returned: {unavailableFeeds.join(', ')}. These sections are shown as unavailable rather than zero.
                </p>
              </div>
            </div>
          )}

          {/* Section 1: Exactly 4 Primary KPI Cards + Secondary Metrics Strip */}
          <ProductionKpis
            summary={productionSummary}
            summaryAvailable={!unavailableFeeds.includes('Production summary')}
            dailyTrend={dailyTrend}
          />

          {/* Section 2: Main Production Trend - Daily Actual, Good & Rejected Output */}
          <ProductionTrendChart
            dailyTrend={dailyTrend}
            dataAvailable={!unavailableFeeds.includes('Daily production trend')}
            selectedPlant={selectedPlant}
            selectedLine={selectedLine}
          />

          {/* Section 3: Production Quality & Mathematical Balance (Actual = Good + Rejected) */}
          <ProductionQualitySection
            summary={productionSummary}
          />

          {/* Section 3B: Energy Intensity & Production Quality Trade-offs */}
          <ProductionEnergyTradeoffSection
            factoryEnergy={factoryEnergy}
            loading={loading}
            selectedLine={selectedLine}
            selectedProduct={selectedProduct}
            selectedShift={selectedShift}
            onClearFilters={handleClearIncompatibleFilters}
          />

          {/* Section 4: Production Line Performance & Comparison */}
          <ProductionByLine
            byLine={byLine}
            dataAvailable={!unavailableFeeds.includes('Production by line')}
            selectedLine={selectedLine}
            onSelectLine={setSelectedLine}
          />

          {/* Section 5: Product SKU & Shift Breakdown */}
          <ProductionByProductAndShift
            byProduct={byProduct}
            byShift={byShift}
            productDataAvailable={!unavailableFeeds.includes('Production by product')}
            shiftDataAvailable={!unavailableFeeds.includes('Production by shift')}
            selectedProduct={selectedProduct}
            onSelectProduct={setSelectedProduct}
            selectedShift={selectedShift}
            onSelectShift={setSelectedShift}
          />

          {/* Section 6: Downtime & Stoppage Analysis */}
          <ProductionDowntimeSection
            downtimeData={downtimeByReason}
            totalDowntimeMin={productionSummary?.downtime_min ?? null}
            dataAvailable={!unavailableFeeds.includes('Downtime by reason')}
          />
        </div>
      )}
    </div>
  );
}
