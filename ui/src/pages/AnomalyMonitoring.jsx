import React, { useState, useEffect, useCallback } from 'react';
import { anomalyApi } from '../services';

import AnomalyPageHeader from './anomalies/AnomalyPageHeader';
import AnomalyKpis from './anomalies/AnomalyKpis';
import RecentSignificantSection from './anomalies/RecentSignificantSection';
import StatisticalAnomaliesSection from './anomalies/StatisticalAnomaliesSection';
import RollingBaselineSection from './anomalies/RollingBaselineSection';
import StandbyEnergySection from './anomalies/StandbyEnergySection';
import PowerFactorAnomalySection from './anomalies/PowerFactorAnomalySection';

export default function AnomalyMonitoring() {
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Unified anomaly data state
  const [anomalyData, setAnomalyData] = useState(null);

  const loadAnomalyData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    const filterParams = selectedPlant ? { plant_id: selectedPlant } : {};

    try {
      const result = await anomalyApi.getAllAnomalies(filterParams);
      setAnomalyData(result);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Anomaly Monitoring data load error:', err);
      setError(err.message || 'Unable to load anomaly detection data. Verify backend connection.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedPlant]);

  useEffect(() => {
    loadAnomalyData(false);
  }, [loadAnomalyData]);

  const handleRefresh = () => {
    loadAnomalyData(true);
  };

  const dateRange = {
    start_date: anomalyData?.analysis_period?.start_time ? anomalyData.analysis_period.start_time.slice(0, 10) : '2026-08-01',
    end_date: anomalyData?.analysis_period?.end_time ? anomalyData.analysis_period.end_time.slice(0, 10) : '2026-10-31',
  };

  return (
    <div className="dashboard-container">
      <AnomalyPageHeader
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
          <div className="loading-title">Executing Deterministic Anomaly Surveillance...</div>
          <div className="loading-subtitle">Running Z-score, rolling baseline, power factor, and standby power models</div>
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
          <div className="error-title">Unable to Load Anomaly Monitoring</div>
          <div className="error-desc">{error}</div>
          <button type="button" className="error-retry-btn" onClick={() => loadAnomalyData(false)}>
            Retry Surveillance Query
          </button>
        </div>
      ) : (
        <div className="dashboard-content-flow">
          {/* Section 1: KPI Overview */}
          <AnomalyKpis
            data={anomalyData}
          />

          {/* Section 2: Highest Magnitude Significant Exceptions */}
          <RecentSignificantSection
            statData={anomalyData?.statistical_zscore}
            rollingData={anomalyData?.rolling_baseline}
          />

          {/* Section 3: Statistical Z-Score Energy Anomalies */}
          <StatisticalAnomaliesSection
            statisticalData={anomalyData?.statistical_zscore}
          />

          {/* Section 4: Rolling Baseline Deviations */}
          <RollingBaselineSection
            rollingData={anomalyData?.rolling_baseline}
          />

          {/* Section 5: Zero-Production Standby Energy Draw */}
          <StandbyEnergySection
            standbyData={anomalyData?.zero_production_standby}
          />

          {/* Section 6: Power Factor Compliance Surveillance */}
          <PowerFactorAnomalySection
            lpfData={anomalyData?.low_power_factor}
          />
        </div>
      )}
    </div>
  );
}
