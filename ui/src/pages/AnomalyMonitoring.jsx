import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { anomalyApi } from '../services';
import AnomalyPageHeader from './anomalies/AnomalyPageHeader';
import BaselineContextSection from './anomalies/BaselineContextSection';
import AlertList from './anomalies/AlertList';
import './anomalies/alert-centre.css';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'];
const EMPTY_FILTERS = { plant_id: null, start_date: '', end_date: '' };

function getAlerts(data) {
  const sources = [
    ['Statistical energy', data?.statistical_zscore?.anomalies],
    ['Rolling baseline', data?.rolling_baseline?.anomalies],
    ['Power factor', data?.low_power_factor?.anomalies],
    ['Zero-production standby', data?.zero_production_standby?.anomalies],
  ];

  return sources.flatMap(([source, anomalies]) =>
    (Array.isArray(anomalies) ? anomalies : []).map((anomaly, index) => ({
      ...anomaly,
      source,
      alertKey: `${source}-${anomaly.timestamp}-${anomaly.plant_id}-${anomaly.meter_id || anomaly.line_id || ''}-${index}`,
    }))
  );
}

export default function AnomalyMonitoring() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [anomalyData, setAnomalyData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const loadAnomalyData = useCallback(async (nextFilters, isRefresh = false) => {
    if (nextFilters.start_date && nextFilters.end_date && nextFilters.start_date > nextFilters.end_date) {
      setError('Start date must be on or before end date.');
      return;
    }

    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    const params = {};
    if (nextFilters.plant_id) params.plant_id = nextFilters.plant_id;
    if (nextFilters.start_date) params.start_time = `${nextFilters.start_date}T00:00:00`;
    if (nextFilters.end_date) params.end_time = `${nextFilters.end_date}T23:59:59`;

    try {
      const result = await anomalyApi.getAllAnomalies(params);
      setAnomalyData(result);
      setAppliedFilters(nextFilters);
      setLastRefreshed(new Date());
    } catch (err) {
      console.warn('Anomaly Monitoring data load issue:', err?.message || err);
      setError(err.message || 'Unable to load alert data. Verify the backend connection and try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadAnomalyData(EMPTY_FILTERS);
  }, [loadAnomalyData]);

  const alerts = useMemo(() => getAlerts(anomalyData), [anomalyData]);
  const categoryOptions = useMemo(
    () => [...new Set(alerts.map((alert) => alert.anomaly_type).filter(Boolean))].sort(),
    [alerts]
  );
  const severityCounts = useMemo(() => {
    const counts = Object.fromEntries(SEVERITIES.map((severity) => [severity, 0]));
    alerts.forEach((alert) => {
      if (Object.prototype.hasOwnProperty.call(counts, alert.severity)) {
        counts[alert.severity] += 1;
      }
    });
    return counts;
  }, [alerts]);

  const visibleAlerts = useMemo(() => {
    const searchTerm = search.trim().toLowerCase();
    return alerts.filter((alert) => {
      if (severityFilter !== 'ALL' && alert.severity !== severityFilter) return false;
      if (categoryFilter !== 'ALL' && alert.anomaly_type !== categoryFilter) return false;
      if (!searchTerm) return true;
      return [
        alert.plant_id,
        alert.meter_id,
        alert.line_id,
        alert.anomaly_type,
        alert.source,
        alert.explanation,
      ].some((value) => String(value || '').toLowerCase().includes(searchTerm));
    }).sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')));
  }, [alerts, categoryFilter, search, severityFilter]);

  const handleApplyFilters = (event) => {
    event.preventDefault();
    if (filters.start_date && filters.end_date && filters.start_date > filters.end_date) {
      setError('Start date must be on or before end date.');
      return;
    }
    loadAnomalyData(filters);
  };

  const handleRefresh = () => loadAnomalyData(appliedFilters, true);

  const dateRange = anomalyData?.analysis_period?.start_time && anomalyData?.analysis_period?.end_time
    ? {
      start_date: anomalyData.analysis_period.start_time.slice(0, 10),
      end_date: anomalyData.analysis_period.end_time.slice(0, 10),
    }
    : 'All available dates';

  return (
    <div className="dashboard-container alert-centre-page">
      <AnomalyPageHeader
        filters={filters}
        onChangeFilters={setFilters}
        onApplyFilters={handleApplyFilters}
        dateRange={dateRange}
        evaluationPeriod={anomalyData?.statistical_zscore?.evaluation_period || anomalyData?.analysis_period}
        baselinePeriod={anomalyData?.statistical_zscore?.baseline_period}
        lastRefreshed={lastRefreshed}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      {error && (
        <div className="alert-centre-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => loadAnomalyData(appliedFilters)} disabled={loading || refreshing}>
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="alert-centre-state" role="status">
          <span className="loading-spinner" />
          <strong>Loading alerts</strong>
          <span>Retrieving current anomaly results.</span>
        </div>
      ) : !error && (
        <>
          <section className="alert-summary" aria-label="Alert counts by severity">
            <button
              type="button"
              className={`alert-summary-card total ${severityFilter === 'ALL' ? 'selected' : ''}`}
              onClick={() => setSeverityFilter('ALL')}
              aria-pressed={severityFilter === 'ALL'}
            >
              <span className="summary-label">Total detector flags</span>
              <strong>{alerts.length.toLocaleString('en-IN')}</strong>
            </button>
            {SEVERITIES.map((severity) => (
              <button
                type="button"
                key={severity}
                className={`alert-summary-card ${severity.toLowerCase()} ${severityFilter === severity ? 'selected' : ''}`}
                onClick={() => setSeverityFilter((current) => current === severity ? 'ALL' : severity)}
                aria-pressed={severityFilter === severity}
              >
                <span className="summary-label">{severity.toLowerCase()}</span>
                <strong>{severityCounts[severity].toLocaleString('en-IN')}</strong>
              </button>
            ))}
          </section>

          {/* Historical Baseline Surveillance & Diagnostic Context */}
          <BaselineContextSection
            statisticalData={anomalyData?.statistical_zscore}
            rollingData={anomalyData?.rolling_baseline}
            analysisPeriod={anomalyData?.analysis_period}
          />

          <section className="alert-list-panel" aria-label="Alert list" aria-busy={loading}>
            <div className="alert-list-toolbar">
              <div>
                <h2>Detector flags</h2>
                <span>{visibleAlerts.length.toLocaleString('en-IN')} shown · {alerts.length.toLocaleString('en-IN')} detector flags returned</span>
              </div>
              <div className="alert-list-filters">
                <label>
                  <span className="visually-hidden">Filter by category</span>
                  <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                    <option value="ALL">All categories</option>
                    {categoryOptions.map((category) => (
                      <option key={category} value={category}>{category.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="visually-hidden">Search alerts</span>
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search plant, meter, line, or alert"
                  />
                </label>
              </div>
            </div>

            {visibleAlerts.length > 0 ? (
              <AlertList alerts={visibleAlerts} />
            ) : (
              <div className="alert-centre-empty" role="status">
                <strong>{alerts.length ? 'No alerts match these filters' : 'No alerts in this period'}</strong>
                <span>{alerts.length ? 'Adjust the severity, category, or search filters.' : 'No anomaly records were returned by the selected detectors.'}</span>
              </div>
            )}
          </section>
          <p className="alert-centre-disclaimer">
            Detector flags identify measurements for review; flags from different detectors may overlap and do not confirm equipment faults or root causes.
          </p>
        </>
      )}
    </div>
  );
}
