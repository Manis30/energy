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
  const [unavailableFeeds, setUnavailableFeeds] = useState([]);

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
      const feedNames = [
        'Energy summary',
        'Energy trend',
        'Energy by meter',
        'Energy by area',
        'Production summary',
        'Production trend',
        'Production by line',
        'Process energy intensity',
        'Factory energy intensity',
        'Anomaly analysis',
      ];
      setUnavailableFeeds(feedNames.filter((_, index) => results[index].status === 'rejected'));

      setEnergySummary(eSummaryRes.status === 'fulfilled' ? eSummaryRes.value : null);
      setEnergyDailyTrend(eTrendRes.status === 'fulfilled' ? eTrendRes.value || [] : []);
      setEnergyByMeter(eMeterRes.status === 'fulfilled' ? eMeterRes.value || [] : []);
      setEnergyByArea(eAreaRes.status === 'fulfilled' ? eAreaRes.value || [] : []);
      setProductionSummary(pSummaryRes.status === 'fulfilled' ? pSummaryRes.value : null);
      setProductionDailyTrend(pTrendRes.status === 'fulfilled' ? pTrendRes.value || [] : []);
      setProductionByLine(pLineRes.status === 'fulfilled' ? pLineRes.value || [] : []);
      setProcessEnergy(secProcessRes.status === 'fulfilled' ? secProcessRes.value : null);
      setFactoryEnergy(secFactoryRes.status === 'fulfilled' ? secFactoryRes.value : null);
      setAnomaliesData(anomRes.status === 'fulfilled' ? anomRes.value : null);

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

  // Derive the date range from dates actually returned, independent of response ordering.
  const validDates = (trend) => (trend || [])
    .map((item) => item?.date)
    .filter((date) => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();
  const energyDates = validDates(energyDailyTrend);
  const productionDates = validDates(productionDailyTrend);
  const dateCoverage = energyDates.length > 0 ? energyDates : productionDates;
  const dateRange = dateCoverage.length > 0 ? {
    start_date: dateCoverage[0],
    end_date: dateCoverage[dateCoverage.length - 1],
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
        <div className="dashboard-loading-state" role="status" aria-live="polite" aria-busy="true">
          <div className="loading-spinner"></div>
          <div className="loading-title">Retrieving Factory Telemetry & Analytics...</div>
          <div className="loading-subtitle">Loading energy, production, intensity, and anomaly analytics</div>
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
                <div className="integrity-title">Some Dashboard data is unavailable</div>
                <p className="integrity-text">
                  Requests not returned: {unavailableFeeds.join(', ')}. These sections are unavailable, not zero; returned values may cover only part of the Dashboard.
                </p>
              </div>
            </div>
          )}

          {/* Section 1: KPI Overview */}
          <KpiOverview
            energySummary={energySummary}
            productionSummary={productionSummary}
            energyAvailable={!unavailableFeeds.includes('Energy summary')}
            productionAvailable={!unavailableFeeds.includes('Production summary')}
          />

          {/* Section 2: Specific Energy Consumption & Intensity */}
          <EnergyEfficiencySection
            processEnergy={processEnergy}
            factoryEnergy={factoryEnergy}
            processAvailable={!unavailableFeeds.includes('Process energy intensity')}
            factoryAvailable={!unavailableFeeds.includes('Factory energy intensity')}
          />

          {/* Section 3: Energy Consumption Analytics */}
          <EnergySection
            dailyTrend={energyDailyTrend}
            byMeter={energyByMeter}
            byArea={energyByArea}
            trendAvailable={!unavailableFeeds.includes('Energy trend')}
            meterAvailable={!unavailableFeeds.includes('Energy by meter')}
            areaAvailable={!unavailableFeeds.includes('Energy by area')}
          />

          {/* Section 4: Production Analytics */}
          <ProductionSection
            dailyTrend={productionDailyTrend}
            byLine={productionByLine}
            productionSummary={productionSummary}
            trendAvailable={!unavailableFeeds.includes('Production trend')}
            lineAvailable={!unavailableFeeds.includes('Production by line')}
            summaryAvailable={!unavailableFeeds.includes('Production summary')}
          />

          {/* Section 5: Automated Anomaly Detection */}
          <AnomalySection
            anomaliesData={anomaliesData}
            dataAvailable={!unavailableFeeds.includes('Anomaly analysis')}
          />
        </div>
      )}
    </div>
  );
}

