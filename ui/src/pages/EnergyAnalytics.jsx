import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { energyApi, productionApi } from '../services';

import EnergyPageHeader from './energy/EnergyPageHeader';
import EnergyKpis from './energy/EnergyKpis';
import EnergyTrendChart from './energy/EnergyTrendChart';
import EnergyIntensityTrendsSection from './energy/EnergyIntensityTrendsSection';
import OperatingContextSection from './energy/OperatingContextSection';
import EnergyMeterBreakdown from './energy/EnergyMeterBreakdown';
import EnergyAreaDistribution from './energy/EnergyAreaDistribution';
import PowerFactorSection from './energy/PowerFactorSection';

// Secondary / Deep-dive engineering modules (placed in collapsible section)
import EnergyConsumptionHeatmap from './energy/EnergyConsumptionHeatmap';
import EnergyProductionRelationship from './energy/EnergyProductionRelationship';
import EnergyPerformanceExceptions from './energy/EnergyPerformanceExceptions';
import EnergyPerformanceComparison from './energy/EnergyPerformanceComparison';
import TariffWhatIfAnalysis from './energy/TariffWhatIfAnalysis';

/**
 * Deterministic date-range resolution helper for Energy Analytics.
 * Supports specific date selection or full-month aggregated views.
 */
function resolveEnergyDateRange(year, month, specificDate) {
  const monthStr = String(month).padStart(2, '0');
  if (specificDate) {
    return {
      startDate: specificDate,
      endDate: specificDate,
      label: specificDate,
      isSingleDate: true,
    };
  }
  const lastDay = new Date(year, month, 0).getDate();
  const lastDayStr = String(lastDay).padStart(2, '0');
  return {
    startDate: `${year}-${monthStr}-01`,
    endDate: `${year}-${monthStr}-${lastDayStr}`,
    label: `${year}-${monthStr}`,
    isSingleDate: false,
  };
}

export default function EnergyAnalytics() {
  const [searchParams] = useSearchParams();
  const urlPlant = searchParams.get('plant_id');
  const urlLine = searchParams.get('line_id');
  const urlDate = searchParams.get('date');
  const urlEpisodeId = searchParams.get('episode_id');

  // Filter States: Plant, Month, Year, Date (single horizontal toolbar)
  const [selectedPlant, setSelectedPlant] = useState(urlPlant || null);
  const [selectedMonth, setSelectedMonth] = useState(() => {
    if (urlDate && urlDate.length >= 7) {
      return parseInt(urlDate.split('-')[1], 10);
    }
    return 10;
  });
  const [selectedYear, setSelectedYear] = useState(() => {
    if (urlDate && urlDate.length >= 4) {
      return parseInt(urlDate.split('-')[0], 10);
    }
    return 2026;
  });
  const [selectedDate, setSelectedDate] = useState(urlDate || '');
  const [targetLine, setTargetLine] = useState(urlLine || null);

  // Collapsible toggle for deep-dive engineering sections
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Status & Metadata states
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [apiAvailability, setApiAvailability] = useState({});
  const requestId = useRef(0);

  // Analytical Data states
  const [energySummary, setEnergySummary] = useState(null);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [productionDailyTrend, setProductionDailyTrend] = useState([]);
  const [byMeter, setByMeter] = useState([]);
  const [byArea, setByArea] = useState([]);
  const [powerFactorData, setPowerFactorData] = useState(null);

  // Resolve active date bounds
  const resolvedDateRange = useMemo(() => {
    return resolveEnergyDateRange(selectedYear, selectedMonth, selectedDate);
  }, [selectedYear, selectedMonth, selectedDate]);

  // Telemetry coverage check (Database holds Aug 1 – Oct 31, 2026)
  const isDataOutOfCoverage = useMemo(() => {
    if (!resolvedDateRange?.startDate || !resolvedDateRange?.endDate) return false;
    return resolvedDateRange.startDate > '2026-10-31' || resolvedDateRange.endDate < '2026-08-01';
  }, [resolvedDateRange]);

  const loadEnergyData = useCallback(async (isRefresh = false) => {
    const currentRequestId = ++requestId.current;
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    // Build query parameters based on active scope
    const filterParams = {
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
      ...(resolvedDateRange?.startDate ? { start_date: resolvedDateRange.startDate } : {}),
      ...(resolvedDateRange?.endDate ? { end_date: resolvedDateRange.endDate } : {}),
    };

    try {
      const results = await Promise.allSettled([
        energyApi.getSummary(filterParams),
        energyApi.getDailyTrend(filterParams),
        productionApi.getDailyTrend(filterParams),
        energyApi.getByMeter(filterParams),
        energyApi.getByArea(filterParams),
        energyApi.getPowerFactorSummary(filterParams),
      ]);
      if (currentRequestId !== requestId.current) return;

      const [summaryRes, trendRes, productionTrendRes, meterRes, areaRes, pfRes] = results;
      const feedNames = [
        'Energy summary',
        'Daily trend',
        'Daily production trend',
        'Energy by meter',
        'Energy by area',
        'Power factor summary',
      ];
      const availability = Object.fromEntries(
        feedNames.map((name, index) => [
          name,
          { available: results[index].status === 'fulfilled' },
        ])
      );
      availability['Daily production trend'] = {
        available: productionTrendRes.status === 'fulfilled' && Array.isArray(productionTrendRes.value),
      };
      setApiAvailability(availability);

      setEnergySummary(summaryRes.status === 'fulfilled' ? summaryRes.value : null);
      setDailyTrend(trendRes.status === 'fulfilled' ? trendRes.value || [] : []);
      setProductionDailyTrend(
        productionTrendRes.status === 'fulfilled' && Array.isArray(productionTrendRes.value)
          ? productionTrendRes.value
          : []
      );
      setByMeter(meterRes.status === 'fulfilled' ? meterRes.value || [] : []);
      setByArea(areaRes.status === 'fulfilled' ? areaRes.value || [] : []);
      setPowerFactorData(pfRes.status === 'fulfilled' ? pfRes.value : null);

      if (summaryRes.status === 'rejected') {
        throw new Error(summaryRes.reason?.message || 'Failed to retrieve energy summary.');
      }

      setLastRefreshed(new Date());
    } catch (err) {
      if (currentRequestId !== requestId.current) return;
      console.error('Energy Analytics data load error:', err);
      setError(err.message || 'Unable to load energy analytics. Verify backend connection.');
    } finally {
      if (currentRequestId === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [selectedPlant, resolvedDateRange]);

  useEffect(() => {
    loadEnergyData(false);
  }, [loadEnergyData]);

  const handleRefresh = () => {
    loadEnergyData(true);
  };

  const handleResetFilters = () => {
    setSelectedPlant(null);
    setSelectedMonth(10);
    setSelectedYear(2026);
    setSelectedDate('');
  };

  // Convert resolved date bounds into standard range format
  const dateRangeForSections = resolvedDateRange?.startDate && resolvedDateRange?.endDate
    ? { start_date: resolvedDateRange.startDate, end_date: resolvedDateRange.endDate }
    : null;

  return (
    <div className="dashboard-container">
      {/* 1. Compact Modern Filter Toolbar: Plant | Month | Date | Clear Filters */}
      <EnergyPageHeader
        selectedPlant={selectedPlant}
        onSelectPlant={setSelectedPlant}
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
          <div className="loading-title">Retrieving Energy Telemetry & Metrics...</div>
          <div className="loading-subtitle">Querying energy interval meters, power factor logs, and area distribution data</div>
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
          <div className="error-title">Unable to Load Energy Analytics</div>
          <div className="error-desc">{error}</div>
          <button type="button" className="error-retry-btn" onClick={() => loadEnergyData(false)}>
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
                  Selected filter period has no telemetry records in the PostgreSQL dataset (coverage: Aug 1 – Oct 31, 2026). Displaying authentic zero/empty state.
                </span>
              </div>
              <button
                type="button"
                className="filter-reset-btn"
                onClick={handleResetFilters}
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem', whiteSpace: 'nowrap' }}
              >
                Reset to October 2026
              </button>
            </div>
          )}

          {/* Feed Offline Notice */}
          {Object.entries(apiAvailability).some(([, status]) => !status.available) && (
            <div className="data-integrity-notice-box" role="status">
              <div className="integrity-content">
                <div className="integrity-title">Some telemetry feeds are offline</div>
                <p className="integrity-text">
                  Endpoints unavailable: {Object.entries(apiAvailability)
                    .filter(([, status]) => !status.available)
                    .map(([name]) => name)
                    .join(', ')}. These sections are shown as unavailable rather than zero.
                </p>
              </div>
            </div>
          )}

          {/* Section 1: Exactly 4 Primary KPI Cards + Secondary Metrics Strip */}
          <EnergyKpis
            energySummary={energySummary}
            powerFactorData={powerFactorData}
            dailyTrend={dailyTrend}
            resolvedDateRange={resolvedDateRange}
            summaryAvailable={apiAvailability['Energy summary']?.available === true}
            pfAvailable={apiAvailability['Power factor summary']?.available === true}
            dailyTrendAvailable={apiAvailability['Daily trend']?.available === true}
          />

          {/* Section 2: Core Visualization A - Daily Energy Consumption Trend */}
          <EnergyTrendChart
            dailyTrend={dailyTrend}
            dataAvailable={apiAvailability['Daily trend']?.available === true}
            dateRange={dateRangeForSections}
            selectedPlant={selectedPlant}
          />

          {/* Section 2B: Energy Intensity Trends per Good Finished Unit (kWh, INR, kg CO2e) */}
          <EnergyIntensityTrendsSection
            selectedPlant={selectedPlant}
            dateRange={dateRangeForSections}
          />

          {/* Section 2C: Operating Context & Line Stoppage Analysis */}
          <OperatingContextSection
            selectedPlant={selectedPlant}
            dateRange={dateRangeForSections}
            initialLineId={targetLine}
            initialEpisodeId={urlEpisodeId}
          />

          {/* Section 3: Core Visualization B - Energy Consumption by Submeter */}
          <EnergyMeterBreakdown
            byMeter={byMeter}
            dataAvailable={apiAvailability['Energy by meter']?.available === true}
          />

          {/* Section 4: Core Visualization C - Energy Consumption by Functional Area */}
          <EnergyAreaDistribution
            byArea={byArea}
            dataAvailable={apiAvailability['Energy by area']?.available === true}
          />

          {/* Section 5: Core Visualization D - Power Factor Monitoring & Compliance */}
          <PowerFactorSection
            powerFactorData={powerFactorData}
            byMeter={byMeter}
            dataAvailable={apiAvailability['Power factor summary']?.available === true}
            meterDataAvailable={apiAvailability['Energy by meter']?.available === true}
          />

          {/* Section 6: Collapsible Detailed Engineering Analytics & Technical Records */}
          <div className="advanced-analytics-collapsible-card">
            <button
              type="button"
              className={`advanced-toggle-btn ${showAdvanced ? 'open' : ''}`}
              onClick={() => setShowAdvanced((prev) => !prev)}
              aria-expanded={showAdvanced}
            >
              <div className="advanced-toggle-title">
                <svg
                  className={`chevron-icon ${showAdvanced ? 'open' : ''}`}
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
                <span>Detailed Engineering Analytics & Records</span>
              </div>
              <span className="advanced-toggle-hint">
                {showAdvanced
                  ? 'Click to collapse technical models and drill-downs'
                  : 'Click to expand calendar heatmap, regression scatter, IQR outliers & what-if simulator'}
              </span>
            </button>

            {showAdvanced && (
              <div className="advanced-content-wrapper">
                {/* 1. Daily Consumption Calendar Heatmap */}
                <EnergyConsumptionHeatmap
                  dailyTrend={dailyTrend}
                  dataAvailable={apiAvailability['Daily trend']?.available === true}
                  selectedPlant={selectedPlant}
                />

                {/* 2. Energy vs Production Regression & Scatter */}
                <EnergyProductionRelationship
                  energyTrend={dailyTrend}
                  productionTrend={productionDailyTrend}
                  energyAvailable={apiAvailability['Daily trend']?.available === true}
                  productionAvailable={apiAvailability['Daily production trend']?.available === true}
                  selectedPlant={selectedPlant}
                  dataScope={selectedPlant}
                />

                {/* 3. Statistical Performance Exceptions (IQR Fences) */}
                <EnergyPerformanceExceptions
                  energyTrend={dailyTrend}
                  productionTrend={productionDailyTrend}
                  energyAvailable={apiAvailability['Daily trend']?.available === true}
                  productionAvailable={apiAvailability['Daily production trend']?.available === true}
                  selectedPlant={selectedPlant}
                  dataScope={selectedPlant}
                />

                {/* 4. Tariff Scenario & What-If Simulation */}
                <TariffWhatIfAnalysis
                  energySummary={energySummary}
                  summaryAvailable={apiAvailability['Energy summary']?.available === true}
                  dateRange={dateRangeForSections}
                  selectedPlant={selectedPlant}
                />

                {/* 5. Period-over-Period Performance Comparison */}
                <EnergyPerformanceComparison
                  selectedPlant={selectedPlant}
                  dateRange={dateRangeForSections}
                  refreshToken={lastRefreshed}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
