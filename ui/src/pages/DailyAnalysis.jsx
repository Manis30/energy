import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
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
import DailyDataConfidence from './daily/DailyDataConfidence';
import DailyIntelligenceSummary from './daily/DailyIntelligenceSummary';
import './daily/daily-confidence.css';
import { formatDate } from '../utils/formatters';

const MIN_DATE = '2026-01-01';
const MAX_DATE = '2030-12-31';
const DEFAULT_DATE = '2026-08-15';

export default function DailyAnalysis() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const dateParam = searchParams.get('date');

  const [selectedDate, setSelectedDate] = useState(() => dateParam || DEFAULT_DATE);
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [dateWarning, setDateWarning] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Sync with URL query parameter when navigating from Daily Reports
  useEffect(() => {
    if (dateParam && dateParam !== selectedDate) {
      setSelectedDate(dateParam);
    }
  }, [dateParam]);

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
  const [apiAvailability, setApiAvailability] = useState(null);
  const [trendPeriod, setTrendPeriod] = useState(null);

  const loadDailyData = useCallback(async (isRefresh = false) => {
    // Validate date against system bounds
    if (!selectedDate || selectedDate < MIN_DATE || selectedDate > MAX_DATE) {
      setDateWarning(`Date ${selectedDate} is outside supported operational range (${MIN_DATE} to ${MAX_DATE}).`);
      setApiAvailability(null);
      setTrendPeriod(null);
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

    // Compute bounded 7-day start date for contextual trend
    const dObj = new Date(selectedDate + 'T00:00:00Z');
    dObj.setUTCDate(dObj.getUTCDate() - 6);
    const raw7DayStart = dObj.toISOString().split('T')[0];
    const trendStartDate = raw7DayStart < MIN_DATE ? MIN_DATE : raw7DayStart;
    const trendEndDate = selectedDate;
    setTrendPeriod({ start_date: trendStartDate, end_date: trendEndDate });
    if (!isRefresh) setApiAvailability(null);

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

      const responses = [
        ['Energy summary', summaryRes],
        ['Energy by meter', meterRes],
        ['Energy by area', areaRes],
        ['Power factor summary', pfRes],
        ['Production summary', prodSumRes],
        ['Production by line', lineRes],
        ['Process energy intensity', procIntRes],
        ['Factory energy intensity', factIntRes],
        ['Anomaly analysis', anomRes],
        ['7-day energy trend', trendRes],
      ];
      setApiAvailability(Object.fromEntries(responses.map(([name, response]) => [
        name,
        {
          available: response.status === 'fulfilled',
          error: response.status === 'rejected' ? response.reason?.message : null,
        },
      ])));

      setEnergySummary(summaryRes.status === 'fulfilled' ? summaryRes.value : null);
      setByMeter(meterRes.status === 'fulfilled' ? meterRes.value || [] : []);
      setByArea(areaRes.status === 'fulfilled' ? areaRes.value || [] : []);
      setPowerFactorData(pfRes.status === 'fulfilled' ? pfRes.value : null);
      setProductionSummary(prodSumRes.status === 'fulfilled' ? prodSumRes.value : null);
      setByLine(lineRes.status === 'fulfilled' ? lineRes.value || [] : []);
      setProcessIntensity(procIntRes.status === 'fulfilled' ? procIntRes.value : null);
      setFactoryIntensity(factIntRes.status === 'fulfilled' ? factIntRes.value : null);
      setAnomaliesData(anomRes.status === 'fulfilled' ? anomRes.value : null);
      setDailyTrend(trendRes.status === 'fulfilled' ? trendRes.value || [] : []);

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

  const hasEnergyData = Boolean(energySummary && Number(energySummary.total_readings) > 0);
  const hasProductionData = Boolean(
    productionSummary && (Number(productionSummary.event_count) > 0 || Number(productionSummary.actual_qty) > 0)
  );
  const isDayEmpty = !hasEnergyData && !hasProductionData && (energySummary !== null || productionSummary !== null);

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
        minDate={MIN_DATE}
        maxDate={MAX_DATE}
      />

      {!loading && (
        <DailyIntelligenceSummary
          selectedDate={selectedDate}
          selectedPlant={selectedPlant}
          energySummary={energySummary}
          productionSummary={productionSummary}
          powerFactorData={powerFactorData}
          processIntensity={processIntensity}
          factoryIntensity={factoryIntensity}
          anomaliesData={anomaliesData}
          dailyTrend={dailyTrend}
          apiAvailability={apiAvailability}
          error={error}
          dateWarning={dateWarning}
        />
      )}

      {loading ? (
        <div className="dashboard-loading-state" role="status" aria-live="polite" aria-busy="true">
          <div className="loading-spinner"></div>
          <div className="loading-title">Retrieving Daily Operational Telemetry...</div>
          <div className="loading-subtitle">
            Querying energy submeters, production lines, and anomaly algorithms for {formatDate(selectedDate)}
          </div>
        </div>
      ) : error ? (
        <>
          {apiAvailability && (
            <DailyDataConfidence
              selectedDate={selectedDate}
              selectedPlant={selectedPlant}
              trendPeriod={trendPeriod}
              energySummary={energySummary}
              productionSummary={productionSummary}
              powerFactorData={powerFactorData}
              processIntensity={processIntensity}
              factoryIntensity={factoryIntensity}
              anomaliesData={anomaliesData}
              apiAvailability={apiAvailability}
            />
          )}
          <div className="dashboard-error-state" role="alert">
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
        </>
      ) : isDayEmpty ? (
        <>
          <DailyDataConfidence
            selectedDate={selectedDate}
            selectedPlant={selectedPlant}
            trendPeriod={trendPeriod}
            energySummary={energySummary}
            productionSummary={productionSummary}
            powerFactorData={powerFactorData}
            processIntensity={processIntensity}
            factoryIntensity={factoryIntensity}
            anomaliesData={anomaliesData}
            apiAvailability={apiAvailability}
          />
          <div className="daily-empty-state-card" role="status">
            <div className="empty-state-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/>
                <line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
            </div>
            <h3 className="empty-state-title">No Records Returned for {formatDate(selectedDate)}</h3>
            <p className="empty-state-desc">
              The energy and production summary APIs returned no records for {selectedPlant ? `Plant ${selectedPlant}` : 'the selected plant scope'} on this date. This does not establish completeness beyond those responses.
            </p>
            <div className="empty-state-actions" style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              <button
                type="button"
                className="dashboard-refresh-btn"
                onClick={() => setSelectedDate(DEFAULT_DATE)}
              >
                Reset to Aug 15, 2026
              </button>
              <button
                type="button"
                className="dashboard-refresh-btn"
                onClick={() => navigate('/daily-reports')}
                style={{ backgroundColor: 'var(--color-primary-600, #2563eb)', color: '#ffffff' }}
              >
                Upload Daily Report
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="daily-analysis-content">
          <DailyDataConfidence
            selectedDate={selectedDate}
            selectedPlant={selectedPlant}
            trendPeriod={trendPeriod}
            energySummary={energySummary}
            productionSummary={productionSummary}
            powerFactorData={powerFactorData}
            processIntensity={processIntensity}
            factoryIntensity={factoryIntensity}
            anomaliesData={anomaliesData}
            apiAvailability={apiAvailability}
          />

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
            productionAvailable={apiAvailability?.['Production summary']?.available === true}
            productionSummary={productionSummary}
          />

          {/* Section E: Daily Energy Trends & Charts */}
          <DailyChartsSection
            byMeter={byMeter}
            byArea={byArea}
            byLine={byLine}
            dailyTrend={dailyTrend}
            selectedDate={selectedDate}
            trendPeriod={trendPeriod}
            trendAvailable={apiAvailability?.['7-day energy trend']?.available === true}
          />

          {/* Section F: Daily Anomaly Summary */}
          <DailyAnomalySummary
            anomaliesData={anomaliesData}
            dataAvailable={apiAvailability?.['Anomaly analysis']?.available === true}
          />
        </div>
      )}
    </div>
  );
}
