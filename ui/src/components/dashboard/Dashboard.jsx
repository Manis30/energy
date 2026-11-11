import React, { useState, useEffect, useCallback } from 'react';
import {
  energyApi,
  productionApi,
  energyIntensityApi,
  anomalyApi,
} from '../../services';

import DashboardHeader from './DashboardHeader';
import KpiOverview from './KpiOverview';
import EnergySection from './EnergySection';
import ProductionSection from './ProductionSection';
import EnergyEfficiencySection from './EnergyEfficiencySection';
import AnomalySection from './AnomalySection';

export default function Dashboard() {
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Analytical data states
  const [energySummary, setEnergySummary] = useState(null);
  const [energyDailyTrend, setEnergyDailyTrend] = useState([]);
  const [energyByMeter, setEnergyByMeter] = useState([]);
  const [energyByArea, setEnergyByArea] = useState([]);

  const [productionSummary, setProductionSummary] = useState(null);
  const [productionDailyTrend, setProductionDailyTrend] = useState([]);
  const [productionByLine, setProductionByLine] = useState([]);

  const [processEnergy, setProcessEnergy] = useState(null);
  const [factoryEnergy, setFactoryEnergy] = useState(null);

  const [anomaliesData, setAnomaliesData] = useState(null);

  const loadDashboardData = useCallback(async (isRefresh = false) => {
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
        productionApi.getSummary(filterParams),
        productionApi.getDailyTrend(filterParams),
        productionApi.getByLine(filterParams),
        energyIntensityApi.getProcessEnergy(filterParams),
        energyIntensityApi.getFactoryEnergy(filterParams),
        anomalyApi.getAllAnomalies(filterParams),
      ]);

      const [
        eSummaryRes,
        eTrendRes,
        eMeterRes,
        eAreaRes,
        pSummaryRes,
        pTrendRes,
        pLineRes,
        secProcessRes,
        secFactoryRes,
        anomRes,
      ] = results;

      // Extract results safely
      if (eSummaryRes.status === 'fulfilled') setEnergySummary(eSummaryRes.value);
      if (eTrendRes.status === 'fulfilled') setEnergyDailyTrend(eTrendRes.value);
      if (eMeterRes.status === 'fulfilled') setEnergyByMeter(eMeterRes.value);
      if (eAreaRes.status === 'fulfilled') setEnergyByArea(eAreaRes.value);

      if (pSummaryRes.status === 'fulfilled') setProductionSummary(pSummaryRes.value);
      if (pTrendRes.status === 'fulfilled') setProductionDailyTrend(pTrendRes.value);
      if (pLineRes.status === 'fulfilled') setProductionByLine(pLineRes.value);

      if (secProcessRes.status === 'fulfilled') setProcessEnergy(secProcessRes.value);
      if (secFactoryRes.status === 'fulfilled') setFactoryEnergy(secFactoryRes.value);

      if (anomRes.status === 'fulfilled') setAnomaliesData(anomRes.value);

      // Check if primary endpoints failed completely
      const primaryFailed = eSummaryRes.status === 'rejected' && pSummaryRes.status === 'rejected';
      if (primaryFailed) {
        throw new Error(eSummaryRes.reason?.message || pSummaryRes.reason?.message || 'Failed to load primary dashboard data.');
      }

      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Dashboard data load error:', err);
      setError(err.message || 'Unable to load dashboard analytics. Verify backend connection.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedPlant]);

  useEffect(() => {
    loadDashboardData(false);
  }, [loadDashboardData]);

  const handleRefresh = () => {
    loadDashboardData(true);
  };

  // Derive source date range from energy or production trend
  const dateRange = energyDailyTrend.length > 0 ? {
    start_date: energyDailyTrend[0].date,
    end_date: energyDailyTrend[energyDailyTrend.length - 1].date,
  } : null;

  return (
    <div className="dashboard-container">
      <DashboardHeader
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
          <div className="loading-title">Retrieving Factory Telemetry & Analytics...</div>
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
          <div className="error-title">Unable to Load Dashboard</div>
          <div className="error-desc">{error}</div>
          <button type="button" className="error-retry-btn" onClick={() => loadDashboardData(false)}>
            Retry Connection
          </button>
        </div>
      ) : (
        <div className="dashboard-content-flow">
          {/* Section 1: KPI Overview */}
          <KpiOverview
            energySummary={energySummary}
            productionSummary={productionSummary}
          />

          {/* Section 2: Specific Energy Consumption & Intensity */}
          <EnergyEfficiencySection
            processEnergy={processEnergy}
            factoryEnergy={factoryEnergy}
          />

          {/* Section 3: Energy Consumption Analytics */}
          <EnergySection
            dailyTrend={energyDailyTrend}
            byMeter={energyByMeter}
            byArea={energyByArea}
          />

          {/* Section 4: Production Analytics */}
          <ProductionSection
            dailyTrend={productionDailyTrend}
            byLine={productionByLine}
            productionSummary={productionSummary}
          />

          {/* Section 5: Automated Anomaly Detection */}
          <AnomalySection
            anomaliesData={anomaliesData}
          />
        </div>
      )}
    </div>
  );
}
