import React, { useState, useEffect, useCallback } from 'react';
import { energyApi } from '../services';

import EnergyPageHeader from './energy/EnergyPageHeader';
import EnergyKpis from './energy/EnergyKpis';
import EnergyTrendChart from './energy/EnergyTrendChart';
import EnergyMeterBreakdown from './energy/EnergyMeterBreakdown';
import EnergyAreaDistribution from './energy/EnergyAreaDistribution';
import PowerFactorSection from './energy/PowerFactorSection';
import CostEmissionsSection from './energy/CostEmissionsSection';

export default function EnergyAnalytics() {
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Analytical data states
  const [energySummary, setEnergySummary] = useState(null);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [byMeter, setByMeter] = useState([]);
  const [byArea, setByArea] = useState([]);
  const [powerFactorData, setPowerFactorData] = useState(null);

  const loadEnergyData = useCallback(async (isRefresh = false) => {
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
        energyApi.getByMeter(filterParams),
        energyApi.getByArea(filterParams),
        energyApi.getPowerFactorSummary(filterParams),
      ]);

      const [summaryRes, trendRes, meterRes, areaRes, pfRes] = results;

      if (summaryRes.status === 'fulfilled') setEnergySummary(summaryRes.value);
      if (trendRes.status === 'fulfilled') setDailyTrend(trendRes.value);
      if (meterRes.status === 'fulfilled') setByMeter(meterRes.value);
      if (areaRes.status === 'fulfilled') setByArea(areaRes.value);
      if (pfRes.status === 'fulfilled') setPowerFactorData(pfRes.value);

      // If summary failed, flag error
      if (summaryRes.status === 'rejected') {
        throw new Error(summaryRes.reason?.message || 'Failed to retrieve energy summary.');
      }

      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Energy Analytics data load error:', err);
      setError(err.message || 'Unable to load energy analytics. Verify backend connection.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedPlant]);

  useEffect(() => {
    loadEnergyData(false);
  }, [loadEnergyData]);

  const handleRefresh = () => {
    loadEnergyData(true);
  };

  // Derive source date range
  const dateRange = dailyTrend.length > 0 ? {
    start_date: dailyTrend[0].date,
    end_date: dailyTrend[dailyTrend.length - 1].date,
  } : null;

  return (
    <div className="dashboard-container">
      <EnergyPageHeader
        dateRange={dateRange}
        lastRefreshed={lastRefreshed}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        selectedPlant={selectedPlant}
        onSelectPlant={setSelectedPlant}
      />

      {loading ? (
        <div className="dashboard-loading-state">
          <div className="loading-spinner"></div>
          <div className="loading-title">Retrieving Energy Telemetry & Metrics...</div>
          <div className="loading-subtitle">Querying verified records from Neon PostgreSQL database</div>
        </div>
      ) : error ? (
        <div className="dashboard-error-state">
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
          {/* Section 1: 6 KPI Cards */}
          <EnergyKpis
            energySummary={energySummary}
            dailyTrendCount={dailyTrend.length || 92}
          />

          {/* Section 2: Daily Consumption Trend Chart */}
          <EnergyTrendChart
            dailyTrend={dailyTrend}
          />

          {/* Section 3: Consumption by Submeter */}
          <EnergyMeterBreakdown
            byMeter={byMeter}
          />

          {/* Section 4: Consumption by Area and Boundary Segregation */}
          <EnergyAreaDistribution
            byArea={byArea}
          />

          {/* Section 5: Power Factor Monitoring */}
          <PowerFactorSection
            powerFactorData={powerFactorData}
            byMeter={byMeter}
          />

          {/* Section 6: Energy Cost & Carbon Emissions Accounting */}
          <CostEmissionsSection
            energySummary={energySummary}
            byArea={byArea}
          />
        </div>
      )}
    </div>
  );
}
