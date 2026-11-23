import React, { useState, useEffect, useCallback } from 'react';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDateTime, formatCurrency, formatNumber } from '../../utils/formatters';

/**
 * Persistent Savings & Intervention Ledger View (Phase 5).
 * 
 * Displays persistent M&V intervention records, verified avoided quantities,
 * guardrail outcomes, and distinguishes verified claims from estimates and inconclusive cases.
 */
export default function SavingsLedgerSection({ onInspectAction }) {
  const [ledgerData, setLedgerData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [plantFilter, setPlantFilter] = useState('ALL');
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  const loadLedger = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit, offset };
      if (statusFilter !== 'ALL') params.status = statusFilter;
      if (plantFilter !== 'ALL') params.plant_id = plantFilter;

      const res = await recommendationsApi.listSavingsLedger(params);
      setLedgerData(res);
    } catch (err) {
      setError(err.message || 'Failed to load savings ledger.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, plantFilter, limit, offset]);

  useEffect(() => {
    loadLedger();
  }, [loadLedger]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* KPI Cards Row */}
      {ledgerData && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
          <div style={{ padding: '1rem', background: 'var(--bg-surface-elevated)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Ledger Entries</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
              {ledgerData.total_count}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>M&amp;V Interventions evaluated</span>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-surface-elevated)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Verified Interventions</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#22c55e', marginTop: '0.25rem' }}>
              {ledgerData.verified_count}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Passed guardrails &amp; signed off</span>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-surface-elevated)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Verified Avoided Energy</span>
            <div style={{ fontSize: ledgerData.verified_count === 0 ? '1.05rem' : '1.4rem', fontWeight: 700, color: ledgerData.verified_count === 0 ? 'var(--text-muted)' : '#10b981', marginTop: '0.25rem' }}>
              {ledgerData.verified_count === 0 ? 'No verified intervention savings' : `${formatNumber(ledgerData.total_verified_avoided_kwh)} kWh`}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Non-overlapping physical kWh</span>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-surface-elevated)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Estimated Avoided Cost</span>
            <div style={{ fontSize: ledgerData.verified_count === 0 ? '1.05rem' : '1.4rem', fontWeight: 700, color: ledgerData.verified_count === 0 ? 'var(--text-muted)' : '#3b82f6', marginTop: '0.25rem' }}>
              {ledgerData.verified_count === 0 ? 'No verified intervention savings' : formatCurrency(ledgerData.total_estimated_avoided_cost_inr || ledgerData.total_verified_avoided_cost_inr)}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
              {ledgerData.estimated_avoided_cost_assumption || 'Dataset tariff assumption: ₹8.25/kWh'}
            </span>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-surface-elevated)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Verified Monetary Savings</span>
            <div style={{ fontSize: (ledgerData.total_verified_monetary_savings_inr || 0) === 0 ? '1.05rem' : '1.4rem', fontWeight: 700, color: (ledgerData.total_verified_monetary_savings_inr || 0) === 0 ? 'var(--text-muted)' : '#10b981', marginTop: '0.25rem' }}>
              {(ledgerData.total_verified_monetary_savings_inr || 0) > 0 ? formatCurrency(ledgerData.total_verified_monetary_savings_inr) : 'Pending contract approval'}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Requires signed approved contract tariff</span>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-surface-elevated)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Pending / Inconclusive</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#eab308', marginTop: '0.25rem' }}>
              {ledgerData.inconclusive_count}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Awaiting review or coverage</span>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="iac-filter-toolbar" style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Claim Status:</label>
          <select
            className="iac-filter-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="VERIFIED">VERIFIED</option>
            <option value="NOT_VERIFIED">NOT_VERIFIED</option>
            <option value="INCONCLUSIVE">INCONCLUSIVE</option>
            <option value="PENDING_REVIEW">PENDING_REVIEW</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Plant:</label>
          <select
            className="iac-filter-select"
            value={plantFilter}
            onChange={(e) => {
              setPlantFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="ALL">All Plants</option>
            <option value="IN-KA-01">IN-KA-01</option>
            <option value="IN-TN-01">IN-TN-01</option>
          </select>
        </div>

        <button
          type="button"
          className="btn-iac btn-iac-secondary"
          onClick={loadLedger}
          style={{ marginLeft: 'auto' }}
        >
          Refresh Ledger
        </button>
      </div>

      {/* Eligibility Notice when zero verified */}
      {ledgerData && ledgerData.verified_count === 0 && ledgerData.total_count > 0 && (
        <div style={{ padding: '0.75rem 1rem', background: 'rgba(234, 179, 8, 0.1)', border: '1px solid rgba(234, 179, 8, 0.3)', borderRadius: '6px', fontSize: '0.82rem', color: '#eab308' }}>
          <strong>Eligibility Notice:</strong> Out of {ledgerData.total_count} evaluated interventions, {ledgerData.inconclusive_count || ledgerData.total_count} are pending reviewer sign-off, breached guardrails, or have incomplete post-action observation data. Missing or unverified assessments are strictly excluded from zero-savings totals.
        </div>
      )}

      {/* Ledger Table Section */}
      {error ? (
        <div style={{ padding: '1.5rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: '6px', color: '#ef4444' }}>
          <strong>Error loading savings ledger:</strong> {error}
        </div>
      ) : loading ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading persistent savings ledger…
        </div>
      ) : !ledgerData || ledgerData.items.length === 0 ? (
        <div style={{ padding: '2.5rem', textAlign: 'center', background: 'var(--bg-surface-elevated)', borderRadius: '8px' }}>
          <h4 style={{ margin: '0 0 0.5rem' }}>No Eligible Savings Entries in Ledger</h4>
          <p style={{ margin: '0 auto', maxWidth: '640px', fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            No operational interventions currently qualify for verified savings under the selected filters.
            Either no interventions have been implemented with approved M&amp;V plans, or post-intervention observation windows are still accumulating data.
            <br />
            <strong style={{ color: 'var(--text-primary)', marginTop: '0.35rem', display: 'inline-block' }}>
              Missing, inconclusive, or pending assessments are strictly excluded from verified savings totals.
            </strong>
          </p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto', background: 'var(--bg-surface)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <table className="iac-table" style={{ width: '100%', fontSize: '0.85rem' }}>
            <thead>
              <tr>
                <th>Status</th>
                <th>Intervention &amp; Plan</th>
                <th>Objective Outcome</th>
                <th>Intensity Impact</th>
                <th>Verified Electricity Savings</th>
                <th>Estimated &amp; Verified Cost</th>
                <th>Guardrails</th>
                <th>Sign-Off &amp; Reviewer</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {ledgerData.items.map((item) => (
                <tr key={item.assessment_id}>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                      <span
                        className="badge-iac"
                        style={{
                          background:
                            item.savings_claim_status === 'VERIFIED'
                              ? 'rgba(34, 197, 94, 0.15)'
                              : item.savings_claim_status === 'NOT_VERIFIED'
                              ? 'rgba(239, 68, 68, 0.15)'
                              : 'rgba(234, 179, 8, 0.15)',
                          color:
                            item.savings_claim_status === 'VERIFIED'
                              ? '#22c55e'
                              : item.savings_claim_status === 'NOT_VERIFIED'
                              ? '#ef4444'
                              : '#eab308',
                          border: '1px solid currentColor',
                          fontWeight: 700,
                          fontSize: '0.75rem',
                        }}
                      >
                        {item.savings_claim_status}
                      </span>
                      {item.overlap_flag && (
                        <span
                          className="badge-iac"
                          style={{ background: 'rgba(234, 179, 8, 0.1)', color: '#eab308', fontSize: '0.68rem' }}
                          title={item.overlap_details}
                        >
                          Overlap Flagged
                        </span>
                      )}
                      {item.is_stale_flag && (
                        <span className="badge-iac" style={{ background: 'rgba(156, 163, 175, 0.2)', color: '#9ca3af', fontSize: '0.68rem' }}>
                          Stale Rev
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <strong style={{ display: 'block', color: 'var(--text-primary)' }}>{item.action_id}</strong>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Plan: {item.plan_id} (v{item.plan_version} • rev {item.assessment_revision})
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      <span
                        className="badge-iac"
                        style={{
                          fontSize: '0.74rem',
                          fontWeight: 700,
                          width: 'fit-content',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          background:
                            item.management_outcome === 'Verified intervention improvement'
                              ? 'rgba(34, 197, 94, 0.15)'
                              : item.management_outcome === 'Eligible for verification — awaiting reviewer'
                              ? 'rgba(59, 130, 246, 0.15)'
                              : item.management_outcome?.includes('breached') || item.management_outcome?.includes('not met')
                              ? 'rgba(239, 68, 68, 0.15)'
                              : 'rgba(234, 179, 8, 0.15)',
                          color:
                            item.management_outcome === 'Verified intervention improvement'
                              ? '#22c55e'
                              : item.management_outcome === 'Eligible for verification — awaiting reviewer'
                              ? '#3b82f6'
                              : item.management_outcome?.includes('breached') || item.management_outcome?.includes('not met')
                              ? '#ef4444'
                              : '#d97706',
                          border: '1px solid currentColor',
                        }}
                      >
                        {item.management_outcome || item.objective_outcome}
                      </span>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.3 }}>
                        {item.management_outcome_detail || item.status_reason}
                      </div>
                      {item.next_step && (
                        <div style={{ fontSize: '0.7rem', color: '#3b82f6', marginTop: '0.15rem' }}>
                          Next: {item.next_step}
                        </div>
                      )}
                    </div>
                  </td>
                  <td>
                    <div>
                      {item.cost_intensity_change_pct != null ? (
                        <span style={{ fontWeight: 600, color: item.cost_intensity_change_pct <= 0 ? '#22c55e' : '#ef4444' }}>
                          Cost: {item.cost_intensity_change_pct}%
                        </span>
                      ) : (
                        'N/A'
                      )}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      kWh: {item.intensity_change_pct != null ? `${item.intensity_change_pct}%` : 'N/A'}
                    </div>
                  </td>
                  <td>
                    {item.savings_claim_status === 'VERIFIED' && item.verified_electricity_savings_kwh != null ? (
                      <strong style={{ color: '#10b981' }}>{formatNumber(item.verified_electricity_savings_kwh)} kWh</strong>
                    ) : item.electricity_savings_kwh != null && item.savings_claim_status !== 'NOT_VERIFIED' ? (
                      <div>
                        <strong style={{ color: '#eab308' }}>{formatNumber(item.electricity_savings_kwh)} kWh</strong>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Pending sign-off</div>
                      </div>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Unverified</span>
                    )}
                  </td>
                  <td>
                    <div style={{ fontSize: '0.78rem' }}>
                      <div>
                        <span style={{ color: 'var(--text-muted)' }}>Verified: </span>
                        {item.savings_claim_status === 'VERIFIED' && item.verified_monetary_savings_inr != null ? (
                          <strong style={{ color: '#10b981' }}>{formatCurrency(item.verified_monetary_savings_inr)}</strong>
                        ) : (
                          <span style={{ color: '#9ca3af', fontStyle: 'italic', fontSize: '0.71rem' }}>Unverified</span>
                        )}
                      </div>
                      <div style={{ marginTop: '0.2rem', color: 'var(--text-muted)', fontSize: '0.71rem' }}>
                        Ledger: <strong>{item.savings_claim_status === 'VERIFIED' && item.verified_monetary_savings_inr != null ? formatCurrency(item.verified_monetary_savings_inr) : '₹0 ledger contribution'}</strong>
                      </div>
                      <div style={{ fontSize: '0.69rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                        {item.estimated_avoided_cost_assumption || item.monetary_savings_basis}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      <div>
                        Output:{' '}
                        {item.output_guardrail_met === true ? (
                          <span style={{ color: '#22c55e', fontWeight: 600 }}>✓ Met</span>
                        ) : item.output_guardrail_met === false ? (
                          <span style={{ color: '#ef4444', fontWeight: 600 }}>✕ Breached</span>
                        ) : (
                          <span style={{ color: '#f59e0b', fontStyle: 'italic' }}>Output protection could not be assessed</span>
                        )}
                      </div>
                      <div>
                        Yield:{' '}
                        {item.quality_guardrail_met === true ? (
                          <span style={{ color: '#22c55e', fontWeight: 600 }}>✓ Met</span>
                        ) : item.quality_guardrail_met === false ? (
                          <span style={{ color: '#ef4444', fontWeight: 600 }}>✕ Breached</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>Not assessed</span>
                        )}
                      </div>
                      <div>
                        Downtime:{' '}
                        {item.downtime_guardrail_met === true ? (
                          <span style={{ color: '#22c55e', fontWeight: 600 }}>✓ Met</span>
                        ) : item.downtime_guardrail_met === false ? (
                          <span style={{ color: '#ef4444', fontWeight: 600 }}>✕ Breached</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>Not assessed</span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '0.75rem' }}>
                      <div><strong>Reviewer:</strong> {item.signed_off_by || 'Pending Sign-Off'}</div>
                      {item.signed_off_at && <div>{formatDateTime(item.signed_off_at)}</div>}
                      {item.review_decision && (
                        <div style={{ color: item.review_decision === 'APPROVED_VERIFIED' ? '#22c55e' : '#ef4444' }}>
                          {item.review_decision}
                        </div>
                      )}
                    </div>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn-iac btn-iac-secondary btn-iac-sm"
                      onClick={() => onInspectAction && onInspectAction(item.action_id)}
                    >
                      Inspect M&amp;V
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
