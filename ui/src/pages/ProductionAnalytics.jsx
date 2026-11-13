import React, { useState, useEffect, useCallback } from 'react';
import { productionApi } from '../services';

import ProductionPageHeader from './production/ProductionPageHeader';
import ProductionKpis from './production/ProductionKpis';
import ProductionTrendChart from './production/ProductionTrendChart';
import ProductionQualitySection from './production/ProductionQualitySection';
import ProductionByLine from './production/ProductionByLine';
import ProductionByProductAndShift from './production/ProductionByProductAndShift';
import ProductionDowntimeSection from './production/ProductionDowntimeSection';

export default function ProductionAnalytics() {
  const [selectedPlant, setSelectedPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Analytical data states
  const [productionSummary, setProductionSummary] = useState(null);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [byLine, setByLine] = useState([]);
  const [byProduct, setByProduct] = useState([]);
  const [byShift, setByShift] = useState([]);
  const [downtimeByReason, setDowntimeByReason] = useState([]);
  const [unavailableFeeds, setUnavailableFeeds] = useState([]);

  const loadProductionData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    const filterParams = selectedPlant ? { plant_id: selectedPlant } : {};

    try {
      const results = await Promise.allSettled([
        productionApi.getSummary(filterParams),
        productionApi.getDailyTrend(filterParams),
        productionApi.getByLine(filterParams),
        productionApi.getByProduct(filterParams),
        productionApi.getByShift(filterParams),
        productionApi.getDowntimeByReason(filterParams),
      ]);

      const [summaryRes, trendRes, lineRes, productRes, shiftRes, downtimeRes] = results;
      const feedNames = [
        'Production summary',
        'Daily production trend',
        'Production by line',
        'Production by product',
        'Production by shift',
        'Downtime by reason',
      ];
      setUnavailableFeeds(feedNames.filter((_, index) => results[index].status === 'rejected'));

      setProductionSummary(summaryRes.status === 'fulfilled' ? summaryRes.value : null);
      setDailyTrend(trendRes.status === 'fulfilled' ? trendRes.value || [] : []);
      setByLine(lineRes.status === 'fulfilled' ? lineRes.value || [] : []);
      setByProduct(productRes.status === 'fulfilled' ? productRes.value || [] : []);
      setByShift(shiftRes.status === 'fulfilled' ? shiftRes.value || [] : []);
      setDowntimeByReason(downtimeRes.status === 'fulfilled' ? downtimeRes.value || [] : []);

      // If summary failed, flag error
      if (summaryRes.status === 'rejected') {
        throw new Error(summaryRes.reason?.message || 'Failed to retrieve production summary.');
      }

      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Production Analytics data load error:', err);
      setError(err.message || 'Unable to load production analytics. Verify backend connection.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedPlant]);

  useEffect(() => {
    loadProductionData(false);
  }, [loadProductionData]);

  const handleRefresh = () => {
    loadProductionData(true);
  };

  // Derive the range from dates actually returned, independent of response ordering.
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
      <ProductionPageHeader
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
          <div className="loading-title">Retrieving Production Telemetry & Quality Records...</div>
          <div className="loading-subtitle">Loading production summary, trend, line, product, shift, and downtime data</div>
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
          <div className="error-title">Unable to Load Production Analytics</div>
          <div className="error-desc">{error}</div>
          <button type="button" className="error-retry-btn" onClick={() => loadProductionData(false)}>
            Retry Connection
          </button>
        </div>
      ) : (
        <div className="dashboard-content-flow">
          {unavailableFeeds.length > 0 && (
            <div className="data-integrity-notice-box" role="status">
              <div className="integrity-content">
                <div className="integrity-title">Some production data is unavailable</div>
                <p className="integrity-text">
                  Requests not returned: {unavailableFeeds.join(', ')}. These sections cannot be interpreted as zero production or zero downtime.
                </p>
              </div>
            </div>
          )}

          {/* Section 1: 6 Supported KPI Cards */}
          <ProductionKpis
            summary={productionSummary}
          />

          {/* Section 2: Daily Production & Defect Trend */}
          <ProductionTrendChart
            dailyTrend={dailyTrend}
            dataAvailable={!unavailableFeeds.includes('Daily production trend')}
          />

          {/* Section 3: Production Quality & Mathematical Quantity Balance */}
          <ProductionQualitySection
            summary={productionSummary}
          />

          {/* Section 4: Production Output by Manufacturing Line */}
          <ProductionByLine
            byLine={byLine}
            dataAvailable={!unavailableFeeds.includes('Production by line')}
          />

          {/* Section 5: Output by Product SKU & Operating Shift */}
          <ProductionByProductAndShift
            byProduct={byProduct}
            byShift={byShift}
            productDataAvailable={!unavailableFeeds.includes('Production by product')}
            shiftDataAvailable={!unavailableFeeds.includes('Production by shift')}
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

