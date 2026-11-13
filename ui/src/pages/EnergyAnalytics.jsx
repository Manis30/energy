import React, { useState, useEffect, useCallback, useRef } from 'react';
import { energyApi, productionApi } from '../services';

import EnergyPageHeader from './energy/EnergyPageHeader';
import EnergyKpis from './energy/EnergyKpis';
import EnergyTrendChart from './energy/EnergyTrendChart';
import EnergyConsumptionHeatmap from './energy/EnergyConsumptionHeatmap';
import EnergyProductionRelationship from './energy/EnergyProductionRelationship';
import EnergyPerformanceExceptions from './energy/EnergyPerformanceExceptions';
import EnergyMeterBreakdown from './energy/EnergyMeterBreakdown';
import EnergyAreaDistribution from './energy/EnergyAreaDistribution';
import PowerFactorSection from './energy/PowerFactorSection';
import CostEmissionsSection from './energy/CostEmissionsSection';
import EnergyPerformanceComparison from './energy/EnergyPerformanceComparison';
import TariffWhatIfAnalysis from './energy/TariffWhatIfAnalysis';

export default function EnergyAnalytics() {
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [apiAvailability, setApiAvailability] = useState({});
  const [trendDataScope, setTrendDataScope] = useState(undefined);
  const requestId = useRef(0);

  // Analytical data states
  const [energySummary, setEnergySummary] = useState(null);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [productionDailyTrend, setProductionDailyTrend] = useState([]);
  const [byMeter, setByMeter] = useState([]);
  const [byArea, setByArea] = useState([]);
  const [powerFactorData, setPowerFactorData] = useState(null);

  const loadEnergyData = useCallback(async (isRefresh = false) => {
    const currentRequestId = ++requestId.current;
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    const filterParams = selectedPlant ? { plant_id: selectedPlant } : {};

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
      const availability = Object.fromEntries(feedNames.map((name, index) => [
        name,
        { available: results[index].status === 'fulfilled' },
      ]));
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
      setTrendDataScope(selectedPlant);
      setByMeter(meterRes.status === 'fulfilled' ? meterRes.value || [] : []);
      setByArea(areaRes.status === 'fulfilled' ? areaRes.value || [] : []);
      setPowerFactorData(pfRes.status === 'fulfilled' ? pfRes.value : null);

      // If summary failed, flag error
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
  }, [selectedPlant]);

  useEffect(() => {
    loadEnergyData(false);
  }, [loadEnergyData]);

  const handleRefresh = () => {
    loadEnergyData(true);
  };

  // Derive source date range
  const trendDates = dailyTrend
    .map((item) => item?.date)
    .filter((date) => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();
  const dateRange = trendDates.length > 0 ? {
    start_date: trendDates[0],
    end_date: trendDates[trendDates.length - 1],
  } : null;

  return (
    <div className="dashboard-container">
      <EnergyPageHeader
        dateRange={dateRange || (apiAvailability['Daily trend']?.available
          ? 'No daily trend dates returned'
          : 'Trend date range unavailable')}
        lastRefreshed={lastRefreshed}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        selectedPlant={selectedPlant}
        onSelectPlant={setSelectedPlant}
      />

      {loading ? (
        <div className="dashboard-loading-state" role="status" aria-live="polite" aria-busy="true">
          <div className="loading-spinner"></div>
          <div className="loading-title">Retrieving Energy Telemetry & Metrics...</div>
          <div className="loading-subtitle">Loading energy and production trends, energy summary, meter, area, and power-factor data</div>
        </div>
      ) : error ? (
        <div className="dashboard-error-state" role="alert">
          <div className="error-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
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
          {Object.entries(apiAvailability).some(([, status]) => !status.available) && (
            <div className="data-integrity-notice-box" role="status">
              <div className="integrity-content">
                <div className="integrity-title">Some energy data is unavailable</div>
                <p className="integrity-text">
                  Requests not returned: {Object.entries(apiAvailability)
                    .filter(([, status]) => !status.available)
                    .map(([name]) => name)
                    .join(', ')}. These sections are unavailable, not zero.
                </p>
              </div>
            </div>
          )}

          {/* Section 1: 6 KPI Cards */}
          <EnergyKpis
            energySummary={energySummary}
            dailyTrend={dailyTrend}
            dailyTrendAvailable={apiAvailability['Daily trend']?.available === true}
            dateRange={dateRange}
            summaryAvailable={apiAvailability['Energy summary']?.available === true}
          />

          {/* Section 2: Daily Consumption Trend Chart */}
          <EnergyTrendChart
            dailyTrend={dailyTrend}
            dataAvailable={apiAvailability['Daily trend']?.available === true}
            dateRange={dateRange}
          />

          <EnergyConsumptionHeatmap
            dailyTrend={dailyTrend}
            dataAvailable={apiAvailability['Daily trend']?.available === true}
            selectedPlant={selectedPlant}
          />

          <EnergyProductionRelationship
            energyTrend={dailyTrend}
            productionTrend={productionDailyTrend}
            energyAvailable={apiAvailability['Daily trend']?.available === true}
            productionAvailable={apiAvailability['Daily production trend']?.available === true}
            selectedPlant={selectedPlant}
            dataScope={trendDataScope}
          />

          <EnergyPerformanceExceptions
            energyTrend={dailyTrend}
            productionTrend={productionDailyTrend}
            energyAvailable={apiAvailability['Daily trend']?.available === true}
            productionAvailable={apiAvailability['Daily production trend']?.available === true}
            selectedPlant={selectedPlant}
            dataScope={trendDataScope}
          />

          {/* Section 3: Consumption by Submeter */}
          <EnergyMeterBreakdown
            byMeter={byMeter}
            dataAvailable={apiAvailability['Energy by meter']?.available === true}
          />

          {/* Section 4: Consumption by Area and Boundary Segregation */}
          <EnergyAreaDistribution
            byArea={byArea}
            dataAvailable={apiAvailability['Energy by area']?.available === true}
          />

          {/* Section 5: Power Factor Monitoring */}
          <PowerFactorSection
            powerFactorData={powerFactorData}
            byMeter={byMeter}
            dataAvailable={apiAvailability['Power factor summary']?.available === true}
            meterDataAvailable={apiAvailability['Energy by meter']?.available === true}
          />

          {/* Section 6: Energy Cost & Carbon Emissions Accounting */}
          <CostEmissionsSection
            energySummary={energySummary}
            byArea={byArea}
            summaryAvailable={apiAvailability['Energy summary']?.available === true}
            areaAvailable={apiAvailability['Energy by area']?.available === true}
          />

          <EnergyPerformanceComparison
            selectedPlant={selectedPlant}
            dateRange={dateRange}
            refreshToken={lastRefreshed}
          />

          <TariffWhatIfAnalysis
            energySummary={energySummary}
            summaryAvailable={apiAvailability['Energy summary']?.available === true}
            dateRange={dateRange}
            selectedPlant={selectedPlant}
          />
        </div>
      )}
    </div>
  );
}

