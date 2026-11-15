import React, { useState } from 'react';

/**
 * Visual badge & icon helper for overall response verification status
 */
function getVerificationStatusConfig(status) {
  switch (status) {
    case 'VERIFIED':
      return {
        label: 'Claims Verified',
        badgeClass: 'status-verified',
        icon: (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
        ),
      };
    case 'PARTIALLY_VERIFIED':
      return {
        label: 'Partially Verified',
        badgeClass: 'status-partial',
        icon: (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        ),
      };
    case 'CONFLICT_DETECTED':
      return {
        label: 'Conflict Detected',
        badgeClass: 'status-conflict',
        icon: (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
        ),
      };
    case 'UNVERIFIED':
      return {
        label: 'Unverified Claims',
        badgeClass: 'status-unverified',
        icon: (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        ),
      };
    case 'NO_ANALYTIC_CLAIMS':
    default:
      return {
        label: 'No Analytic Claims',
        badgeClass: 'status-none',
        icon: (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="8" y1="12" x2="16" y2="12"/>
          </svg>
        ),
      };
  }
}

/**
 * Visual badge & icon helper for individual claim outcome
 */
function getOutcomeConfig(outcome) {
  switch (outcome) {
    case 'VERIFIED':
      return {
        label: 'Verified',
        className: 'outcome-verified',
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        ),
      };
    case 'CONFLICTING':
      return {
        label: 'Conflicting',
        className: 'outcome-conflicting',
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
        ),
      };
    case 'SCOPE_MISMATCH':
      return {
        label: 'Scope Mismatch',
        className: 'outcome-mismatch',
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
            <polyline points="2 17 12 22 22 17"/>
            <polyline points="2 12 12 17 22 12"/>
          </svg>
        ),
      };
    case 'UNIT_MISMATCH':
      return {
        label: 'Unit Mismatch',
        className: 'outcome-mismatch',
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>
            <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
          </svg>
        ),
      };
    case 'NOT_APPLICABLE':
      return {
        label: 'Not Applicable',
        className: 'outcome-na',
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="8" y1="12" x2="16" y2="12"/>
          </svg>
        ),
      };
    case 'UNVERIFIED':
    default:
      return {
        label: 'Unverified',
        className: 'outcome-unverified',
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        ),
      };
  }
}

/**
 * ClaimVerificationView: Displays transparent verification metadata for AI-generated numerical claims.
 * Complies strictly with the AssistantChatResponse schema:
 * - verification_status: VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, CONFLICT_DETECTED, NO_ANALYTIC_CLAIMS
 * - claims: array of ClaimVerificationItem
 * - verified_claims_count, unverified_claims_count
 */
export default function ClaimVerificationView({
  verificationStatus = null,
  claims = [],
  verifiedClaimsCount = 0,
  unverifiedClaimsCount = 0,
  evidenceId = 'assistant-claims-verification',
}) {
  // If this message predates the verification feature (historical message), render nothing
  if (!verificationStatus && (!claims || claims.length === 0)) {
    return null;
  }

  const effectiveStatus = verificationStatus || (claims.length > 0 ? 'PARTIALLY_VERIFIED' : 'NO_ANALYTIC_CLAIMS');
  const statusConfig = getVerificationStatusConfig(effectiveStatus);

  // Auto-expand if a conflict was detected so the operator notices discrepancies immediately
  const hasConflict = effectiveStatus === 'CONFLICT_DETECTED' || claims.some((c) => c.outcome === 'CONFLICTING');
  const [isOpen, setIsOpen] = useState(hasConflict);

  // If response contains no analytic claims
  if (effectiveStatus === 'NO_ANALYTIC_CLAIMS' && (!claims || claims.length === 0)) {
    return (
      <div className="assistant-claim-verification-note">
        <span className={`claim-status-pill ${statusConfig.badgeClass}`}>
          {statusConfig.icon}
          <span>{statusConfig.label}</span>
        </span>
        <span className="claim-note-text">
          Direct synthesis &bull; No numerical analytical claims evaluated
        </span>
      </div>
    );
  }

  const totalClaims = claims.length;

  return (
    <div className={`assistant-claim-verification-card ${isOpen ? 'open' : ''} ${hasConflict ? 'has-conflict' : ''}`}>
      <button
        type="button"
        className="claim-verification-header"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-controls={evidenceId}
      >
        <div className="claim-header-left">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <span className="claim-verification-title">Evidence verification</span>
          <span className={`claim-status-pill ${statusConfig.badgeClass}`}>
            {statusConfig.icon}
            <span>{statusConfig.label}</span>
          </span>
          <span className="claim-summary-counts">
            {verifiedClaimsCount > 0 && (
              <span className="count-verified">{verifiedClaimsCount} verified</span>
            )}
            {unverifiedClaimsCount > 0 && (
              <span className="count-unverified">{unverifiedClaimsCount} unverified</span>
            )}
            {verifiedClaimsCount === 0 && unverifiedClaimsCount === 0 && totalClaims > 0 && (
              <span className="count-total">{totalClaims} {totalClaims === 1 ? 'claim' : 'claims'}</span>
            )}
          </span>
        </div>

        <div className="claim-header-right">
          <span className="claim-toggle-hint">
            {isOpen ? 'Hide claim audit' : `Inspect ${totalClaims} ${totalClaims === 1 ? 'claim' : 'claims'}`}
          </span>
          <svg
            className={`claim-chevron ${isOpen ? 'rotated' : ''}`}
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </button>

      <div id={evidenceId} className="claim-verification-body" hidden={!isOpen}>
        {claims.length === 0 ? (
          <p className="claim-empty-note">
            No individual numerical claims were isolated for verification in this turn.
          </p>
        ) : (
          <div className="claim-items-list">
            {claims.map((claim, idx) => {
              const outcomeCfg = getOutcomeConfig(claim.outcome);
              const isConflicting = claim.outcome === 'CONFLICTING';
              const isMismatch = claim.outcome === 'SCOPE_MISMATCH' || claim.outcome === 'UNIT_MISMATCH';

              return (
                <div
                  key={idx}
                  className={`claim-item-card outcome-${(claim.outcome || 'unverified').toLowerCase()} ${
                    isConflicting ? 'claim-conflict-card' : ''
                  }`}
                >
                  <div className="claim-item-topbar">
                    <div className="claim-item-badges">
                      <span className={`claim-outcome-pill ${outcomeCfg.className}`}>
                        {outcomeCfg.icon}
                        <span>{outcomeCfg.label}</span>
                      </span>
                      {claim.was_corrected && (
                        <span className="claim-corrected-badge" title="Contradiction was automatically corrected in the final response">
                          Corrected by Verifier
                        </span>
                      )}
                    </div>
                    {claim.supporting_tool && (
                      <span className="claim-tool-badge" title="Authoritative backing tool">
                        <code>{claim.supporting_tool}</code>
                      </span>
                    )}
                  </div>

                  <div className="claim-item-content">
                    {/* Primary comparison: Claimed vs Authoritative fact */}
                    <div className="claim-values-comparison">
                      <div className="claim-value-block claimed-value-block">
                        <span className="value-label">Claimed value</span>
                        <div className="value-display">
                          <span className="value-number">{claim.claimed_number}</span>
                          {claim.unit && <span className="value-unit">{claim.unit}</span>}
                        </div>
                      </div>

                      {claim.authoritative_value && (
                        <div className={`claim-value-block authoritative-value-block ${isConflicting ? 'auth-divergence' : ''}`}>
                          <span className="value-label">Authoritative telemetry</span>
                          <div className="value-display">
                            <span className="value-number">{claim.authoritative_value}</span>
                            {claim.authoritative_unit && <span className="value-unit">{claim.authoritative_unit}</span>}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Scope and Metric Context */}
                    {(claim.metric || claim.scope) && (
                      <div className="claim-meta-details">
                        {claim.metric && (
                          <span className="claim-meta-tag">
                            <span className="meta-key">Metric:</span>
                            <span className="meta-val">{claim.metric}</span>
                          </span>
                        )}
                        {claim.scope && (
                          <span className="claim-meta-tag">
                            <span className="meta-key">Scope:</span>
                            <span className="meta-val">{claim.scope}</span>
                          </span>
                        )}
                      </div>
                    )}

                    {/* Explanatory rationale from deterministic verifier */}
                    {claim.explanation && (
                      <div className={`claim-explanation-box ${isConflicting ? 'explanation-conflict' : isMismatch ? 'explanation-mismatch' : ''}`}>
                        <div className="explanation-icon-col">
                          {isConflicting ? (
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <circle cx="12" cy="12" r="10"/>
                              <line x1="12" y1="8" x2="12" y2="12"/>
                              <line x1="12" y1="16" x2="12.01" y2="16"/>
                            </svg>
                          ) : (
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <circle cx="12" cy="12" r="10"/>
                              <line x1="12" y1="16" x2="12" y2="12"/>
                              <line x1="12" y1="8" x2="12.01" y2="8"/>
                            </svg>
                          )}
                        </div>
                        <span className="explanation-text">{claim.explanation}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

