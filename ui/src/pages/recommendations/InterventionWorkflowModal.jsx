import React, { useState, useEffect, useRef } from 'react';
import { recommendationsApi } from '../../services/recommendationsApi';
import { formatDateTime, formatCurrency, formatNumber } from '../../utils/formatters';
import './intervention-workflow-modal.css';

const WORKFLOW_STEPS = [
  { key: 'overview', label: 'Overview' },
  { key: 'review', label: 'Review' },
  { key: 'plan', label: 'Measurement plan' },
  { key: 'implement', label: 'Implementation' },
  { key: 'assessment', label: 'Assessment' },
];

/**
 * Format raw backend enums (e.g. 'PENDING_REVIEW') to sentence/title case ('Pending review')
 */
function formatEnum(val) {
  if (!val) return '';
  return val
    .toLowerCase()
    .split('_')
    .map((word, i) => (i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ');
}

const REGISTERED_PLANT_LINES = {
  'IN-TN-01': ['SMT-L1', 'FAL-L1'],
  'IN-KA-01': ['SMT-L2', 'FAL-L2'],
};

function getResolvedLineDisplay(plantId, equipment) {
  if (!equipment) return 'Line unassigned';
  const clean = String(equipment).trim();
  const validLines = REGISTERED_PLANT_LINES[plantId] || ['SMT-L1', 'FAL-L1', 'SMT-L2', 'FAL-L2'];
  if (validLines.includes(clean)) {
    return clean;
  }
  if (clean.toUpperCase() === 'SMT') return validLines.find((l) => l.startsWith('SMT')) || 'Line unassigned';
  if (clean.toUpperCase() === 'FAL') return validLines.find((l) => l.startsWith('FAL')) || 'Line unassigned';
  return 'Line unassigned';
}

/**
 * Complete Operator Workflow Modal for Corrective Actions, Measurement Plans,
 * Deterministic Before/After Assessment, and Reviewer Sign-Off.
 */
export default function InterventionWorkflowModal({
  action,
  isOpen,
  onClose,
  onActionUpdated,
}) {
  const [activeStep, setActiveStep] = useState('overview');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [plan, setPlan] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [showEvidence, setShowEvidence] = useState(false);

  // Focus trap and restore references
  const dialogRef = useRef(null);
  const triggerElementRef = useRef(null);
  const stepRailRef = useRef(null);

  // Review Form state
  const [reviewDecision, setReviewDecision] = useState(() => {
    if (action?.review_status === 'APPROVED') return 'APPROVE';
    if (action?.review_status === 'REJECTED') return 'REJECT';
    return null;
  });
  const [reviewReason, setReviewReason] = useState('');
  const [reviewerName, setReviewerName] = useState('');

  // Implementation Form state
  const [implementedAt, setImplementedAt] = useState(new Date().toISOString().slice(0, 16));
  const [implementedBy, setImplementedBy] = useState('Production Maintenance Team');
  const [implementationNotes, setImplementationNotes] = useState('');
  const [workOrderId, setWorkOrderId] = useState('');
  const [downtimeEventId, setDowntimeEventId] = useState('');

  // Plan Form state
  const [intendedChange, setIntendedChange] = useState('');
  const [planOwner, setPlanOwner] = useState('');
  const [baselineStart, setBaselineStart] = useState('2026-10-01T00:00');
  const [baselineEnd, setBaselineEnd] = useState('2026-10-31T23:00');
  const [postStart, setPostStart] = useState('2026-11-04T00:00');
  const [postEnd, setPostEnd] = useState('2026-11-04T23:00');
  const [comparisonMethod, setComparisonMethod] = useState('MATCHED_SCHEDULE');
  const [minCoveragePct, setMinCoveragePct] = useState(90);

  // Guardrail fields with direction, units, and engineering reasons
  const [guardrailOutputMin, setGuardrailOutputMin] = useState(500);
  const [guardrailOutputUnit, setGuardrailOutputUnit] = useState('good units');
  const [guardrailOutputDirection, setGuardrailOutputDirection] = useState('GREATER_OR_EQUAL');
  const [guardrailOutputReason, setGuardrailOutputReason] = useState('Minimum production volume to meet customer delivery schedule');

  const [guardrailRejectMax, setGuardrailRejectMax] = useState(25);
  const [guardrailRejectUnit, setGuardrailRejectUnit] = useState('units');
  const [guardrailRejectDirection, setGuardrailRejectDirection] = useState('LESS_OR_EQUAL');
  const [guardrailRejectReason, setGuardrailRejectReason] = useState('QA maximum scrap ceiling for line process stability');

  const [guardrailDowntimeMax, setGuardrailDowntimeMax] = useState(120);
  const [guardrailDowntimeUnit, setGuardrailDowntimeUnit] = useState('minutes');
  const [guardrailDowntimeDirection, setGuardrailDowntimeDirection] = useState('LESS_OR_EQUAL');
  const [guardrailDowntimeReason, setGuardrailDowntimeReason] = useState('Operational line availability allowance for shift changeovers');

  const [guardrailRestartMax, setGuardrailRestartMax] = useState(15);
  const [guardrailRestartUnit, setGuardrailRestartUnit] = useState('minutes');
  const [guardrailRestartDirection, setGuardrailRestartDirection] = useState('LESS_OR_EQUAL');
  const [guardrailRestartReason, setGuardrailRestartReason] = useState('Maximum line restart ramp duration following physical intervention');

  const [successCriterion, setSuccessCriterion] = useState('Cost intensity reduction >= 3.0% with good output >= 500 units');
  const [isRetrospective, setIsRetrospective] = useState(false);

  // Sign-Off Form state
  const [signOffDecision, setSignOffDecision] = useState('APPROVED_VERIFIED');
  const [signOffNotes, setSignOffNotes] = useState('');
  const [signOffReviewer, setSignOffReviewer] = useState('Plant Operations Manager - R. Kumar');

  // Trial Plan Auto-Draft & AI Explanation State
  const [draftingTrialPlan, setDraftingTrialPlan] = useState(false);
  const [trialSuitabilityNotice, setTrialSuitabilityNotice] = useState(null);
  const [draftTrialDetails, setDraftTrialDetails] = useState(null);
  const [assessmentExplanation, setAssessmentExplanation] = useState(null);
  const [explainingAssessment, setExplainingAssessment] = useState(false);
  const [explainError, setExplainError] = useState(null);

  const handleAutoDraftTrialPlan = async () => {
    if (!action?.recommendation_id) return;
    setDraftingTrialPlan(true);
    setTrialSuitabilityNotice(null);
    try {
      const res = await fetch(`/api/recommendations/${encodeURIComponent(action.recommendation_id)}/draft-trial-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to draft trial plan: HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data.plan_draft) {
        const d = data.plan_draft;
        if (d.intended_change) setIntendedChange(d.intended_change);
        if (d.comparison_method) setComparisonMethod(d.comparison_method);
        if (d.baseline_start) setBaselineStart(d.baseline_start.slice(0, 16));
        if (d.baseline_end) setBaselineEnd(d.baseline_end.slice(0, 16));
        if (d.post_start) setPostStart(d.post_start.slice(0, 16));
        if (d.post_end) setPostEnd(d.post_end.slice(0, 16));
        if (d.guardrail_output_min !== undefined) setGuardrailOutputMin(d.guardrail_output_min);
        if (d.guardrail_reject_max !== undefined) setGuardrailRejectMax(d.guardrail_reject_max);
        if (d.guardrail_downtime_max_min !== undefined) setGuardrailDowntimeMax(d.guardrail_downtime_max_min);
        if (d.guardrail_restart_max_min !== undefined) setGuardrailRestartMax(d.guardrail_restart_max_min);
        if (d.guardrail_output_reason) setGuardrailOutputReason(d.guardrail_output_reason);
        if (d.guardrail_reject_reason) setGuardrailRejectReason(d.guardrail_reject_reason);
        if (d.guardrail_downtime_reason) setGuardrailDowntimeReason(d.guardrail_downtime_reason);
        if (d.guardrail_restart_reason) setGuardrailRestartReason(d.guardrail_restart_reason);
        if (d.success_criterion) setSuccessCriterion(d.success_criterion);
        if (d.min_coverage_pct) setMinCoveragePct(d.min_coverage_pct);
      }
      if (data.is_suitable === false || data.unsuitable_reason || data.audit_recommendation) {
        setTrialSuitabilityNotice({
          status: (data.is_suitable === false || data.unsuitable_reason) ? 'UNSUITABLE_FOR_TRIAL' : 'EVIDENCE_GATHERING',
          reason: data.unsuitable_reason || data.trial_suitability_reason,
          auditRecommendation: data.audit_recommendation,
        });
      }
      setDraftTrialDetails({
        isSuitable: data.is_suitable,
        targetEquipment: data.target_equipment,
        operatingChange: data.suggested_operating_change,
        operatingWindow: data.operating_window,
        whySavesElectricity: data.why_saves_electricity,
        productionDependencies: data.production_dependencies,
        restartRequirements: data.restart_requirements,
        stopConditions: data.stop_conditions,
        inferenceSource: data.inference_source,
        agentExecutionTrace: data.agent_execution_trace,
      });
    } catch (err) {
      console.error('Failed to auto-draft trial plan:', err);
      alert('Failed to draft trial plan: ' + err.message);
    } finally {
      setDraftingTrialPlan(false);
    }
  };

  const handleExplainAssessmentWithAi = async () => {
    if (!action?.action_id) return;
    setExplainingAssessment(true);
    setExplainError(null);
    try {
      const res = await fetch(`/api/actions/${encodeURIComponent(action.action_id)}/assessment/explain-ai`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Explanation failed: HTTP ${res.status}`);
      }
      const data = await res.json();
      setAssessmentExplanation(data);
    } catch (err) {
      console.error('Failed to explain assessment with AI:', err);
      setExplainError(err.message || 'AI Explanation service unavailable.');
    } finally {
      setExplainingAssessment(false);
    }
  };

  // Lock background scroll and store triggering active element
  useEffect(() => {
    if (!isOpen) return;
    triggerElementRef.current = document.activeElement;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = prevOverflow;
      if (triggerElementRef.current && typeof triggerElementRef.current.focus === 'function') {
        triggerElementRef.current.focus();
      }
    };
  }, [isOpen]);

  // Support Escape key to close dialog
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Trap keyboard focus inside dialog
  useEffect(() => {
    if (!isOpen || !dialogRef.current) return;
    const dialogNode = dialogRef.current;

    const handleFocusTrap = (e) => {
      if (e.key !== 'Tab') return;
      const focusables = Array.from(
        dialogNode.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    dialogNode.addEventListener('keydown', handleFocusTrap);
    return () => dialogNode.removeEventListener('keydown', handleFocusTrap);
  }, [isOpen, activeStep]);

  // Load existing plan & assessment when modal opens or action changes
  useEffect(() => {
    if (!action || !isOpen) return;
    setError(null);

    // Sync review defaults
    if (action.review_status === 'APPROVED') {
      setReviewDecision('APPROVE');
    } else if (action.review_status === 'REJECTED') {
      setReviewDecision('REJECT');
    } else {
      setReviewDecision(null);
    }
    setReviewerName(action.reviewed_by || '');
    setReviewReason(action.review_notes || '');

    const loadPlanAndAssessment = async () => {
      setLoading(true);
      try {
        try {
          const p = await recommendationsApi.getMeasurementPlan(action.action_id);
          setPlan(p);
          if (p) {
            setIntendedChange(p.intended_change || action.description || '');
            setPlanOwner(p.implementation_owner || action.owner || '');
            if (p.comparison_method) setComparisonMethod(p.comparison_method);
            if (p.min_coverage_pct) setMinCoveragePct(p.min_coverage_pct);
            if (p.guardrail_output_min !== undefined && p.guardrail_output_min !== null) setGuardrailOutputMin(p.guardrail_output_min);
            if (p.guardrail_output_reason) setGuardrailOutputReason(p.guardrail_output_reason);
            if (p.guardrail_reject_max !== undefined && p.guardrail_reject_max !== null) setGuardrailRejectMax(p.guardrail_reject_max);
            if (p.guardrail_reject_reason) setGuardrailRejectReason(p.guardrail_reject_reason);
            if (p.guardrail_downtime_max_min !== undefined && p.guardrail_downtime_max_min !== null) setGuardrailDowntimeMax(p.guardrail_downtime_max_min);
            if (p.guardrail_downtime_reason) setGuardrailDowntimeReason(p.guardrail_downtime_reason);
            if (p.guardrail_restart_max_min !== undefined && p.guardrail_restart_max_min !== null) setGuardrailRestartMax(p.guardrail_restart_max_min);
            if (p.guardrail_restart_reason) setGuardrailRestartReason(p.guardrail_restart_reason);
            if (p.baseline_start) setBaselineStart(p.baseline_start.slice(0, 16));
            if (p.baseline_end) setBaselineEnd(p.baseline_end.slice(0, 16));
            if (p.post_start) setPostStart(p.post_start.slice(0, 16));
            if (p.post_end) setPostEnd(p.post_end.slice(0, 16));
          }
        } catch (planErr) {
          const errMsg = planErr.message || '';
          if (planErr.status === 404 && errMsg.toLowerCase().includes('no measurement plan found')) {
            // Recognized legitimate empty plan state: render empty plan form without showing error
            setPlan(null);
          } else {
            // Unknown action, permission, or server errors: keep visible
            setPlan(null);
            setError(errMsg || 'Failed to load measurement plan.');
          }
        }

        if (action.implemented_at) {
          try {
            const asm = await recommendationsApi.getAssessment(action.action_id);
            setAssessment(asm);
          } catch {
            setAssessment(null);
          }
        } else {
          setAssessment(null);
        }
      } finally {
        setLoading(false);
      }
    };

    loadPlanAndAssessment();

    if (action) {
      setIntendedChange(action.description || 'Standby load interlock and heater setpoint optimization');
      setPlanOwner(action.owner || 'Facilities Engineering');
      if (action.implemented_at) {
        try {
          setImplementedAt(new Date(action.implemented_at).toISOString().slice(0, 16));
        } catch {
          setImplementedAt('');
        }
      }
    }
  }, [action?.action_id, isOpen]);

  if (!isOpen || !action) return null;

  // Step indices
  const currentStepIndex = WORKFLOW_STEPS.findIndex((s) => s.key === activeStep);

  const handleStepClick = (stepKey) => {
    setError(null);
    if (stepKey === 'assessment' && action.implemented_at && !assessment) {
      handleEvaluateAssessment();
    } else {
      setActiveStep(stepKey);
    }
  };

  const handlePrevStep = () => {
    if (currentStepIndex > 0) {
      handleStepClick(WORKFLOW_STEPS[currentStepIndex - 1].key);
    }
  };

  const handleNextStep = () => {
    if (currentStepIndex < WORKFLOW_STEPS.length - 1) {
      handleStepClick(WORKFLOW_STEPS[currentStepIndex + 1].key);
    }
  };

  // Completion statuses for stepper checkmarks
  const isStepCompleted = (key) => {
    switch (key) {
      case 'overview':
        return Boolean(action.action_id);
      case 'review':
        return action.review_status === 'APPROVED' || action.review_status === 'REJECTED';
      case 'plan':
        return Boolean(plan && plan.is_frozen);
      case 'implement':
        return Boolean(action.implemented_at);
      case 'assessment':
        return Boolean(action.assessment_status && action.assessment_status !== 'NONE');
      default:
        return false;
    }
  };

  // Handlers
  const handleReviewSubmit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!reviewDecision) {
      setError('Please select either Approve proposal or Reject proposal before submitting.');
      return;
    }
    if (!reviewReason.trim()) {
      setError('Please provide an engineering justification explaining why this action is appropriate or rejected.');
      return;
    }
    const finalReviewer = reviewerName.trim() || 'Facilities Engineering Lead (Demo)';
    setLoading(true);
    setError(null);
    try {
      const updated = await recommendationsApi.reviewAction(action.action_id, {
        decision: reviewDecision,
        reason: reviewReason.trim(),
        reviewer: finalReviewer,
      });
      if (onActionUpdated) onActionUpdated(updated);
      setActiveStep(reviewDecision === 'APPROVE' ? 'plan' : 'overview');
    } catch (err) {
      setError(err.message || 'Failed to submit proposal review.');
    } finally {
      setLoading(false);
    }
  };

  const handleImplementationSubmit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!implementedAt) {
      setError('An explicit physical implementation timestamp is required.');
      return;
    }
    if (!implementedBy.trim() || implementedBy.trim().toLowerCase() === 'anonymous' || implementedBy.trim().toLowerCase() === 'admin') {
      setError('A genuine operator or team identifier is required (anonymous or placeholder identities are rejected).');
      return;
    }
    if (!implementationNotes.trim()) {
      setError('Please provide implementation notes describing physical actions taken on equipment.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = {
        implemented_at: new Date(implementedAt).toISOString(),
        implemented_by: implementedBy.trim(),
        implementation_notes: implementationNotes.trim(),
      };
      if (workOrderId.trim()) payload.work_order_id = workOrderId.trim();
      if (downtimeEventId.trim()) payload.downtime_event_id = downtimeEventId.trim();

      const updated = await recommendationsApi.recordImplementation(action.action_id, payload);
      if (onActionUpdated) onActionUpdated(updated);
      setActiveStep('assessment');
      handleEvaluateAssessment();
    } catch (err) {
      setError(err.message || 'Failed to record implementation.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePlanSubmit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (!baselineStart || !baselineEnd || !postStart || !postEnd) {
        setError('Please specify valid start and end dates for both baseline and post-intervention windows.');
        setLoading(false);
        return;
      }
      if (baselineEnd <= baselineStart) {
        setError('Invalid dates: Baseline end date must be after baseline start date.');
        setLoading(false);
        return;
      }
      if (postEnd <= postStart) {
        setError('Invalid dates: Post-intervention end date must be after post-intervention start date.');
        setLoading(false);
        return;
      }

      const plant = action.plant_id || 'IN-TN-01';
      const resolvedLine = getResolvedLineDisplay(plant, action.affected_equipment);
      const linePayload = resolvedLine !== 'Line unassigned' ? resolvedLine : (action.affected_equipment || 'Line unassigned');
      const meterId = action.measurement_meter_id || action.affected_equipment || 'MTR-COMPRESSOR';
      const meters = [meterId];

      const newPlan = await recommendationsApi.createMeasurementPlan(action.action_id, {
        intended_change: intendedChange,
        implementation_owner: planOwner,
        plant_id: plant,
        process_or_line: linePayload,
        eligible_meters: meters,
        production_denominator: resolvedLine !== 'Line unassigned' ? `${resolvedLine} good finished units` : 'Plant finished goods',
        production_unit: 'good units',
        baseline_start: baselineStart.length === 16 ? `${baselineStart}:00` : baselineStart,
        baseline_end: baselineEnd.length === 16 ? `${baselineEnd}:00` : baselineEnd,
        post_start: postStart.length === 16 ? `${postStart}:00` : postStart,
        post_end: postEnd.length === 16 ? `${postEnd}:00` : postEnd,
        comparison_method: comparisonMethod,
        min_coverage_pct: Number(minCoveragePct),
        guardrail_output_min: Number(guardrailOutputMin),
        guardrail_output_unit: guardrailOutputUnit,
        guardrail_output_direction: guardrailOutputDirection,
        guardrail_output_reason: guardrailOutputReason,
        guardrail_reject_max: Number(guardrailRejectMax),
        guardrail_reject_unit: guardrailRejectUnit,
        guardrail_reject_direction: guardrailRejectDirection,
        guardrail_reject_reason: guardrailRejectReason,
        guardrail_downtime_max_min: Number(guardrailDowntimeMax),
        guardrail_downtime_unit: guardrailDowntimeUnit,
        guardrail_downtime_direction: guardrailDowntimeDirection,
        guardrail_downtime_reason: guardrailDowntimeReason,
        guardrail_restart_max_min: Number(guardrailRestartMax),
        guardrail_restart_unit: guardrailRestartUnit,
        guardrail_restart_direction: guardrailRestartDirection,
        guardrail_restart_reason: guardrailRestartReason,
        success_criterion: successCriterion,
        is_retrospective: isRetrospective,
      });
      setPlan(newPlan);
      setError(null);
      if (onActionUpdated) onActionUpdated({ ...action, measurement_plan_id: newPlan.plan_id });
    } catch (err) {
      setError(err.message || 'Failed to create measurement plan.');
    } finally {
      setLoading(false);
    }
  };

  const handleApprovePlan = async () => {
    if (!plan) return;
    setLoading(true);
    setError(null);
    try {
      const approved = await recommendationsApi.approveMeasurementPlan(action.action_id, {
        reviewer: reviewerName || 'Facilities Engineering Lead',
        approval_notes: 'Approved prospective M&V baseline, coverage, and guardrail limits.',
      });
      setPlan(approved);
      setActiveStep('implement');
    } catch (err) {
      setError(err.message || 'Failed to approve measurement plan.');
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluateAssessment = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await recommendationsApi.getAssessment(action.action_id);
      setAssessment(res);
      setActiveStep('assessment');
    } catch (err) {
      setError(err.message || 'Failed to evaluate before/after outcome.');
    } finally {
      setLoading(false);
    }
  };

  const handleSignOffSubmit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await recommendationsApi.signOffAssessment(action.action_id, {
        reviewer: signOffReviewer,
        decision: signOffDecision,
        notes: signOffNotes,
      });
      const updatedAsm = await recommendationsApi.getAssessment(action.action_id);
      setAssessment(updatedAsm);
      if (onActionUpdated) {
        onActionUpdated({
          ...action,
          assessment_status: signOffDecision === 'APPROVED_VERIFIED' ? 'VERIFIED' : 'NOT_VERIFIED',
          status: signOffDecision === 'APPROVED_VERIFIED' ? 'COMPLETED' : action.status,
        });
      }
    } catch (err) {
      setError(err.message || 'Failed to submit sign-off decision.');
    } finally {
      setLoading(false);
    }
  };

  // Render primary action button in persistent footer
  const renderPrimaryAction = () => {
    if (activeStep === 'overview') {
      return (
        <button
          type="button"
          className="workflow-btn workflow-btn-primary"
          onClick={() => setActiveStep('review')}
        >
          Proceed to Review →
        </button>
      );
    }

    if (activeStep === 'review') {
      const isReject = reviewDecision === 'REJECT';
      const label = loading
        ? 'Submitting review…'
        : reviewDecision === 'APPROVE'
          ? 'Approve proposal'
          : reviewDecision === 'REJECT'
            ? 'Reject proposal'
            : 'Select decision to submit';

      return (
        <button
          type="button"
          className={`workflow-btn ${isReject ? 'workflow-btn-danger' : 'workflow-btn-primary'}`}
          onClick={handleReviewSubmit}
          disabled={loading || !reviewDecision}
        >
          {label}
        </button>
      );
    }

    if (activeStep === 'plan') {
      if (!plan) {
        return (
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={handleCreatePlanSubmit}
            disabled={loading}
          >
            {loading ? 'Creating plan…' : 'Capture measurement plan'}
          </button>
        );
      }
      if (!plan.is_frozen) {
        return (
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={handleApprovePlan}
            disabled={loading}
          >
            {loading ? 'Freezing plan…' : 'Approve & freeze plan'}
          </button>
        );
      }
      return (
        <button
          type="button"
          className="workflow-btn workflow-btn-primary"
          onClick={() => setActiveStep('implement')}
        >
          Proceed to Implementation →
        </button>
      );
    }

    if (activeStep === 'implement') {
      if (!action.implemented_at) {
        return (
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={handleImplementationSubmit}
            disabled={loading || action.review_status !== 'APPROVED'}
          >
            {loading ? 'Recording…' : 'Record implementation'}
          </button>
        );
      }
      return (
        <button
          type="button"
          className="workflow-btn workflow-btn-primary"
          onClick={handleEvaluateAssessment}
          disabled={loading}
        >
          {loading ? 'Loading assessment…' : 'Proceed to Assessment →'}
        </button>
      );
    }

    if (activeStep === 'assessment') {
      if (!assessment) {
        return (
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={handleEvaluateAssessment}
            disabled={loading}
          >
            {loading ? 'Evaluating…' : 'Run assessment'}
          </button>
        );
      }
      return (
        <button
          type="button"
          className="workflow-btn workflow-btn-primary"
          onClick={handleSignOffSubmit}
          disabled={loading}
        >
          {loading ? 'Finalizing…' : 'Sign off & update ledger'}
        </button>
      );
    }

    return null;
  };

  return (
    <div
      className="workflow-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="workflow-action-title"
    >
      <div
        className="workflow-modal-dialog"
        ref={dialogRef}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ROW 1: HEADER (Action title, compact metadata, status badges, and stepper) */}
        <div className="workflow-modal-header">
          <div className="workflow-header-top">
            <div className="workflow-header-info">
              <div className="workflow-header-badges">
                <span className={`workflow-badge workflow-badge-${(action.status || 'open').toLowerCase().replace('_', '-')}`}>
                  {formatEnum(action.status || 'OPEN')}
                </span>
                <span className="workflow-badge workflow-badge-review">
                  {formatEnum(action.review_status || 'PENDING_REVIEW')}
                </span>
                {action.assessment_status && action.assessment_status !== 'NONE' && (
                  <span className={`workflow-badge workflow-badge-${action.assessment_status.toLowerCase()}`}>
                    {formatEnum(action.assessment_status)}
                  </span>
                )}
                {plan?.is_retrospective && (
                  <span className="workflow-badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#d97706', border: '1px solid #f59e0b' }}>
                    Retrospective analysis
                  </span>
                )}
              </div>

              <h2 className="workflow-header-title" id="workflow-action-title">
                {action.title}
              </h2>

              <div className="workflow-header-meta">
                <span>Action ID: <span className="workflow-meta-pill">{action.action_id}</span></span>
                <span>• Plant: <span className="workflow-meta-pill">{action.plant_id || 'N/A'}</span></span>
                <span>• Line: <span className="workflow-meta-pill">{getResolvedLineDisplay(action.plant_id, action.affected_equipment)}</span></span>
                <span>• Meter: <span className="workflow-meta-pill">{action.measurement_meter_id || action.affected_equipment || 'MTR-COMPRESSOR'}</span></span>
              </div>
            </div>

            <button
              type="button"
              className="workflow-close-btn"
              onClick={onClose}
              aria-label="Close dialog"
              title="Close (Esc)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Stepper: 5 equal-width columns on desktop, horizontal scroll on mobile */}
          <div className="workflow-stepper-container">
            <div className="workflow-stepper-scroll" ref={stepRailRef}>
              <div className="workflow-stepper-rail" role="tablist" aria-label="Workflow Steps">
                {WORKFLOW_STEPS.map((step, idx) => {
                  const isSelected = activeStep === step.key;
                  const isCompleted = isStepCompleted(step.key);
                  const isLast = idx === WORKFLOW_STEPS.length - 1;

                  return (
                    <button
                      key={step.key}
                      type="button"
                      role="tab"
                      aria-selected={isSelected}
                      className={`workflow-step-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleStepClick(step.key)}
                      title={`Step ${idx + 1}: ${step.label}`}
                    >
                      <div className="workflow-step-node-wrap">
                        {!isLast && (
                          <div className={`workflow-step-connector ${isCompleted ? 'completed' : ''}`} />
                        )}
                        <div className={`workflow-step-marker ${isCompleted ? 'completed' : ''} ${isSelected ? 'active' : ''}`}>
                          {isCompleted ? (
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          ) : (
                            <span>{idx + 1}</span>
                          )}
                        </div>
                      </div>
                      <span className={`workflow-step-label ${isSelected ? 'active' : ''}`}>
                        {step.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* ROW 2: SCROLLABLE CONTENT (Single vertical scrollbar for dialog content) */}
        <div className="workflow-modal-content">
          {/* Error Banner if any error occurred */}
          {error && (
            <div className="workflow-alert-error" role="alert">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* STEP 1: OVERVIEW & BOUNDARY */}
          {activeStep === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              <div className="workflow-card">
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', fontWeight: 700 }}>
                  Action Description &amp; Scope
                </span>
                <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-primary)', whiteSpace: 'pre-line', lineHeight: 1.5 }}>
                  {action.description || 'No descriptive text supplied.'}
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                <div className="workflow-card">
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Production Line</span>
                  <div style={{ fontWeight: 650, fontSize: '0.9rem' }}>{getResolvedLineDisplay(action.plant_id, action.affected_equipment)}</div>
                </div>
                <div className="workflow-card">
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Measurement Meter</span>
                  <div style={{ fontWeight: 650, fontSize: '0.9rem' }}>{action.measurement_meter_id || action.affected_equipment || 'MTR-COMPRESSOR'}</div>
                </div>
                <div className="workflow-card">
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Responsible Team</span>
                  <div style={{ fontWeight: 650, fontSize: '0.9rem' }}>{action.responsible_team || 'Facilities / Production'}</div>
                </div>
                <div className="workflow-card">
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Originating Finding</span>
                  <div style={{ fontWeight: 650, fontSize: '0.85rem', color: '#10b981', fontFamily: 'monospace' }}>
                    {action.finding_id || 'N/A'}
                  </div>
                </div>
              </div>

              {action.shared_meter_limitation && (
                <div className="workflow-compact-notice warning">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                  <span><strong>Shared Metering Limitation:</strong> {action.shared_meter_limitation}</span>
                </div>
              )}

              <div className="workflow-card">
                <h4 className="workflow-card-title">Workflow Lifecycle Traceability</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', fontSize: '0.84rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color-light)', paddingBottom: '0.35rem' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>1. Proposal Review:</span>
                    <strong>{formatEnum(action.review_status || 'PENDING_REVIEW')} {action.reviewed_by ? `by ${action.reviewed_by}` : ''}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color-light)', paddingBottom: '0.35rem' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>2. Measurement Plan:</span>
                    <strong>{plan ? `v${plan.version} (${plan.is_frozen ? 'Frozen' : 'Draft'}${plan.is_retrospective ? ', Retrospective' : ''})` : 'Not Defined'}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color-light)', paddingBottom: '0.35rem' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>3. Physical Implementation:</span>
                    <strong>{action.implemented_at ? `${formatDateTime(action.implemented_at)} by ${action.implemented_by}` : 'Pending Implementation'}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>4. Verified Outcome:</span>
                    <strong>{formatEnum(action.assessment_status || 'NONE')}</strong>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: PROPOSAL REVIEW (Redesigned) */}
          {activeStep === 'review' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="workflow-card">
                <h3 className="workflow-card-title">Review proposal</h3>
                <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                  Approval authorizes capturing a frozen measurement plan and scheduling physical implementation on the equipment.
                </p>
              </div>

              {/* Approve & Reject explicit choices */}
              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 650, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
                  Review Decision Choice <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <div className="workflow-review-choices">
                  <div
                    tabIndex={0}
                    role="button"
                    aria-pressed={reviewDecision === 'APPROVE'}
                    className={`workflow-choice-card approve ${reviewDecision === 'APPROVE' ? 'selected' : ''}`}
                    onClick={() => {
                      setReviewDecision('APPROVE');
                      if (error) setError(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setReviewDecision('APPROVE');
                      }
                    }}
                  >
                    <div className="workflow-choice-header">
                      <span className="workflow-choice-title" style={{ color: reviewDecision === 'APPROVE' ? '#059669' : 'inherit' }}>
                        Approve proposal
                      </span>
                      {reviewDecision === 'APPROVE' && (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </div>
                    <span className="workflow-choice-desc">
                      Authorize operational intervention and proceed to define or freeze measurement plan.
                    </span>
                  </div>

                  <div
                    tabIndex={0}
                    role="button"
                    aria-pressed={reviewDecision === 'REJECT'}
                    className={`workflow-choice-card reject ${reviewDecision === 'REJECT' ? 'selected' : ''}`}
                    onClick={() => {
                      setReviewDecision('REJECT');
                      if (error) setError(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setReviewDecision('REJECT');
                      }
                    }}
                  >
                    <div className="workflow-choice-header">
                      <span className="workflow-choice-title" style={{ color: reviewDecision === 'REJECT' ? '#dc2626' : 'inherit' }}>
                        Reject proposal
                      </span>
                      {reviewDecision === 'REJECT' && (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      )}
                    </div>
                    <span className="workflow-choice-desc">
                      Decline operational intervention and archive the action with engineering justification.
                    </span>
                  </div>
                </div>
              </div>

              {/* Reviewer field with demo tag and example placeholder */}
              <div>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: '0.82rem', fontWeight: 650, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
                  <span>Reviewer Name &amp; Title</span>
                  <span className="workflow-demo-tag">Demo review</span>
                </label>
                <input
                  type="text"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  placeholder="e.g. A. Sharma (Facilities Engineering Lead)"
                  style={{
                    width: '100%',
                    padding: '0.55rem 0.75rem',
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                    boxBox: 'border-box',
                  }}
                />
              </div>

              {/* Full-width justification textarea with visible label and prompt */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.35rem', flexWrap: 'wrap', gap: '0.3rem' }}>
                  <label htmlFor="review-justification" style={{ fontSize: '0.82rem', fontWeight: 650, color: 'var(--text-primary)' }}>
                    Engineering justification <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                    Why is this action appropriate for this equipment?
                  </span>
                </div>
                <textarea
                  id="review-justification"
                  rows={4}
                  value={reviewReason}
                  onChange={(e) => {
                    setReviewReason(e.target.value);
                    if (error) setError(null);
                  }}
                  placeholder="Explain the technical basis, root-cause alignment, or rejection reason for this equipment..."
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.75rem',
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                    lineHeight: 1.45,
                    boxSizing: 'border-box',
                  }}
                  required
                />
              </div>

              {/* Compact Notice near decision replacing oversized banner */}
              <div className="workflow-compact-notice info">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                <span>Demo reviews are excluded from verified factory totals. All decisions are tracked in the operational audit trail.</span>
                {plan && (
                  <span style={{ marginLeft: 'auto', fontWeight: 600, fontSize: '0.74rem', whiteSpace: 'nowrap' }}>
                    Plan v{plan.version} ({plan.is_frozen ? 'Frozen' : 'Draft'})
                  </span>
                )}
              </div>
            </div>
          )}

          {/* STEP 3: MEASUREMENT PLAN */}
          {activeStep === 'plan' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="workflow-card">
                <div style={{ fontWeight: 700, color: 'var(--brand-purple, #6f3dba)', fontSize: '0.88rem' }}>
                  Operational Measurement Plan Governance (IPMVP Standard)
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: 1.45 }}>
                  Changes intended to reduce electricity during line stoppages evaluate two independent boundaries:
                  <strong> Boundary A (Stoppage Period)</strong> and <strong>Boundary B (Restart &amp; Productive Shift)</strong>.
                  Plans must be frozen before physical enactment. Post-outcome plans are classified as <em>Retrospective analysis</em>.
                </div>
              </div>

              {plan ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: '0.95rem' }}>
                        Measurement &amp; Verification Plan: {plan.plan_id} (Revision {plan.version})
                      </h4>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Status: {plan.is_frozen ? 'Frozen Contract' : 'Draft Plan'} • {plan.is_retrospective ? 'Retrospective analysis' : 'Prospective Approved Plan'}
                        {plan.has_dual_boundary && ' • Dual Boundary (Stoppage + Restart)'}
                      </span>
                    </div>
                  </div>

                  {plan.has_dual_boundary && (
                    <div style={{ padding: '0.75rem', background: 'rgba(59, 130, 246, 0.08)', borderRadius: '6px', border: '1px solid rgba(59, 130, 246, 0.25)', fontSize: '0.8rem' }}>
                      <strong style={{ color: '#2563eb' }}>Dual Boundary Architecture Active:</strong>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.5rem', marginTop: '0.35rem' }}>
                        <div><strong>Boundary A (Stoppage):</strong> Standby and idle electrical draw during non-operating intervals.</div>
                        <div><strong>Boundary B (Restart &amp; Shift):</strong> Restart duration, scrap ceiling, downtime, and cost per good unit.</div>
                      </div>
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
                    <div className="workflow-card">
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Baseline Window [start, end)</span>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{formatDateTime(plan.baseline_start)} to {formatDateTime(plan.baseline_end)}</div>
                    </div>
                    <div className="workflow-card">
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Post Window [start, end)</span>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{formatDateTime(plan.post_start)} to {formatDateTime(plan.post_end)}</div>
                    </div>
                    <div className="workflow-card">
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Comparison Method &amp; Coverage</span>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{plan.comparison_method || 'MATCHED_SCHEDULE'} (Min {plan.min_coverage_pct}%)</div>
                    </div>
                  </div>

                  {/* Preapproved Guardrails Grid */}
                  <div className="workflow-card">
                    <h5 style={{ margin: 0, fontSize: '0.85rem' }}>Preapproved Production, Quality &amp; Restart Guardrails</h5>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.6rem', fontSize: '0.8rem' }}>
                      <div style={{ padding: '0.5rem', background: 'var(--bg-surface)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Output Guardrail (At least)</span>
                        <div style={{ fontWeight: 700 }}>&ge; {plan.guardrail_output_min || 0} {plan.guardrail_output_unit}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          Reason: {plan.guardrail_output_reason || 'Maintain delivery rate'}
                        </div>
                      </div>
                      <div style={{ padding: '0.5rem', background: 'var(--bg-surface)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Rejects / Quality (At most)</span>
                        <div style={{ fontWeight: 700 }}>&le; {plan.guardrail_reject_max ?? 0} {plan.guardrail_reject_unit}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          Reason: {plan.guardrail_reject_reason || 'QA scrap ceiling'}
                        </div>
                      </div>
                      <div style={{ padding: '0.5rem', background: 'var(--bg-surface)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Downtime (At most)</span>
                        <div style={{ fontWeight: 700 }}>&le; {plan.guardrail_downtime_max_min ?? 0} {plan.guardrail_downtime_unit}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          Reason: {plan.guardrail_downtime_reason || 'Changeover buffer'}
                        </div>
                      </div>
                      <div style={{ padding: '0.5rem', background: 'var(--bg-surface)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Restart Duration (At most)</span>
                        <div style={{ fontWeight: 700 }}>&le; {plan.guardrail_restart_max_min ?? 15} {plan.guardrail_restart_unit || 'minutes'}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          Reason: {plan.guardrail_restart_reason || 'Ramp-up envelope'}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="workflow-card">
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Success Criterion Claim</span>
                    <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{plan.success_criterion}</div>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  {/* Energy-Saving Trial Auto-Draft Option */}
                  {action.recommendation_id && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(59, 130, 246, 0.08)', padding: '0.65rem 0.85rem', borderRadius: '6px', border: '1px solid rgba(59, 130, 246, 0.25)', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <div>
                        <strong style={{ color: '#2563eb', fontSize: '0.82rem' }}>⚡ Energy-Saving Trial Measurement Plan</strong>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>Auto-populate prospective trial parameters, dual-boundary windows and production guardrails.</div>
                      </div>
                      <button
                        type="button"
                        className="workflow-btn workflow-btn-secondary"
                        style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem', borderColor: '#3b82f6', color: '#1d4ed8', background: '#fff', fontWeight: 600 }}
                        onClick={handleAutoDraftTrialPlan}
                        disabled={draftingTrialPlan}
                      >
                        {draftingTrialPlan ? '⚡ Drafting Trial Plan...' : '⚡ Auto-Draft Trial Plan'}
                      </button>
                    </div>
                  )}

                  {/* Trial Suitability Notice if break < restart or missing equipment */}
                  {trialSuitabilityNotice && (
                    <div style={{ padding: '0.65rem 0.85rem', background: trialSuitabilityNotice.status === 'UNSUITABLE_FOR_TRIAL' ? '#fef2f2' : '#fffbeb', borderRadius: '6px', border: `1px solid ${trialSuitabilityNotice.status === 'UNSUITABLE_FOR_TRIAL' ? '#fecaca' : '#fde68a'}`, fontSize: '0.78rem', color: trialSuitabilityNotice.status === 'UNSUITABLE_FOR_TRIAL' ? '#b91c1c' : '#92400e' }}>
                      <strong>{trialSuitabilityNotice.status === 'UNSUITABLE_FOR_TRIAL' ? 'Trial Unsuitable: ' : 'Evidence Gathering: '}</strong>
                      {trialSuitabilityNotice.reason || trialSuitabilityNotice.auditRecommendation}
                    </div>
                  )}

                  {/* AI Agent Proposed Operating Change & Guardrail Conditions */}
                  {draftTrialDetails && draftTrialDetails.operatingWindow && (
                    <div style={{ padding: '0.75rem 0.9rem', background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '0.78rem', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 700, color: '#1e293b' }}>
                          ⚡ AI Proposed Operating Change &amp; Conditions:
                        </span>
                        {draftTrialDetails.inferenceSource === 'DOMO_AI_MODEL' ? (
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, padding: '0.15rem 0.45rem', background: '#ecfdf5', color: '#065f46', borderRadius: '4px', border: '1px solid #a7f3d0' }}>
                            Live AI · Domo AI
                          </span>
                        ) : (
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, padding: '0.15rem 0.45rem', background: '#fef3c7', color: '#92400e', borderRadius: '4px', border: '1px solid #fde68a' }}>
                            Rule-Based Fallback
                          </span>
                        )}
                      </div>
                      <div><strong>Operating Window:</strong> {draftTrialDetails.operatingWindow}</div>
                      {draftTrialDetails.whySavesElectricity && (
                        <div><strong>Why it Saves Electricity:</strong> {draftTrialDetails.whySavesElectricity}</div>
                      )}
                      {draftTrialDetails.productionDependencies && (
                        <div><strong>Production Dependencies:</strong> {draftTrialDetails.productionDependencies}</div>
                      )}
                      {draftTrialDetails.restartRequirements && (
                        <div><strong>Restart Requirements:</strong> {draftTrialDetails.restartRequirements}</div>
                      )}
                      {draftTrialDetails.stopConditions && (
                        <div style={{ color: '#b91c1c' }}><strong>Stop Conditions:</strong> {draftTrialDetails.stopConditions}</div>
                      )}
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.5rem', padding: '0.6rem 0.8rem', background: 'var(--bg-surface-elevated)', borderRadius: '6px', fontSize: '0.78rem' }}>
                    <div>Plant: <strong>{action.plant_id || 'N/A'}</strong></div>
                    <div>Line: <strong>{getResolvedLineDisplay(action.plant_id, action.affected_equipment)}</strong></div>
                    <div>Meter: <strong>{action.measurement_meter_id || action.affected_equipment || 'MTR-COMPRESSOR'}</strong></div>
                    <div>Scope: <strong>{getResolvedLineDisplay(action.plant_id, action.affected_equipment) === 'Line unassigned' ? 'Utility-meter scope' : 'Production-line process scope'}</strong></div>
                    <div>Owner: <strong>{action.owner || 'Facilities Engineering'}</strong></div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Baseline Start [start, end)</label>
                      <input
                        type="datetime-local"
                        value={baselineStart}
                        onChange={(e) => setBaselineStart(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Baseline End</label>
                      <input
                        type="datetime-local"
                        value={baselineEnd}
                        onChange={(e) => setBaselineEnd(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Post-Intervention Start</label>
                      <input
                        type="datetime-local"
                        value={postStart}
                        onChange={(e) => setPostStart(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Post-Intervention End</label>
                      <input
                        type="datetime-local"
                        value={postEnd}
                        onChange={(e) => setPostEnd(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Comparison Method</label>
                      <select
                        value={comparisonMethod}
                        onChange={(e) => setComparisonMethod(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                      >
                        <option value="DUAL_STOPPAGE_AND_RESTART">DUAL_STOPPAGE_AND_RESTART — Dual Boundary Stoppage Reduction &amp; Restart Overhead</option>
                        <option value="MATCHED_SCHEDULE">MATCHED_SCHEDULE — Equivalent operating shift hours</option>
                        <option value="IDENTICAL_HOUR_OF_WEEK">IDENTICAL_HOUR_OF_WEEK — Matched calendar weekday/hour</option>
                        <option value="EQUIVALENT_RUN_RATE">EQUIVALENT_RUN_RATE — Matched throughput envelope</option>
                        <option value="REPEATED_STOPPAGES_DEDICATED_METER_V1">REPEATED_STOPPAGES_DEDICATED_METER_V1 — Repeated stoppages on dedicated process meter</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Minimum Required Coverage (%)</label>
                      <input
                        type="number"
                        min="50"
                        max="100"
                        value={minCoveragePct}
                        onChange={(e) => setMinCoveragePct(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                  </div>

                  <div className="workflow-card">
                    <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>Guardrails Configuration</span>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                      <div>
                        <label style={{ fontSize: '0.75rem', fontWeight: 600 }}>Min Good Output (Units &ge; Target)</label>
                        <input
                          type="number"
                          value={guardrailOutputMin}
                          onChange={(e) => setGuardrailOutputMin(e.target.value)}
                          style={{ width: '100%', padding: '0.4rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                          required
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: '0.75rem', fontWeight: 600 }}>Max Rejects (Units &le; Ceiling)</label>
                        <input
                          type="number"
                          value={guardrailRejectMax}
                          onChange={(e) => setGuardrailRejectMax(e.target.value)}
                          style={{ width: '100%', padding: '0.4rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                          required
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: '0.75rem', fontWeight: 600 }}>Max Downtime (Min &le; Allowance)</label>
                        <input
                          type="number"
                          value={guardrailDowntimeMax}
                          onChange={(e) => setGuardrailDowntimeMax(e.target.value)}
                          style={{ width: '100%', padding: '0.4rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                          required
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: '0.75rem', fontWeight: 600 }}>Max Restart Duration (Min &le; Target)</label>
                        <input
                          type="number"
                          value={guardrailRestartMax}
                          onChange={(e) => setGuardrailRestartMax(e.target.value)}
                          style={{ width: '100%', padding: '0.4rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                          required
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Success Criterion (Exact Objective Claim)</label>
                    <input
                      type="text"
                      value={successCriterion}
                      onChange={(e) => setSuccessCriterion(e.target.value)}
                      style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                      required
                    />
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <input
                      type="checkbox"
                      id="retroCheck"
                      checked={isRetrospective}
                      onChange={(e) => setIsRetrospective(e.target.checked)}
                    />
                    <label htmlFor="retroCheck" style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      Mark explicitly as <strong>Retrospective analysis</strong> (if post window occurred prior to plan definition)
                    </label>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 4: PHYSICAL IMPLEMENTATION */}
          {activeStep === 'implement' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              {action.implemented_at ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <div style={{ padding: '0.9rem 1.1rem', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid #10b981', borderRadius: '8px' }}>
                    <h4 style={{ margin: '0 0 0.4rem', color: '#059669', fontSize: '0.95rem' }}>Implementation Recorded</h4>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.5rem' }}>
                      <div><strong>Timestamp:</strong> {formatDateTime(action.implemented_at)}</div>
                      <div><strong>Implemented By:</strong> {action.implemented_by || 'Unspecified'}</div>
                      <div style={{ gridColumn: '1 / -1' }}><strong>Notes:</strong> {action.implementation_notes || 'None'}</div>
                    </div>
                  </div>

                  {assessment?.work_order_link && (
                    <div className="workflow-card">
                      <strong>Linked Maintenance Work Order:</strong> {assessment.work_order_link.work_order_id} ({assessment.work_order_link.maintenance_type})
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.2rem' }}>
                        {assessment.work_order_link.note}
                      </div>
                    </div>
                  )}

                  {assessment?.downtime_event_link && (
                    <div className="workflow-card">
                      <strong>Linked Downtime Event:</strong> {assessment.downtime_event_link.downtime_id} ({assessment.downtime_event_link.reason_code}, {assessment.downtime_event_link.duration_min} min)
                    </div>
                  )}

                  {assessment?.is_awaiting_data && (
                    <div className="workflow-compact-notice warning">
                      <strong>Awaiting Post-Action Data:</strong> Approximately {assessment.remaining_time_minutes} minutes remaining in observation window.
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div className="workflow-card">
                    <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                      <strong>Strict Rule:</strong> Approval alone cannot begin the post-intervention period. An actual physical implementation timestamp and genuine operator identity are required before evaluating an outcome.
                    </p>
                  </div>

                  {action.review_status !== 'APPROVED' && (
                    <div className="workflow-alert-error">
                      Cannot record implementation: Proposal must be APPROVED first in Step 2.
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Actual Implementation Timestamp</label>
                      <input
                        type="datetime-local"
                        value={implementedAt}
                        onChange={(e) => setImplementedAt(e.target.value)}
                        disabled={action.review_status !== 'APPROVED'}
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Implemented By (Genuine Operator / Team)</label>
                      <input
                        type="text"
                        value={implementedBy}
                        onChange={(e) => setImplementedBy(e.target.value)}
                        disabled={action.review_status !== 'APPROVED'}
                        placeholder="e.g. Facilities Lead - A. Sharma"
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        required
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                        Linked CMMS Work Order (Optional)
                      </label>
                      <input
                        type="text"
                        value={workOrderId}
                        onChange={(e) => setWorkOrderId(e.target.value)}
                        disabled={action.review_status !== 'APPROVED'}
                        placeholder="e.g. MWO-00001"
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                        Linked Downtime Event ID (Optional)
                      </label>
                      <input
                        type="text"
                        value={downtimeEventId}
                        onChange={(e) => setDowntimeEventId(e.target.value)}
                        disabled={action.review_status !== 'APPROVED'}
                        placeholder="e.g. DT-000001"
                        style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                      />
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Physical Implementation Notes</label>
                    <textarea
                      rows={3}
                      value={implementationNotes}
                      onChange={(e) => setImplementationNotes(e.target.value)}
                      disabled={action.review_status !== 'APPROVED'}
                      placeholder="Describe the physical state changes made on the equipment..."
                      style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                      required
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 5: VERIFICATION ASSESSMENT */}
          {activeStep === 'assessment' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              {!action.implemented_at ? (
                <div style={{ padding: '2rem 1.5rem', textAlign: 'center', background: 'var(--bg-surface-elevated)', borderRadius: '8px' }}>
                  <h4 style={{ margin: '0 0 0.5rem', color: '#ef4444' }}>Outcome Assessment Unavailable</h4>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Physical implementation has not yet been recorded. An implementation timestamp is required before the post-intervention period can be evaluated.
                  </p>
                </div>
              ) : !assessment ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <p style={{ marginBottom: '1rem', color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
                    Implementation recorded for {formatDateTime(action.implemented_at)}. Run the deterministic before/after verification model.
                  </p>
                  <button type="button" className="workflow-btn workflow-btn-primary" onClick={handleEvaluateAssessment} disabled={loading}>
                    {loading ? 'Executing Deterministic Comparison…' : 'Run Deterministic Outcome Assessment'}
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  {/* Lead with Plain-Language Management Outcome */}
                  <div style={{
                    padding: '0.95rem 1.15rem',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    background: assessment.management_outcome === 'Verified intervention improvement'
                      ? 'rgba(16, 185, 129, 0.1)'
                      : assessment.management_outcome === 'Eligible for verification — awaiting reviewer'
                        ? 'rgba(59, 130, 246, 0.1)'
                        : (assessment.management_outcome?.includes('breached') || assessment.management_outcome?.includes('not met')
                          ? 'rgba(239, 68, 68, 0.08)'
                          : 'rgba(245, 158, 11, 0.08)'),
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.35rem' }}>
                      <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, color: 'var(--text-muted)' }}>
                        Plain-Language Management Outcome
                      </span>
                      <span
                        className="workflow-badge"
                        style={{
                          fontSize: '0.78rem',
                          background: assessment.management_outcome === 'Verified intervention improvement' ? '#10b981' : '#2563eb',
                          color: '#fff',
                        }}
                      >
                        {assessment.management_outcome || assessment.objective_outcome}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.92rem', color: 'var(--text-primary)', fontWeight: 550, lineHeight: 1.4 }}>
                      {assessment.management_outcome_detail || assessment.status_reason}
                    </div>

                    {assessment.server_timing_reason && (
                      <div style={{ marginTop: '0.45rem', fontSize: '0.78rem', color: assessment.server_timing_verified ? '#10b981' : '#f59e0b', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <span>⏱</span>
                        <strong>Server Timing:</strong> {assessment.server_timing_reason}
                      </div>
                    )}
                  </div>

                  {/* Three Authoritative Assessment Answers Grid */}
                  <div className="workflow-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.4rem' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                        Three Authoritative Assessment Answers
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Boundary: Meter {action.measurement_meter_id || action.affected_equipment || 'MTR-COMPRESSOR'} · Line {getResolvedLineDisplay(action.plant_id, action.affected_equipment)}
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.65rem' }}>
                      <div style={{ padding: '0.75rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                          1. Did electricity cost / good unit fall?
                        </div>
                        <div style={{
                          fontWeight: 700,
                          fontSize: '1rem',
                          color: assessment.objective_outcome === 'IMPROVED' ? '#10b981' : (assessment.objective_outcome === 'NOT_IMPROVED' ? '#ef4444' : '#f59e0b')
                        }}>
                          {assessment.objective_outcome}
                          <span style={{ fontSize: '0.8rem', fontWeight: 500, marginLeft: '0.4rem', color: 'var(--text-secondary)' }}>
                            ({assessment.cost_intensity_change_pct !== null && assessment.cost_intensity_change_pct !== undefined ? `${assessment.cost_intensity_change_pct}%` : 'N/A'})
                          </span>
                        </div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                          Baseline: <strong>{assessment.baseline?.cost_per_good_unit ? `₹${assessment.baseline.cost_per_good_unit}/unit` : '0 units'}</strong> · Post: <strong>{assessment.post?.cost_per_good_unit ? `₹${assessment.post.cost_per_good_unit}/unit` : 'N/A'}</strong>
                        </div>
                      </div>

                      <div style={{ padding: '0.75rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                          2. Were production and quality protected?
                        </div>
                        <div style={{
                          fontWeight: 700,
                          fontSize: '1rem',
                          color: assessment.production_protection_status === 'PROTECTED' ? '#10b981' : (assessment.production_protection_status === 'UNASSESSABLE' ? '#f59e0b' : '#ef4444')
                        }}>
                          {assessment.production_protection_status}
                        </div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                          {assessment.guardrails?.filter((g) => g.passed).length || 0} of {assessment.guardrails?.length || 0} limits passed.
                        </div>
                      </div>

                      <div style={{ padding: '0.75rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                          3. How much is attributable to action?
                        </div>
                        <div style={{
                          fontWeight: 700,
                          fontSize: '1rem',
                          color: (assessment.verified_electricity_savings_kwh || assessment.electricity_savings_kwh) ? '#10b981' : 'var(--text-muted)'
                        }}>
                          {(assessment.verified_electricity_savings_kwh || assessment.electricity_savings_kwh)
                            ? `${formatNumber(assessment.verified_electricity_savings_kwh || assessment.electricity_savings_kwh)} kWh`
                            : 'No verified savings'}
                        </div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                          {assessment.verified_monetary_savings_inr ? (
                            <span style={{ color: '#10b981', fontWeight: 600 }}>Verified: {formatCurrency(assessment.verified_monetary_savings_inr)}</span>
                          ) : assessment.avoided_cost_inr ? (
                            <span>Est avoided: {formatCurrency(assessment.avoided_cost_inr)} (Pending contract approval)</span>
                          ) : (
                            'Attribution unverified.'
                          )}
                        </div>
                        {assessment.attribution_details && (
                          <div style={{ marginTop: '0.35rem', fontSize: '0.7rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-color)', paddingTop: '0.25rem' }}>
                            Method: {assessment.attribution_details.attribution_method} · Pool: {assessment.attribution_details.reference_pool_count} eps · CV: {assessment.attribution_details.baseline_cv_pct}% · Band: ±{assessment.attribution_details.uncertainty_pct}%
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Side-by-Side Comparison Table */}
                  <div style={{ overflowX: 'auto', border: '1px solid var(--border-color)', borderRadius: '6px' }}>
                    <table className="iac-table" style={{ width: '100%', fontSize: '0.82rem' }}>
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Baseline Period</th>
                          <th>Post-Intervention</th>
                          <th>Change / Impact</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><strong>Electricity (kWh)</strong></td>
                          <td>{formatNumber(assessment.baseline?.kwh)} kWh</td>
                          <td>{formatNumber(assessment.post?.kwh)} kWh</td>
                          <td>{assessment.kwh_change_abs > 0 ? `+${assessment.kwh_change_abs}` : assessment.kwh_change_abs} kWh ({assessment.kwh_change_pct}%)</td>
                        </tr>
                        <tr>
                          <td><strong>Estimated Cost (₹)</strong></td>
                          <td>{formatCurrency(assessment.baseline?.cost_inr)}</td>
                          <td>{formatCurrency(assessment.post?.cost_inr)}</td>
                          <td>{formatCurrency((assessment.post?.cost_inr || 0) - (assessment.baseline?.cost_inr || 0))}</td>
                        </tr>
                        <tr>
                          <td><strong>Good Finished Output</strong></td>
                          <td>{formatNumber(assessment.baseline?.good_units)} units</td>
                          <td>{formatNumber(assessment.post?.good_units)} units</td>
                          <td>{(assessment.post?.good_units || 0) - (assessment.baseline?.good_units || 0)} units</td>
                        </tr>
                        <tr>
                          <td><strong>Cost Intensity</strong></td>
                          <td>{assessment.baseline?.cost_per_good_unit ? `₹${assessment.baseline.cost_per_good_unit}/unit` : 'Undefined'}</td>
                          <td>{assessment.post?.cost_per_good_unit ? `₹${assessment.post.cost_per_good_unit}/unit` : 'N/A'}</td>
                          <td style={{ color: (assessment.cost_intensity_change_pct || 0) <= 0 ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                            {assessment.cost_intensity_change_pct ? `${assessment.cost_intensity_change_pct}%` : 'N/A'}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Rejects / Scrap</strong></td>
                          <td>{assessment.baseline?.reject_units ?? 0} units</td>
                          <td>{assessment.post?.reject_units ?? 0} units</td>
                          <td>{(assessment.post?.reject_units || 0) - (assessment.baseline?.reject_units || 0)} units</td>
                        </tr>
                        <tr>
                          <td><strong>Operational Downtime</strong></td>
                          <td>{assessment.baseline?.downtime_minutes ?? 0} min</td>
                          <td>{assessment.post?.downtime_minutes ?? 0} min</td>
                          <td>{(assessment.post?.downtime_minutes || 0) - (assessment.baseline?.downtime_minutes || 0)} min</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {/* Dual Boundary Linked Stoppage & Restart Breakdown */}
                  {assessment.has_dual_boundary && assessment.dual_boundary_breakdown && (
                    <div className="workflow-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h5 style={{ margin: 0, fontSize: '0.86rem' }}>Dual Boundary Assessment: Stoppage &amp; Restart</h5>
                        <span style={{ fontSize: '0.72rem', padding: '0.15rem 0.45rem', background: 'rgba(59, 130, 246, 0.12)', color: '#2563eb', borderRadius: '4px', fontWeight: 600 }}>
                          Evaluated Together · No Double Counting
                        </span>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.5rem', fontSize: '0.8rem' }}>
                        <div><strong>Boundary A (Stoppage):</strong> Change of {assessment.dual_boundary_breakdown.boundary_a_stoppage.kwh_change} kWh</div>
                        <div><strong>Boundary B (Restart Overhead):</strong> +{assessment.dual_boundary_breakdown.boundary_b_restart_shift.restart_overhead_kwh} kWh</div>
                      </div>
                    </div>
                  )}

                  {/* AI Assistant Assessment Explanation */}
                  <div className="workflow-card" style={{ border: '1px solid #8b5cf6', background: 'rgba(139, 92, 246, 0.03)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: '1rem' }}>⚡</span>
                        <h5 style={{ margin: 0, fontSize: '0.88rem', fontWeight: 700, color: '#6d28d9' }}>
                          Industrial Energy Assistant · Assessment Synthesis
                        </h5>
                      </div>
                      <button
                        type="button"
                        className="workflow-btn workflow-btn-secondary"
                        onClick={handleExplainAssessmentWithAi}
                        disabled={explainingAssessment}
                        style={{ fontSize: '0.76rem', padding: '0.3rem 0.65rem', background: '#8b5cf6', color: '#fff', border: 'none' }}
                      >
                        {explainingAssessment ? 'Synthesizing...' : (assessmentExplanation ? '↻ Refresh AI Explanation' : '⚡ Explain Assessment with AI')}
                      </button>
                    </div>

                    {explainError && (
                      <div style={{ padding: '0.5rem', background: 'rgba(239, 68, 68, 0.1)', color: '#dc2626', borderRadius: '4px', fontSize: '0.78rem', marginBottom: '0.5rem' }}>
                        {explainError}
                      </div>
                    )}

                    {assessmentExplanation ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                          <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Overall Assessment Verdict:</span>
                          <span style={{
                            fontSize: '0.78rem',
                            fontWeight: 700,
                            padding: '0.2rem 0.6rem',
                            borderRadius: '4px',
                            background: assessmentExplanation.overall_verdict?.includes('Verified') ? 'rgba(16, 185, 129, 0.15)' : (assessmentExplanation.overall_verdict?.includes('Breached') ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)'),
                            color: assessmentExplanation.overall_verdict?.includes('Verified') ? '#059669' : (assessmentExplanation.overall_verdict?.includes('Breached') ? '#dc2626' : '#d97706')
                          }}>
                            {assessmentExplanation.overall_verdict}
                          </span>
                        </div>

                        {/* 3 Questions Grid */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.6rem' }}>
                          <div style={{ padding: '0.65rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontWeight: 600 }}>1. Cost Per Good Unit</div>
                            <div style={{ fontSize: '0.88rem', fontWeight: 700, margin: '0.2rem 0', color: assessmentExplanation.question_1_cost_intensity?.answer === 'YES' ? '#10b981' : (assessmentExplanation.question_1_cost_intensity?.answer === 'NO' ? '#ef4444' : 'var(--text-secondary)') }}>
                              Answer: {assessmentExplanation.question_1_cost_intensity?.answer}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                              {assessmentExplanation.question_1_cost_intensity?.explanation}
                            </div>
                          </div>

                          <div style={{ padding: '0.65rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontWeight: 600 }}>2. Production Protection</div>
                            <div style={{ fontSize: '0.88rem', fontWeight: 700, margin: '0.2rem 0', color: assessmentExplanation.question_2_production_protection?.status === 'PROTECTED' ? '#10b981' : (assessmentExplanation.question_2_production_protection?.status === 'BREACHED' ? '#ef4444' : 'var(--text-secondary)') }}>
                              Status: {assessmentExplanation.question_2_production_protection?.status} ({assessmentExplanation.question_2_production_protection?.answer})
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                              {assessmentExplanation.question_2_production_protection?.explanation}
                            </div>
                          </div>

                          <div style={{ padding: '0.65rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontWeight: 600 }}>3. Attributable Savings</div>
                            <div style={{ fontSize: '0.88rem', fontWeight: 700, margin: '0.2rem 0', color: assessmentExplanation.question_3_attribution?.status === 'ATTRIBUTED' ? '#10b981' : 'var(--text-muted)' }}>
                              Result: {assessmentExplanation.question_3_attribution?.answer}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                              {assessmentExplanation.question_3_attribution?.explanation}
                            </div>
                          </div>
                        </div>

                        {/* Ledger Eligibility Status */}
                        {assessmentExplanation.ledger_eligibility && (
                          <div style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-surface)', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.76rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span><strong>Factory Ledger Finalization Status:</strong> {assessmentExplanation.ledger_eligibility.savings_claim_status}</span>
                              <span style={{
                                fontWeight: 600,
                                color: assessmentExplanation.ledger_eligibility.is_eligible_for_verified_cost ? '#10b981' : '#f59e0b'
                              }}>
                                {assessmentExplanation.ledger_eligibility.is_eligible_for_verified_cost ? '✓ Verified Savings Ledger Eligible' : '⚠ Non-eligible for Monetary Ledger Post'}
                              </span>
                            </div>
                            <div style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                              kWh Criterion: {assessmentExplanation.ledger_eligibility.kwh_eligibility_reason} | Monetary: {assessmentExplanation.ledger_eligibility.monetary_eligibility_reason}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontStyle: 'italic', padding: '0.25rem 0' }}>
                        Click "Explain Assessment with AI" to generate an authoritative governance synthesis for production limits, cost intensity, and ledger attribution.
                      </div>
                    )}
                  </div>

                  {/* Expandable Evidence Toggle */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="workflow-btn workflow-btn-secondary"
                      onClick={() => setShowEvidence(!showEvidence)}
                      style={{ fontSize: '0.78rem', padding: '0.35rem 0.65rem' }}
                    >
                      {showEvidence ? 'Hide Detailed Evidence ▲' : 'Show Detailed Evidence & Accounting ▼'}
                    </button>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                      Reconciliation &amp; Audit Provenance
                    </span>
                  </div>

                  {/* Detailed Evidence Block */}
                  {showEvidence && (
                    <div className="workflow-card" style={{ fontSize: '0.8rem' }}>
                      <div>
                        <strong>Tariff &amp; Factor Traceability:</strong>
                        <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          Rate: ₹{assessment.common_rate_factor_inr_per_kwh}/kWh [{assessment.common_rate_factor_version}]
                        </div>
                      </div>
                      <div>
                        <strong>Interval Accounting:</strong>
                        <div style={{ marginTop: '0.2rem', color: 'var(--text-secondary)' }}>
                          Baseline Eligible Hours: {assessment.baseline?.complete_eligible_hours || 0} · Post Eligible Hours: {assessment.post?.complete_eligible_hours || 0}
                        </div>
                      </div>
                      {(assessment.work_order_link || assessment.downtime_event_link) && (
                        <div>
                          <strong>Physical Operational Linkage:</strong>
                          <div style={{ marginTop: '0.2rem', color: 'var(--text-secondary)' }}>
                            {assessment.work_order_link?.work_order_id} ({assessment.work_order_link?.maintenance_type})
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Reviewer Sign-Off Form */}
                  <div className="workflow-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h4 className="workflow-card-title">Authorized Reviewer Sign-Off &amp; Ledger Finalization</h4>
                      <span className="workflow-demo-tag">Demo mode</span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginTop: '0.35rem' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Reviewer Decision</label>
                        <select
                          value={signOffDecision}
                          onChange={(e) => setSignOffDecision(e.target.value)}
                          style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        >
                          <option value="APPROVED_VERIFIED">APPROVED_VERIFIED — Verify savings and finalize in ledger</option>
                          <option value="REJECTED">REJECTED — Reject verification claim</option>
                          <option value="REQUEST_REANALYSIS">REQUEST_REANALYSIS — Request updated baseline or period</option>
                        </select>
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem' }}>Sign-Off Notes</label>
                        <input
                          type="text"
                          value={signOffNotes}
                          onChange={(e) => setSignOffNotes(e.target.value)}
                          placeholder="Reviewer confirmation notes..."
                          style={{ width: '100%', padding: '0.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ROW 3: PERSISTENT FOOTER (Always visible, explicit actions, secondary navigation) */}
        <div className="workflow-modal-footer">
          <div className="workflow-footer-nav">
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={onClose}
            >
              Close
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={handlePrevStep}
              disabled={currentStepIndex === 0}
              aria-label="Previous Step"
            >
              ← Previous
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={handleNextStep}
              disabled={currentStepIndex === WORKFLOW_STEPS.length - 1}
              aria-label="Next Step"
            >
              Next →
            </button>
          </div>

          <div className="workflow-footer-actions">
            {renderPrimaryAction()}
          </div>
        </div>
      </div>
    </div>
  );
}
