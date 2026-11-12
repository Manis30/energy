import React, { useState, useEffect, useCallback } from 'react';
import {
  energyApi,
  productionApi,
  energyIntensityApi,
  anomalyApi,
} from '../services';

import DailyPageHeader from './daily/DailyPageHeader';
import DailyEnergyKpis from './daily/DailyEnergyKpis';
import DailyProductionSection from './daily/DailyProductionSection';
import DailyIntensitySection from './daily/DailyIntensitySection';
import DailyChartsSection from './daily/DailyChartsSection';
import DailyAnomalySummary from './daily/DailyAnomalySummary';
import { formatDate } from '../utils/formatters';

const MIN_DATE = '2026-08-01';
const MAX_DATE = '2026-10-31';
const DEFAULT_DATE = '2026-08-15';

export default function DailyAnalysis() {
  const [selectedDate, setSelectedDate] = useState(DEFAULT_DATE);
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [dateWarning, setDateWarning] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Analytical data states
  const [energySummary, setEnergySummary] = useState(null);
  const [byMeter, setByMeter] = useState([]);
  const [byArea, setByArea] = useState([]);
  const [powerFactorData, setPowerFactorData] = useState(null);
  const [productionSummary, setProductionSummary] = useState(null);
  const [byLine, setByLine] = useState([]);
  const [processIntensity, setProcessIntensity] = useState(null);
  const [factoryIntensity, setFactoryIntensity] = useState(null);
  const [anomaliesData, setAnomaliesData] = useState(null);
  const [dailyTrend, setDailyTrend] = useState([]);

  const loadDailyData = useCallback(async (isRefresh = false) => {
    // Validate date against verified dataset period
    if (!selectedDate || selectedDate < MIN_DATE || selectedDate > MAX_DATE) {
      setDateWarning(`Available dataset coverage is August 1, 2026 – October 31, 2026. Date ${selectedDate} is outside this range.`);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    setDateWarning(null);

    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    // Compute bounded 7-day start date for contextual trend (strictly within dataset range)
    const dObj = new Date(selectedDate + 'T00:00:00Z');
    dObj.setUTCDate(dObj.getUTCDate() - 6);
    const raw7DayStart = dObj.toISOString().split('T')[0];
    const trendStartDate = raw7DayStart < MIN_DATE ? MIN_DATE : (raw7DayStart > MAX_DATE ? MAX_DATE : raw7DayStart);
    const trendEndDate = selectedDate > MAX_DATE ? MAX_DATE : (selectedDate < MIN_DATE ? MIN_DATE : selectedDate);

    const baseParams = {
      start_date: selectedDate,
      end_date: selectedDate,
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
    };

    const anomalyParams = {
      start_time: `${selectedDate}T00:00:00`,
      end_time: `${selectedDate}T23:59:59`,
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
    };

    const trendParams = {
      start_date: trendStartDate,
      end_date: trendEndDate,
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
    };

    try {
      const results = await Promise.allSettled([
        energyApi.getSummary(baseParams),
        energyApi.getByMeter(baseParams),
        energyApi.getByArea(baseParams),
        energyApi.getPowerFactorSummary(baseParams),
        productionApi.getSummary(baseParams),
        productionApi.getByLine(baseParams),
        energyIntensityApi.getProcessEnergy(baseParams),
        energyIntensityApi.getFactoryEnergy(baseParams),
        anomalyApi.getAllAnomalies(anomalyParams),
        energyApi.getDailyTrend(trendParams),
      ]);

      const [
        summaryRes,
        meterRes,
        areaRes,
        pfRes,
        prodSumRes,
        lineRes,
        procIntRes,
        factIntRes,
        anomRes,
        trendRes,
      ] = results;

      if (summaryRes.status === 'fulfilled') setEnergySummary(summaryRes.value);
      if (meterRes.status === 'fulfilled') setByMeter(meterRes.value || []);
      if (areaRes.status === 'fulfilled') setByArea(areaRes.value || []);
      if (pfRes.status === 'fulfilled') setPowerFactorData(pfRes.value);
      if (prodSumRes.status === 'fulfilled') setProductionSummary(prodSumRes.value);
      if (lineRes.status === 'fulfilled') setByLine(lineRes.value || []);
      if (procIntRes.status === 'fulfilled') setProcessIntensity(procIntRes.value);
      if (factIntRes.status === 'fulfilled') setFactoryIntensity(factIntRes.value);
      if (anomRes.status === 'fulfilled') setAnomaliesData(anomRes.value);
      if (trendRes.status === 'fulfilled') setDailyTrend(trendRes.value || []);

      // If critical summary failed, record error
      if (summaryRes.status === 'rejected') {
        throw new Error(summaryRes.reason?.message || 'Failed to retrieve daily energy telemetry.');
      }

      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Daily Analysis load error:', err);
      setError(err.message || 'Unable to retrieve daily analytics from backend.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedDate, selectedPlant]);

  useEffect(() => {
    loadDailyData(false);
  }, [loadDailyData]);

  const handleRefresh = () => {
    loadDailyData(true);
  };

  const isDayEmpty = energySummary && Number(energySummary.total_readings) === 0;

  return (
    <div className="dashboard-container daily-analysis-page">
      <DailyPageHeader
        selectedDate={selectedDate}
        onDateChange={setSelectedDate}
        selectedPlant={selectedPlant}
        onSelectPlant={setSelectedPlant}
        lastRefreshed={lastRefreshed}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        dateWarning={dateWarning}
      />

      {loading ? (
        <div className="dashboard-loading-state">
          <div className="loading-spinner"></div>
          <div className="loading-title">Retrieving Daily Operational Telemetry...</div>
          <div className="loading-subtitle">
            Querying energy submeters, production lines, and anomaly algorithms for {formatDate(selectedDate)}
          </div>
        </div>
      ) : error ? (
        <div className="dashboard-error-state">
          <div className="error-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div className="error-title">Daily Analysis Telemetry Unavailable</div>
          <div className="error-message">{error}</div>
          <button
            type="button"
            className="dashboard-refresh-btn"
            onClick={() => loadDailyData(false)}
            style={{ marginTop: '1.25rem' }}
          >
            Retry Query
          </button>
        </div>
      ) : isDayEmpty ? (
        <div className="daily-empty-state-card">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
          </div>
          <h3 className="empty-state-title">No Records Logged for {formatDate(selectedDate)}</h3>
          <p className="empty-state-desc">
            No energy telemetry readings or production records were found for {selectedPlant ? `Plant ${selectedPlant}` : 'monitored plants'} on this date.
            The verified platform dataset covers August 1, 2026 through October 31, 2026.
          </p>
          <div className="empty-state-actions">
            <button
              type="button"
              className="dashboard-refresh-btn"
              onClick={() => setSelectedDate(DEFAULT_DATE)}
            >
              Reset to Aug 15, 2026
            </button>
          </div>
        </div>
      ) : (
        <div className="daily-analysis-content">
          {/* Section B: Daily Energy Performance */}
          <DailyEnergyKpis
            energySummary={energySummary}
            powerFactorData={powerFactorData}
          />

          {/* Section C: Daily Production Performance */}
          <DailyProductionSection
            productionSummary={productionSummary}
          />

          {/* Section D: Energy Intensity Analysis */}
          <DailyIntensitySection
            processEnergy={processIntensity}
            factoryEnergy={factoryIntensity}
          />

          {/* Section E: Daily Energy Trends & Charts */}
          <DailyChartsSection
            byMeter={byMeter}
            byArea={byArea}
            byLine={byLine}
            dailyTrend={dailyTrend}
            selectedDate={selectedDate}
          />

          {/* Section F: Daily Anomaly Summary */}
          <DailyAnomalySummary
            anomaliesData={anomaliesData}
          />
        </div>
      )}
    </div>
  );
}
