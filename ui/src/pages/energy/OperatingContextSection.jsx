import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { operatingContextApi } from '../../services';
import { formatCurrency, formatDate, formatDateTime, formatNumber } from '../../utils/formatters';

const LINES = [
  { id: 'ALL', label: 'All Production Lines' },
  { id: 'SMT-L1', label: 'SMT-L1 (Chennai - SMT)', plant: 'IN-TN-01', process: 'SMT', meter: 'MTR-SMT' },
  { id: 'SMT-L2', label: 'SMT-L2 (Bengaluru - SMT)', plant: 'IN-KA-01', process: 'SMT', meter: 'MTR-SMT' },
  { id: 'FAL-L1', label: 'FAL-L1 (Chennai - Final Assembly)', plant: 'IN-TN-01', process: 'Final Assembly', meter: 'MTR-FAL' },
  { id: 'FAL-L2', label: 'FAL-L2 (Bengaluru - Final Assembly)', plant: 'IN-KA-01', process: 'Final Assembly', meter: 'MTR-FAL' },
];

export default function OperatingContextSection({
  selectedPlant = null,
  dateRange = null,
  initialLineId = null,
  initialEpisodeId = null,
}) {
  const [selectedLine, setSelectedLine] = useState(initialLineId || 'ALL');
  const [selectedReason, setSelectedReason] = useState('ALL');
  const [minDuration, setMinDuration] = useState(1);

  const [activeView, setActiveView] = useState('stoppages'); // 'stoppages' | 'utilities'
  const [utilityData, setUtilityData] = useState(null);
  const [utilityLoading, setUtilityLoading] = useState(false);
  const [utilityError, setUtilityError] = useState(null);
  const [selectedUtilityType, setSelectedUtilityType] = useState('COMPRESSED_AIR');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [episodes, setEpisodes] = useState([]);

  // Detail Modal / Drawer state
  const [selectedEpisodeId, setSelectedEpisodeId] = useState(initialEpisodeId || null);
  const [episodeDetail, setEpisodeDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  // Sync initial props
  useEffect(() => {
    if (initialLineId) setSelectedLine(initialLineId);
  }, [initialLineId]);

  useEffect(() => {
    if (initialEpisodeId) setSelectedEpisodeId(initialEpisodeId);
  }, [initialEpisodeId]);

  // Load summary and episodes
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = {
      ...(selectedPlant ? { plant_id: selectedPlant } : {}),
      ...(selectedLine !== 'ALL' ? { line_id: selectedLine } : {}),
      ...(dateRange?.startDate ? { start_date: dateRange.startDate } : {}),
      ...(dateRange?.endDate ? { end_date: dateRange.endDate } : {}),
      min_duration_hours: minDuration,
      ...(selectedReason !== 'ALL' ? { downtime_reason: selectedReason } : {}),
    };

    try {
      const [sumRes, epRes] = await Promise.all([
        operatingContextApi.getSummary({
          ...(selectedPlant ? { plant_id: selectedPlant } : {}),
          ...(selectedLine !== 'ALL' ? { line_id: selectedLine } : {}),
          ...(dateRange?.startDate ? { start_date: dateRange.startDate } : {}),
          ...(dateRange?.endDate ? { end_date: dateRange.endDate } : {}),
        }),
        operatingContextApi.getStoppages(params),
      ]);

      setSummary(sumRes);
      setEpisodes(epRes.episodes || []);
    } catch (err) {
      setError(err?.message || 'Failed to load operating context.');
    } finally {
      setLoading(false);
    }
  }, [selectedPlant, selectedLine, dateRange, minDuration, selectedReason]);

  const loadUtilities = useCallback(async () => {
    setUtilityLoading(true);
    setUtilityError(null);
    try {
      const res = await operatingContextApi.getUtilities({
        plant_id: selectedPlant || 'IN-TN-01',
        ...(selectedUtilityType !== 'ALL' ? { utility_type: selectedUtilityType } : {}),
        ...(dateRange?.startDate ? { start_time: `${dateRange.startDate}T00:00:00` } : {}),
        ...(dateRange?.endDate ? { end_time: `${dateRange.endDate}T23:59:59` } : {}),
        limit: 50,
      });
      setUtilityData(res);
    } catch (err) {
      setUtilityError(err?.message || 'Failed to load utility telemetry observations.');
    } finally {
      setUtilityLoading(false);
    }
  }, [selectedPlant, selectedUtilityType, dateRange]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (activeView === 'utilities') {
      loadUtilities();
    }
  }, [activeView, loadUtilities]);

  // Load detail when selectedEpisodeId changes
  useEffect(() => {
    if (!selectedEpisodeId) {
      setEpisodeDetail(null);
      return;
    }

    let isMounted = true;
    setDetailLoading(true);
    setDetailError(null);

    operatingContextApi
      .getStoppageDetail(selectedEpisodeId)
      .then((res) => {
        if (isMounted) setEpisodeDetail(res);
      })
      .catch((err) => {
        if (isMounted) setDetailError(err?.message || 'Failed to load episode detail.');
      })
      .finally(() => {
        if (isMounted) setDetailLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedEpisodeId]);

  // Available downtime reasons across loaded episodes
  const availableReasons = useMemo(() => {
    const reasons = new Set();
    episodes.forEach((ep) => {
      (ep.downtime_reasons || []).forEach((r) => {
        if (r && r !== 'NONE') reasons.add(r);
      });
    });
    return Array.from(reasons).sort();
  }, [episodes]);

  // Filtered lines according to plant selection
  const visibleLines = useMemo(() => {
    if (!selectedPlant) return LINES;
    return LINES.filter((l) => l.id === 'ALL' || l.plant === selectedPlant);
  }, [selectedPlant]);

  return (
    <div className="energy-card operating-context-section chart-card" style={{ marginTop: '1.5rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius-md, 8px)', padding: '1.25rem', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-sm)' }}>
      {/* 1. Header & Controls */}
      <div className="energy-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
            <span className="badge badge-purple" style={{ textTransform: 'uppercase', fontSize: '0.72rem', letterSpacing: '0.05em' }}>
              Phase 3 • Operating Context
            </span>
            <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Operating Context & Line Stoppage Analysis
            </h3>
          </div>
          <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            Examine line electricity alongside production output. Inspect stoppage episodes, observed restart conditions, and descriptive historical comparisons.
          </p>
        </div>

        {/* Filter Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Line Selector */}
          <div>
            <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
              Production Line
            </label>
            <select
              className="form-select form-select-sm"
              style={{ minWidth: '160px', backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-primary)', borderColor: 'var(--border-color)' }}
              value={selectedLine}
              onChange={(e) => setSelectedLine(e.target.value)}
            >
              {visibleLines.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          {/* Downtime Reason Filter */}
          <div>
            <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
              Downtime Reason
            </label>
            <select
              className="form-select form-select-sm"
              style={{ minWidth: '140px', backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-primary)', borderColor: 'var(--border-color)' }}
              value={selectedReason}
              onChange={(e) => setSelectedReason(e.target.value)}
            >
              <option value="ALL">All Reasons</option>
              <option value="NONE">NONE (Standard / Idle)</option>
              {availableReasons.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {/* Min Duration Filter */}
          <div>
            <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
              Min Duration
            </label>
            <select
              className="form-select form-select-sm"
              style={{ minWidth: '100px', backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-primary)', borderColor: 'var(--border-color)' }}
              value={minDuration}
              onChange={(e) => setMinDuration(Number(e.target.value))}
            >
              <option value={1}>≥ 1 hour</option>
              <option value={2}>≥ 2 hours</option>
              <option value={3}>≥ 3 hours</option>
            </select>
          </div>
        </div>

        {/* View Toggle Tabs */}
        <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.85rem', width: '100%' }}>
          <button
            type="button"
            onClick={() => setActiveView('stoppages')}
            style={{
              padding: '0.35rem 0.85rem',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              background: activeView === 'stoppages' ? 'var(--brand-purple)' : 'var(--bg-surface-subtle)',
              color: activeView === 'stoppages' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
            }}
          >
            Line Stoppage Analysis
          </button>
          <button
            type="button"
            onClick={() => setActiveView('utilities')}
            style={{
              padding: '0.35rem 0.85rem',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              background: activeView === 'utilities' ? 'var(--brand-purple)' : 'var(--bg-surface-subtle)',
              color: activeView === 'utilities' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
            }}
          >
            Utility Telemetry &amp; Compressed Air Quality
          </button>
        </div>
      </div>

      {activeView === 'utilities' ? (
        /* ---------------- UTILITY TELEMETRY VIEW ---------------- */
        <div style={{ marginTop: '1.25rem' }}>
          {/* Utility Selector Controls */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Qualified Utility Telemetry &amp; Delivery Measurements
              </h4>
              <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Distinguishes compressor electricity (MTR-COMPRESSOR in fact_energy_meter_hourly) from pneumatic delivery in fact_utility_telemetry_hourly.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Utility Type:</label>
              <select
                className="form-select form-select-sm"
                value={selectedUtilityType}
                onChange={(e) => setSelectedUtilityType(e.target.value)}
                style={{ backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-primary)', borderColor: 'var(--border-color)', fontSize: '0.75rem' }}
              >
                <option value="COMPRESSED_AIR">Compressed Air (COMPRESSED_AIR)</option>
                <option value="CHILLED_WATER">Chilled Water (CHILLED_WATER)</option>
                <option value="HVAC">HVAC</option>
                <option value="NITROGEN">Nitrogen (NITROGEN)</option>
                <option value="PROCESS_WATER">Process Water (PROCESS_WATER)</option>
                <option value="ALL">All Utilities</option>
              </select>
              <button
                type="button"
                onClick={loadUtilities}
                className="btn btn-sm"
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem', background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '4px', cursor: 'pointer', color: 'var(--text-secondary)' }}
              >
                Refresh
              </button>
            </div>
          </div>

          {utilityLoading && (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              Loading utility telemetry observations…
            </div>
          )}

          {utilityError && (
            <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '6px', color: 'var(--status-danger, #ef4444)', fontSize: '0.82rem', marginBottom: '1rem' }}>
              {utilityError}
            </div>
          )}

          {!utilityLoading && !utilityError && utilityData && (
            <>
              {/* Utility Metric Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.85rem', marginBottom: '1.25rem' }}>
                <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--brand-purple)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
                    MTR-COMPRESSOR Electricity (Input)
                  </div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                    {utilityData.compressor_electrical_consumption_kwh !== null
                      ? `${formatNumber(utilityData.compressor_electrical_consumption_kwh, 2)} kWh`
                      : 'N/A for Selected Range'}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                    {utilityData.compressor_electricity_label || 'Compressor electricity consumption (kWh)'} — electrical motor input distinct from delivery.
                  </div>
                </div>

                <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--brand-blue)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
                    Pneumatic Delivery Flow
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
                    <span style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>Raw Readings</span>
                    <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.5rem', borderRadius: '4px', background: 'rgba(245, 138, 58, 0.15)', color: 'var(--status-warning, #f58a3a)', fontWeight: 600 }}>
                      Flow-rate unit unverified
                    </span>
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                    Source metadata does not establish unit/basis. Derived volume, leak rate, and monetary savings: <strong>null</strong>.
                  </div>
                </div>

                <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--status-success, #10b981)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
                    Header Pressure &amp; Alarms
                  </div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 700, color: 'var(--status-success, #10b981)', marginTop: '0.25rem' }}>
                    Valid Pressure (bar)
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                    Observed header bar readings and recorded equipment alarm codes exposed directly.
                  </div>
                </div>
              </div>

              {/* Ultrasonic Leak-Check Recommendation Box */}
              {utilityData.leak_check_recommendation && (
                <div
                  style={{
                    background: utilityData.leak_check_recommendation.warrants_investigation ? 'rgba(245, 138, 58, 0.08)' : 'var(--bg-surface-subtle)',
                    border: `1px solid ${utilityData.leak_check_recommendation.warrants_investigation ? 'var(--status-warning, #f58a3a)' : 'var(--border-color)'}`,
                    borderRadius: '8px',
                    padding: '1rem',
                    marginBottom: '1.25rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        Leak-Check Recommendation: {utilityData.leak_check_recommendation.warrants_investigation ? 'Investigation Warranted' : 'Nominal Conditions'}
                      </span>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          fontWeight: 600,
                          background: utilityData.leak_check_recommendation.warrants_investigation ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                          color: utilityData.leak_check_recommendation.warrants_investigation ? 'var(--status-danger, #ef4444)' : 'var(--status-success, #10b981)',
                        }}
                      >
                        {utilityData.leak_check_recommendation.quantification_status}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Window: {utilityData.leak_check_recommendation.time_window}
                    </span>
                  </div>

                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '0.5rem' }}>
                    <strong>Evidence:</strong> {utilityData.leak_check_recommendation.evidence}<br />
                    <strong>Operator Question:</strong> <em>{utilityData.leak_check_recommendation.operator_question}</em>
                  </div>

                  <div style={{ background: 'var(--bg-surface)', padding: '0.75rem', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.76rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                      Defensible Investigation Method: Ultrasonic Acoustic Inspection
                    </div>
                    <div>{utilityData.leak_check_recommendation.suggested_investigation_method}</div>
                    <div style={{ marginTop: '0.35rem', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                      <em>Note on Quantification:</em> {utilityData.leak_check_recommendation.quantification_reason}
                    </div>
                  </div>
                </div>
              )}

              {/* Utility Telemetry Table */}
              <div style={{ border: '1px solid var(--border-color)', borderRadius: '6px', overflow: 'hidden' }}>
                <div style={{ padding: '0.6rem 0.85rem', background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Hourly Utility Observations ({utilityData.records?.length || 0} readings)
                  </span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Plant: {utilityData.plant_id} • Units Recorded: {utilityData.distinct_recorded_units?.join(', ') || 'None'}
                  </span>
                </div>
                <div style={{ overflowX: 'auto', width: '100%' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.76rem', textAlign: 'left', color: 'var(--text-secondary)' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Timestamp</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Utility</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Equipment</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Zone</th>
                        <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>Flow Rate</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Flow Unit Status</th>
                        <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>Pressure (bar)</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Status</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Alarm</th>
                        <th style={{ padding: '0.5rem 0.75rem' }}>Source ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(utilityData.records || []).map((row, idx) => (
                        <tr key={row.utility_reading_id || idx} style={{ borderBottom: '1px solid var(--border-color)', background: idx % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-surface-subtle)' }}>
                          <td style={{ padding: '0.45rem 0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            {formatDateTime(row.timestamp)}
                          </td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>{row.utility_type}</td>
                          <td style={{ padding: '0.45rem 0.75rem', fontWeight: 500 }}>{row.equipment_id}</td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>{row.zone}</td>
                          <td style={{ padding: '0.45rem 0.75rem', textAlign: 'right', fontWeight: 600, color: 'var(--brand-blue)' }}>
                            {row.flow_rate !== null ? formatNumber(row.flow_rate, 2) : '—'}
                          </td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>
                            <span style={{ fontSize: '0.68rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(245, 138, 58, 0.12)', color: 'var(--status-warning, #f58a3a)' }}>
                              Flow-rate unit unverified
                            </span>
                          </td>
                          <td style={{ padding: '0.45rem 0.75rem', textAlign: 'right', fontWeight: 600, color: row.pressure_bar < 6.0 ? 'var(--status-danger, #ef4444)' : 'var(--text-primary)' }}>
                            {row.pressure_bar !== null ? `${formatNumber(row.pressure_bar, 2)} bar` : '—'}
                          </td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>{row.operating_status}</td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>
                            {row.alarm_code && row.alarm_code !== 'NONE' ? (
                              <span style={{ fontSize: '0.68rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(239, 68, 68, 0.15)', color: 'var(--status-danger, #ef4444)', fontWeight: 600 }}>
                                {row.alarm_code}
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>NONE</span>
                            )}
                          </td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>
                            <code style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{row.source_id}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      ) : (
        /* ---------------- STOPPAGES VIEW ---------------- */
        <>

      {/* 2. Headline Observation & Coverage KPIs */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.85rem', margin: '1.25rem 0' }}>
          {/* Card A: Telemetry Coverage */}
          <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Observation Coverage
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#38bdf8', marginTop: '0.25rem' }}>
              {formatNumber(summary.matched_hours, 0)} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>/ {formatNumber(summary.total_observed_hours, 0)} hrs</span>
            </div>
            <div style={{ fontSize: '0.75rem', marginTop: '0.35rem', color: summary.missing_energy_hours === 0 && summary.missing_production_hours === 0 ? 'var(--status-success, #22c55e)' : 'var(--status-warning, #eab308)' }}>
              {summary.missing_energy_hours === 0 && summary.missing_production_hours === 0
                ? '● 100% Complete Observation Match'
                : `Missing: ${summary.missing_energy_hours} energy, ${summary.missing_production_hours} production`}
            </div>
          </div>

          {/* Card B: Detected Stoppage Episodes */}
          <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Stoppage Episodes
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f59e0b', marginTop: '0.25rem' }}>
              {formatNumber(summary.stoppage_episode_count, 0)} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>episodes</span>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
              Total Stoppage Time: <strong style={{ color: 'var(--text-primary)' }}>{formatNumber(summary.total_stoppage_hours, 0)} hours</strong>
            </div>
          </div>

          {/* Card C: Target Production Lost */}
          <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Target Output Lost
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--status-danger, #ef4444)', marginTop: '0.25rem' }}>
              {formatNumber(summary.total_target_lost, 0)} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>units</span>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
              Observed Output: <strong style={{ color: 'var(--status-success, #22c55e)' }}>0 actual units</strong> during stoppage
            </div>
          </div>

          {/* Card D: Standby Electricity Consumed */}
          <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.9rem' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Standby Process Electricity
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#a855f7', marginTop: '0.25rem' }}>
              {formatNumber(summary.total_stoppage_kwh, 2)} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>kWh</span>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
              Dedicated process meters (MTR-SMT / MTR-FAL)
            </div>
          </div>
        </div>
      )}

      {/* 3. Stoppage Episodes Table */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
          <div className="spinner-border text-primary" role="status" style={{ marginBottom: '0.5rem' }} />
          <div>Scanning and calculating operating stoppage episodes...</div>
        </div>
      ) : error ? (
        <div className="alert alert-danger" style={{ margin: '1rem 0' }}>
          {error}
        </div>
      ) : episodes.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)', background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
          Zero stoppage episodes found matching the selected line and filter criteria.
        </div>
      ) : (
        <div className="table-responsive" style={{ maxHeight: '450px', overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: '8px', background: 'var(--bg-surface)' }}>
          <table className="table table-hover table-sm" style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            <thead style={{ position: 'sticky', top: 0, backgroundColor: 'var(--bg-surface-subtle)', zIndex: 2, borderBottom: '2px solid var(--border-color)', color: 'var(--text-primary)' }}>
              <tr>
                <th>Episode ID</th>
                <th>Plant / Line</th>
                <th>Interval Window</th>
                <th style={{ textAlign: 'right' }}>Duration</th>
                <th style={{ textAlign: 'right' }}>Target Shortfall during Observed Hours</th>
                <th style={{ textAlign: 'center' }}>Observed Output</th>
                <th style={{ textAlign: 'right' }}>Process kWh</th>
                <th style={{ textAlign: 'right' }}>Dataset Cost</th>
                <th>Downtime Reasons</th>
                <th>Restart Condition</th>
                <th style={{ textAlign: 'center' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {episodes.map((ep) => {
                const isSelected = selectedEpisodeId === ep.episode_id;
                return (
                  <tr
                    key={ep.episode_id}
                    style={{
                      backgroundColor: isSelected ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedEpisodeId(ep.episode_id)}
                  >
                    <td>
                      <code style={{ color: 'var(--brand-blue, #38bdf8)', fontSize: '0.74rem' }}>{ep.episode_id}</code>
                    </td>
                    <td>
                      <div>
                        <strong style={{ color: 'var(--text-primary)' }}>{ep.line_id}</strong>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: '0.35rem' }}>({ep.plant_id})</span>
                      </div>
                      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{ep.process}</div>
                    </td>
                    <td>
                      <div style={{ color: 'var(--text-primary)' }}>{formatDateTime(ep.first_interval)}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--brand-blue, #38bdf8)', fontFamily: 'monospace' }}>
                        {ep.interval_window || `to ${formatDateTime(ep.last_interval)}`}
                      </div>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="badge badge-secondary" style={{ fontSize: '0.72rem' }}>
                        {ep.observed_duration_hours} hr{ep.observed_duration_hours > 1 ? 's' : ''}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--status-danger, #ef4444)' }}>
                      {formatNumber(ep.target_shortfall ?? ep.target_qty_lost, 0)} units
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                        0 actual (verified)
                      </span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--brand-purple, #a855f7)' }}>
                      {ep.process_kwh !== null ? `${formatNumber(ep.process_kwh, 2)} kWh` : '—'}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--brand-blue, #38bdf8)' }}>
                      {ep.process_cost_inr !== null ? formatCurrency(ep.process_cost_inr) : '—'}
                    </td>
                    <td>
                      {(ep.downtime_reasons_display || ep.downtime_reasons)?.map((r, i) => (
                        <span key={i} className="badge badge-outline" style={{ fontSize: '0.68rem', marginRight: '0.25rem', borderColor: 'var(--border-color)', color: 'var(--text-secondary)' }}>
                          {r === 'NONE' ? 'Reason unspecified' : r}
                        </span>
                      ))}
                    </td>
                    <td>
                      {ep.next_restart_interval ? (
                        <div style={{ fontSize: '0.72rem', color: 'var(--status-success, #10b981)' }}>
                          ✓ Output resumed ({formatNumber(ep.next_restart_interval.actual_qty, 0)} units, {formatNumber(ep.next_restart_interval.consumption_kwh, 2)} kWh)
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          No immediate restart recorded
                        </div>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-outline-primary btn-sm"
                        style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedEpisodeId(ep.episode_id);
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 4. Episode Detail Inspection Drawer / Modal */}
      {selectedEpisodeId && (
        <div
          style={{
            marginTop: '1.5rem',
            background: 'var(--bg-surface)',
            border: '2px solid var(--brand-blue)',
            borderRadius: '10px',
            padding: '1.25rem',
            position: 'relative',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          {/* Close button */}
          <button
            type="button"
            className="btn-close"
            style={{ position: 'absolute', top: '1rem', right: '1rem', zIndex: 10 }}
            onClick={() => setSelectedEpisodeId(null)}
            aria-label="Close detail view"
          />

          {detailLoading ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
              <div className="spinner-border text-info" role="status" style={{ marginBottom: '0.5rem' }} />
              <div>Loading detailed episode context and historical comparison...</div>
            </div>
          ) : detailError ? (
            <div className="alert alert-danger">{detailError}</div>
          ) : episodeDetail ? (
            <div>
              {/* Detail Header */}
              <div style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '0.85rem', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                  <span className="badge badge-primary" style={{ fontSize: '0.75rem' }}>
                    Episode Inspection
                  </span>
                  <code style={{ fontSize: '0.9rem', color: 'var(--brand-blue)', fontWeight: 700 }}>
                    {episodeDetail.episode.episode_id}
                  </code>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Line: <strong>{episodeDetail.episode.line_id}</strong> • Plant: <strong>{episodeDetail.episode.plant_id}</strong> ({episodeDetail.episode.process})
                  </span>
                </div>
              </div>

              {/* Chronological Lifecycle: Before -> Stoppage -> Restart */}
              <div style={{ marginBottom: '1.25rem' }}>
                <h4 style={{ fontSize: '0.88rem', color: 'var(--text-primary)', margin: '0 0 0.75rem 0', fontWeight: 600 }}>
                  Chronological Operating Lifecycle (Before → Stoppage → Restart)
                </h4>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                  {/* Phase 1: Prior Productive Hour */}
                  <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.85rem' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--brand-blue)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '0.4rem' }}>
                      1. Prior Productive Interval
                    </div>
                    {episodeDetail.episode.prior_productive_interval ? (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        <div>Timestamp: <strong style={{ color: 'var(--text-primary)' }}>{formatDateTime(episodeDetail.episode.prior_productive_interval.timestamp)}</strong></div>
                        <div style={{ marginTop: '0.25rem' }}>
                          Actual Output: <strong style={{ color: 'var(--status-success, #22c55e)' }}>{formatNumber(episodeDetail.episode.prior_productive_interval.actual_qty, 0)} units</strong> ({formatNumber(episodeDetail.episode.prior_productive_interval.good_qty, 0)} good, {formatNumber(episodeDetail.episode.prior_productive_interval.reject_qty, 0)} rejects)
                        </div>
                        <div style={{ marginTop: '0.25rem' }}>
                          Process Electricity: <strong style={{ color: 'var(--brand-purple, #a855f7)' }}>{formatNumber(episodeDetail.episode.prior_productive_interval.consumption_kwh, 2)} kWh</strong> ({formatCurrency(episodeDetail.episode.prior_productive_interval.cost_inr)})
                        </div>
                        <div style={{ marginTop: '0.25rem', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          Downtime: {episodeDetail.episode.prior_productive_interval.downtime_min} min ({episodeDetail.episode.prior_productive_interval.downtime_reason || 'NONE'})
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>No prior productive interval recorded in dataset window.</div>
                    )}
                  </div>

                  {/* Phase 2: Stoppage Episode Summary */}
                  <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--status-warning, #eab308)', borderRadius: '6px', padding: '0.85rem' }}>
                    <div style={{ fontSize: '0.72rem', color: '#eab308', textTransform: 'uppercase', fontWeight: 700, marginBottom: '0.4rem' }}>
                      2. Stoppage Period ({episodeDetail.episode.observed_duration_hours} hr{episodeDetail.episode.observed_duration_hours > 1 ? 's' : ''})
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      <div>Duration: <strong style={{ color: 'var(--text-primary)' }}>{episodeDetail.episode.interval_window || `${formatDateTime(episodeDetail.episode.first_interval)} → ${formatDateTime(episodeDetail.episode.last_interval)}`}</strong></div>
                      <div style={{ marginTop: '0.25rem' }}>
                        Target Shortfall during Observed Hours: <strong style={{ color: 'var(--status-danger, #ef4444)' }}>{formatNumber(episodeDetail.episode.target_shortfall ?? episodeDetail.episode.target_qty_lost, 0)} units</strong>
                      </div>
                      <div style={{ marginTop: '0.25rem' }}>
                        Observed Production: <strong style={{ color: 'var(--status-success, #22c55e)' }}>0 actual units</strong> ({episodeDetail.episode.recorded_downtime_minutes} min recorded downtime, {episodeDetail.episode.downtime_reasons_display?.join(', ') || 'Reason unspecified'})
                      </div>
                      <div style={{ marginTop: '0.25rem' }}>
                        {episodeDetail.episode.process_electricity_label || "Process electricity during zero-output hours"}: <strong style={{ color: 'var(--brand-purple, #a855f7)' }}>{formatNumber(episodeDetail.episode.process_kwh, 2)} kWh</strong> ({formatCurrency(episodeDetail.episode.process_cost_inr)})
                      </div>
                      <div style={{ marginTop: '0.25rem', fontSize: '0.7rem', color: '#eab308' }}>
                        Energy Coverage: {episodeDetail.episode.energy_coverage_pct}% Complete
                      </div>
                    </div>
                  </div>

                  {/* Phase 3: Restart Interval */}
                  <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.85rem' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--status-success, #22c55e)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '0.4rem' }}>
                      3. Next Restart Interval
                    </div>
                    {episodeDetail.episode.next_restart_interval ? (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        <div>Timestamp: <strong style={{ color: 'var(--text-primary)' }}>{formatDateTime(episodeDetail.episode.next_restart_interval.timestamp)}</strong></div>
                        <div style={{ marginTop: '0.25rem' }}>
                          Resumed Output: <strong style={{ color: 'var(--status-success, #22c55e)' }}>{formatNumber(episodeDetail.episode.next_restart_interval.actual_qty, 0)} units</strong> ({formatNumber(episodeDetail.episode.next_restart_interval.good_qty, 0)} good, {formatNumber(episodeDetail.episode.next_restart_interval.reject_qty, 0)} rejects)
                        </div>
                        <div style={{ marginTop: '0.25rem' }}>
                          Process Electricity: <strong style={{ color: 'var(--brand-purple, #a855f7)' }}>{formatNumber(episodeDetail.episode.next_restart_interval.consumption_kwh, 2)} kWh</strong> ({formatCurrency(episodeDetail.episode.next_restart_interval.cost_inr)})
                        </div>
                        <div style={{ marginTop: '0.25rem', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          Downtime: {episodeDetail.episode.next_restart_interval.downtime_min} min ({episodeDetail.episode.next_restart_interval.downtime_reason || 'NONE'})
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Zero or unobserved restart output immediately following stoppage.</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Hour-by-Hour Constituent Readings Table */}
              <div style={{ marginBottom: '1.25rem' }}>
                <h4 style={{ fontSize: '0.84rem', color: 'var(--text-primary)', margin: '0 0 0.5rem 0', fontWeight: 600 }}>
                  Constituent Hourly Readings during Stoppage
                </h4>
                <div className="table-responsive" style={{ border: '1px solid var(--border-color)', borderRadius: '6px' }}>
                  <table className="table table-hover table-sm" style={{ margin: 0, fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                    <thead>
                      <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)' }}>
                        <th>Hour / Time</th>
                        <th>Shift</th>
                        <th style={{ textAlign: 'right' }}>Target Lost</th>
                        <th style={{ textAlign: 'center' }}>Actual / Good</th>
                        <th style={{ textAlign: 'right' }}>Downtime</th>
                        <th>Downtime Reason</th>
                        <th style={{ textAlign: 'right' }}>Process kWh</th>
                        <th style={{ textAlign: 'right' }}>Cost (INR)</th>
                        <th>Machine States</th>
                        <th>Machine Alarms</th>
                        <th>Source Reading ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {episodeDetail.constituent_hours?.map((h, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                          <td style={{ color: 'var(--text-primary)' }}>{formatDateTime(h.timestamp)}</td>
                          <td>
                            <span className="badge badge-secondary" style={{ fontSize: '0.68rem' }}>
                              {h.shift_name || `Shift ${h.shift_id}`}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right', color: 'var(--status-danger, #ef4444)' }}>{h.target_qty}</td>
                          <td style={{ textAlign: 'center', color: 'var(--status-success, #22c55e)' }}>
                            {h.actual_qty} / {h.good_qty}
                          </td>
                          <td style={{ textAlign: 'right' }}>{h.downtime_min} min</td>
                          <td>
                            <span className="badge badge-outline" style={{ fontSize: '0.68rem', borderColor: 'var(--border-color)', color: 'var(--text-secondary)' }}>
                              {h.downtime_reason || 'NONE'}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right', color: 'var(--brand-purple, #a855f7)', fontWeight: 600 }}>
                            {formatNumber(h.consumption_kwh, 3)}
                          </td>
                          <td style={{ textAlign: 'right', color: 'var(--brand-blue, #38bdf8)' }}>
                            {formatCurrency(h.cost_inr)}
                          </td>
                          <td>
                            {h.machine_states?.length > 0 ? (
                              h.machine_states.map((s, i) => (
                                <span key={i} className="badge badge-warning" style={{ fontSize: '0.65rem', marginRight: '0.2rem' }}>
                                  {s}
                                </span>
                              ))
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>None</span>
                            )}
                          </td>
                          <td>
                            {h.alarm_codes?.length > 0 ? (
                              h.alarm_codes.map((a, i) => (
                                <span key={i} className="badge badge-danger" style={{ fontSize: '0.65rem', marginRight: '0.2rem' }}>
                                  {a}
                                </span>
                              ))
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>None</span>
                            )}
                          </td>
                          <td>
                            <code style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{h.source_reading_id || '—'}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Descriptive Historical Comparison Card */}
              {episodeDetail.similar_periods && (
                <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.6rem' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                      Descriptive Historical Comparison ({episodeDetail.similar_periods.eligible_count} Comparable Stoppages)
                    </div>
                    <span className="badge badge-info" style={{ fontSize: '0.7rem' }}>
                      Strictly Descriptive • No Counterfactual Baselines
                    </span>
                  </div>

                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.85rem' }}>
                    <div>Criteria: <em>{episodeDetail.similar_periods.matching_criteria}</em></div>
                    <div style={{ marginTop: '0.2rem' }}>
                      <span>Baseline: {episodeDetail.similar_periods.historical_window}</span>
                      {episodeDetail.similar_periods.comparison_cutoff && (
                        <span style={{ marginLeft: '0.8rem', color: 'var(--brand-blue)' }}>
                          Comparison Cutoff: {formatDateTime(episodeDetail.similar_periods.comparison_cutoff)}
                        </span>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Current Episode Rate</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--brand-purple, #a855f7)', marginTop: '0.2rem' }}>
                        {formatNumber(episodeDetail.episode.process_kwh / episodeDetail.episode.observed_duration_hours, 2)} <span style={{ fontSize: '0.75rem' }}>kWh/hr</span>
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                        Total: {formatNumber(episodeDetail.episode.process_kwh, 2)} kWh over {episodeDetail.episode.observed_duration_hours}h
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Historical Median Rate</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--brand-blue, #38bdf8)', marginTop: '0.2rem' }}>
                        {episodeDetail.similar_periods.median_kwh_per_hour !== null ? `${formatNumber(episodeDetail.similar_periods.median_kwh_per_hour, 2)} kWh/hr` : '—'}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                        Min: {formatNumber(episodeDetail.similar_periods.min_kwh_per_hour, 2)} • Max: {formatNumber(episodeDetail.similar_periods.max_kwh_per_hour, 2)} kWh/hr
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Historical Duration Norm</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#f59e0b', marginTop: '0.2rem' }}>
                        {episodeDetail.similar_periods.duration_min_hours === episodeDetail.similar_periods.duration_max_hours
                          ? `${episodeDetail.similar_periods.duration_min_hours} hr`
                          : `${episodeDetail.similar_periods.duration_min_hours} – ${episodeDetail.similar_periods.duration_max_hours} hrs`}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                        {episodeDetail.similar_periods.duration_min_hours === episodeDetail.similar_periods.duration_max_hours
                          ? `All ${episodeDetail.similar_periods.eligible_count} earlier episodes were ${episodeDetail.similar_periods.duration_min_hours}h long`
                          : `Range across ${episodeDetail.similar_periods.eligible_count} earlier episodes`}
                        {' • '}Current: {episodeDetail.episode.observed_duration_hours}h
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Common Baseline Reasons</div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.3rem' }}>
                        {(episodeDetail.similar_periods.typical_downtime_reasons_display || episodeDetail.similar_periods.typical_downtime_reasons)?.join(', ') || 'Reason unspecified'}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                        Exclusions: {episodeDetail.similar_periods.excluded_count} ({Object.entries(episodeDetail.similar_periods.excluded_reasons || {}).map(([k, v]) => `${k}: ${v}`).join(', ')})
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Actionable Engineering Investigation (Facilities & Production) */}
              {episodeDetail.actionable_investigation && (
                <div style={{ background: 'var(--bg-surface-subtle)', border: '1px solid var(--status-success, #10b981)', borderRadius: '8px', padding: '1.1rem', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.8rem', flexWrap: 'wrap' }}>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--status-success, #10b981)' }}>
                      Actionable Engineering Investigation (Facilities &amp; Production)
                    </div>
                    <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                      Operational Guidance
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.85rem', marginBottom: '0.85rem' }}>
                    {/* Section 1: Observed Condition */}
                    <div style={{ background: 'var(--bg-surface)', padding: '0.85rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--brand-blue)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.35rem' }}>
                        1. Observed Condition
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                        {episodeDetail.actionable_investigation.observed_condition}
                      </div>
                    </div>

                    {/* Section 2: Comparison & Evidence */}
                    <div style={{ background: 'var(--bg-surface)', padding: '0.85rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                      <div style={{ fontSize: '0.72rem', color: '#f59e0b', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.35rem' }}>
                        2. Comparison &amp; Evidence
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                        {episodeDetail.actionable_investigation.comparison_and_evidence}
                      </div>
                    </div>
                  </div>

                  {/* Section 3: Possible Causes & Limitations */}
                  <div style={{ background: 'var(--bg-surface)', padding: '0.85rem', borderRadius: '6px', border: '1px solid var(--border-color)', marginBottom: '0.85rem' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--brand-purple)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.4rem' }}>
                      3. Possible Causes &amp; Limitations (Labeled Hypotheses)
                    </div>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      {episodeDetail.actionable_investigation.possible_causes_and_limitations?.map((cause, i) => (
                        <li key={i} style={{ marginBottom: '0.25rem' }}>{cause}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Section 4: Suggested Investigation */}
                  <div style={{ background: 'var(--bg-surface)', padding: '0.85rem', borderRadius: '6px', border: '1px solid var(--status-success, #10b981)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--status-success, #10b981)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.4rem' }}>
                      4. Suggested Investigation (Responsible Teams &amp; Boundary Conditions)
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                      <strong style={{ color: 'var(--text-primary)' }}>Responsible Teams:</strong>{' '}
                      {episodeDetail.actionable_investigation.suggested_investigation?.responsible_teams?.map((t, idx) => (
                        <span key={idx} className="badge badge-info" style={{ marginRight: '0.3rem', fontSize: '0.7rem' }}>{t}</span>
                      ))}
                    </div>
                    <div style={{ fontSize: '0.76rem', color: '#f59e0b', background: 'rgba(245, 158, 11, 0.08)', padding: '0.5rem', borderRadius: '4px', marginBottom: '0.4rem', borderLeft: '3px solid #f59e0b' }}>
                      <strong>Condition to check before modifying state:</strong>{' '}
                      {episodeDetail.actionable_investigation.suggested_investigation?.production_condition_to_check}
                    </div>
                    {episodeDetail.actionable_investigation.suggested_investigation?.action_items && (
                      <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                        {episodeDetail.actionable_investigation.suggested_investigation.action_items.map((item, idx) => (
                          <li key={idx} style={{ marginBottom: '0.2rem' }}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}

              {/* Provenance & Source IDs footer */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-color)' }}>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Linked Source IDs: {episodeDetail.episode.source_record_ids?.slice(0, 4).join(', ')}
                  {episodeDetail.episode.source_record_ids?.length > 4 ? ` (+${episodeDetail.episode.source_record_ids.length - 4} more)` : ''}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.75rem' }}
                    onClick={() => setSelectedEpisodeId(null)}
                  >
                    Close Inspection
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
      </>
      )}
    </div>
  );
}
