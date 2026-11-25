import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { energyIntensityApi } from '../../services/energyIntensityApi';
import { formatNumber, formatCurrency } from '../../utils/formatters';

import stage1Img from '../../assets/pipeline/stage1-factory-inputs.png';
import stage2Img from '../../assets/pipeline/stage2-intake-storage.png';
import stage3Img from '../../assets/pipeline/stage3-energy-analysis.png';
import stage4Img from '../../assets/pipeline/Plant engineer reviewing a checklist.png';
import stage5Img from '../../assets/pipeline/stage5-assessment.png';

// 9 local row illustrations
import rowMeterReadingsImg from '../../assets/pipeline/rows/meter-readings.png';
import rowProductionLogsImg from '../../assets/pipeline/rows/production-logs.png';
import rowOperatingContextImg from '../../assets/pipeline/rows/operating-context.png';
import rowMatchPlantHoursImg from '../../assets/pipeline/rows/match-plant-hours.png';
import rowCalculateUnitCostImg from '../../assets/pipeline/rows/calculate-unit-cost.png';
import rowFlagUnusualUseImg from '../../assets/pipeline/rows/flag-unusual-use.png';
import rowComparePeriodsImg from '../../assets/pipeline/rows/compare-periods.png';
import rowCheckOutputImg from '../../assets/pipeline/rows/check-output.png';
import rowAssessSavingsImg from '../../assets/pipeline/rows/assess-savings.png';

/**
 * 5 System Architecture Stages Configuration
 */
const SYSTEM_STAGES = [
  {
    id: 1,
    number: '1',
    headerLabel: 'Factory inputs',
    headerSub: '(Data ingestion)',
    headerColor: '#b91c1c',
    image: stage1Img,
    fallbackImage: '/pipeline/stage1-factory-inputs.png',
    pictogram: 'factory',
    layoutType: 'rows',
    title: 'Factory inputs & operating context',
    badge: 'Stage 1 of 5',
    items: [
      {
        id: 'meter-readings',
        text: 'Meter readings',
        icon: 'zap',
        iconImg: rowMeterReadingsImg,
        fallbackImg: '/pipeline/rows/meter-readings.png',
        hint: 'Hourly kWh, PF, voltage',
        tint: 'tint-blue',
        explanation: [
          'In Daily Operations, the user selects a plant and date, then enters or pastes hourly electricity readings for a meter.',
          'After validation, the app saves those readings in PostgreSQL so energy analysis can compare electricity use with production for the same plant and hour.',
        ],
      },
      {
        id: 'production-logs',
        text: 'Production logs',
        icon: 'box',
        iconImg: rowProductionLogsImg,
        fallbackImg: '/pipeline/rows/production-logs.png',
        hint: 'Good units, scrap, downtime',
        tint: 'tint-green',
        explanation: [
          'In Daily Operations, the user enters hourly production output, good finished units, scrap, and stoppage time.',
          'The app stores these records to calculate unit electricity cost and protect production throughput against unverified savings claims.',
        ],
      },
      {
        id: 'operating-context',
        text: 'Operating context',
        icon: 'sliders',
        iconImg: rowOperatingContextImg,
        fallbackImg: '/pipeline/rows/operating-context.png',
        hint: 'Utility baseload, tariffs',
        tint: 'tint-purple',
        explanation: [
          'Defines plant working hours, shifts, baseline thresholds, and tariffs.',
          'Used to classify operating versus non-operating hours and convert energy use into electricity cost.',
        ],
      },
    ],
    explanation:
      'Factory energy telemetry, submeter hierarchy, hourly production logs, and utility operating context are aggregated from shop-floor CSV/XLSX reports across plants.',
    technicalDetails: {
      protocols: 'CSV / XLSX Daily Uploads · Multi-Meter Substation Telemetry',
      tables: ['dim_production_line', 'dim_energy_meter', 'upload_history'],
    },
    flowHeading: 'Execution Logic & Operational Flow:',
    workflow: [
      { step: 1, title: 'Energy Telemetry Feeds', desc: 'Submeter monitoring across 5 plant processes (MTR-SMT, MTR-FAL, MTR-HVAC, MTR-CHILLER, MTR-COMPRESSOR).' },
      { step: 2, title: 'Production Records', desc: 'Captures hourly line-level good output, scrap rejects, rework, and downtime by shift.' },
      { step: 3, title: 'Operating Context', desc: 'Centralized utility baseload boundaries and tariff factor assumptions.' },
    ],
    linkText: 'Open Daily Operations',
    linkRoute: '/daily-operations',
  },
  {
    id: 2,
    number: '2',
    headerLabel: 'Intake & storage',
    headerSub: '(Storage & lineage)',
    headerColor: '#1d4ed8',
    image: stage2Img,
    fallbackImage: '/pipeline/stage2-intake-storage.png',
    pictogram: 'database',
    layoutType: 'illustration',
    title: 'Intake validation & atomic storage',
    badge: 'Stage 2 of 5',
    items: [
      {
        id: 'validate-entries',
        text: 'Validate entries',
        icon: 'shield-check',
        hint: 'Bounds, monotonicity, schema',
        tint: 'tint-blue',
        explanation: [
          'In Daily Operations, the user triggers validation after data entry.',
          'The app verifies that readings are within physical limits, non-negative, and continuous before any record is stored.',
        ],
      },
      {
        id: 'store-postgresql',
        text: 'Store in PostgreSQL',
        icon: 'database',
        hint: 'Immutable star schema tables',
        tint: 'tint-cyan',
        explanation: [
          'Commits validated readings to the database.',
          'These records populate the dashboard, the energy heatmap, and the investigation centre.',
        ],
      },
    ],
    explanation:
      'FastAPI executes two-stage schema, voltage, and power factor validation before atomically committing confirmed readings and their source revisions to PostgreSQL.',
    technicalDetails: {
      protocols: 'Two-Stage Schema Validator · Ingestion Error Remediation · FastAPI Upload',
      tables: ['fact_energy_meter_hourly', 'fact_hourly_production', 'upload_history'],
    },
    flowHeading: 'Execution Logic & Operational Flow:',
    workflow: [
      { step: 1, title: 'Pre-Ingestion Guard', desc: 'Enforces mandatory headers, voltage (415±10% V), power factor (0.0–1.0), and physical electrical bounds.' },
      { step: 2, title: 'Timestamp Monotonicity', desc: 'Verifies strictly monotonic hourly intervals and detects missing or conflicting records.' },
      { step: 3, title: 'Atomic Commit & Lineage', desc: 'Commits with immutable upload_id and sha256 file provenance hash for 100% forensic auditability.' },
    ],
    linkText: 'Open Upload Validation',
    linkRoute: '/daily-operations',
  },
  {
    id: 3,
    number: '3',
    headerLabel: 'Energy analysis',
    headerSub: '(Anomaly surveillance)',
    headerColor: '#6b21a8',
    image: stage3Img,
    fallbackImage: '/pipeline/stage3-energy-analysis.png',
    pictogram: 'chart',
    layoutType: 'rows',
    title: 'Energy analysis & anomaly surveillance',
    badge: 'Stage 3 of 5',
    items: [
      {
        id: 'match-plant-hours',
        text: 'Match plant hours',
        icon: 'clock',
        iconImg: rowMatchPlantHoursImg,
        fallbackImg: '/pipeline/rows/match-plant-hours.png',
        hint: 'Temporal coverage audit',
        tint: 'tint-purple',
        explanation: [
          'Aligns hourly electricity consumption with production logs for the same timestamp so energy use is assessed only during active operational hours.',
        ],
      },
      {
        id: 'calculate-unit-cost',
        text: 'Calculate unit cost',
        icon: 'calculator',
        iconImg: rowCalculateUnitCostImg,
        fallbackImg: '/pipeline/rows/calculate-unit-cost.png',
        hint: 'kWh & ₹ per good unit',
        tint: 'tint-cyan',
        explanation: [
          'Calculates electricity cost per good unit, specific energy consumption (SEC), and cost per operating hour from the active filters.',
        ],
      },
      {
        id: 'flag-unusual-use',
        text: 'Flag unusual use',
        icon: 'activity',
        iconImg: rowFlagUnusualUseImg,
        fallbackImg: '/pipeline/rows/flag-unusual-use.png',
        hint: 'Z-score, standby, low PF',
        tint: 'tint-amber',
        explanation: [
          'Flags baseload spikes, standby consumption during zero-production hours, and low power factor (< 0.90) as active findings.',
        ],
      },
    ],
    explanation:
      'Matches electricity with production by plant and hour, calculates Specific Energy Consumption (SEC) per good finished unit, and runs multi-algorithm anomaly surveillance.',
    technicalDetails: {
      protocols: 'Hourly Plant Reconciler · Multi-Algorithm Anomaly Detectors · Z-Score Surveillance',
      tables: ['fact_energy_meter_hourly', 'fact_hourly_production', 'fact_utility_telemetry_hourly'],
    },
    flowHeading: 'Execution Logic & Operational Flow:',
    workflow: [
      { step: 1, title: 'Temporal Alignment', desc: 'Joins meter telemetry with line output on exact plant-hours with complete coverage verification.' },
      { step: 2, title: 'Specific Energy Consumption', desc: 'Formulates kWh, dataset-derived cost, and emissions per good unit without Cartesian inflation.' },
      { step: 3, title: 'Multi-Detector Surveillance', desc: 'Flags statistical Z-score spikes, rolling baseline shifts, power factor deficits, and zero-production standby energy.' },
    ],
    linkText: 'Open Energy Analytics',
    linkRoute: '/energy-analytics',
  },
  {
    id: 4,
    number: '4',
    headerLabel: 'Human review',
    headerSub: '(M&V governance)',
    headerColor: '#3730a3',
    image: stage4Img,
    fallbackImage: '/pipeline/Plant engineer reviewing a checklist.png',
    pictogram: 'people',
    layoutType: 'illustration',
    title: 'Human review & M&V plan approval',
    badge: 'Stage 4 of 5',
    items: [
      {
        id: 'review-findings',
        text: 'Review findings',
        icon: 'search',
        hint: 'Trace telemetry provenance',
        tint: 'tint-blue',
        explanation: [
          'In the Investigation Centre, the plant engineer reviews flagged anomalies, checks telemetry evidence, and adds investigation notes before acting.',
        ],
      },
      {
        id: 'approve-action',
        text: 'Approve action',
        icon: 'user-check',
        hint: 'Assign engineering tasks',
        tint: 'tint-green',
        explanation: [
          'When a finding warrants action, the engineer documents the planned corrective measure and commits it to the audit log.',
        ],
      },
    ],
    explanation:
      'Facilities and Production engineers investigate detected findings, agree on corrective actions, and freeze prospective measurement plans with preapproved operational limits.',
    technicalDetails: {
      protocols: 'Investigation Centre · M&V Governance Protocol · Role-Based Sign-Off Gate',
      tables: ['operational_findings', 'corrective_actions', 'intervention_plans'],
    },
    flowHeading: 'Execution Logic & Operational Flow:',
    workflow: [
      { step: 1, title: 'Finding Investigation', desc: 'Engineers review telemetry provenance, Z-score deviation, and affected equipment.' },
      { step: 2, title: 'Action Formulation', desc: 'Facilities and Production assign ownership and define the physical modification.' },
      { step: 3, title: 'Measurement Plan Freeze', desc: 'Pre-approves baseline/post evaluation windows and non-zero guardrails before implementation.' },
    ],
    linkText: 'Open Investigation Centre',
    linkRoute: '/investigation-actions',
  },
  {
    id: 5,
    number: '5',
    headerLabel: 'Assessment',
    headerSub: '(Savings verification)',
    headerColor: '#881337',
    image: stage5Img,
    fallbackImage: '/pipeline/stage5-assessment.png',
    pictogram: 'checklist',
    layoutType: 'rows',
    title: 'Action assessment & savings verification',
    badge: 'Stage 5 of 5',
    items: [
      {
        id: 'compare-periods',
        text: 'Compare periods',
        icon: 'columns',
        iconImg: rowComparePeriodsImg,
        fallbackImg: '/pipeline/rows/compare-periods.png',
        hint: 'Half-open window intervals',
        tint: 'tint-amber',
        explanation: [
          'Compares electricity use and production between pre-intervention and post-intervention periods using matching operational conditions.',
        ],
      },
      {
        id: 'check-output',
        text: 'Check output',
        icon: 'check-circle-2',
        iconImg: rowCheckOutputImg,
        fallbackImg: '/pipeline/rows/check-output.png',
        hint: 'Evaluate 4 guardrails',
        tint: 'tint-green',
        explanation: [
          'Confirms that production throughput, good units, and product quality did not drop before attributing lower energy use to an efficiency gain.',
        ],
      },
      {
        id: 'assess-savings',
        text: 'Assess savings',
        icon: 'award',
        iconImg: rowAssessSavingsImg,
        fallbackImg: '/pipeline/rows/assess-savings.png',
        hint: 'Counterfactual attribution',
        tint: 'tint-rose',
        explanation: [
          'Reconciles verified electricity reduction against baseline tariffs to compute audited financial savings and update the ledger.',
        ],
      },
    ],
    explanation:
      'Facilities and Production compare electricity use before and after a recorded action, check output and quality, and review the evidence for any savings claim.',
    technicalDetails: {
      protocols: 'Deterministic Before/After Comparison · Repeated Stoppages Attribution · ISO 50015 Protocol',
      tables: ['intervention_plans', 'intervention_assessments', 'fact_energy_meter_hourly'],
    },
    flowHeading: 'Execution Logic & Operational Decisions (Three Separate Answers):',
    workflow: [
      {
        step: 1,
        title: 'Cost per good unit',
        desc: 'Did electricity cost per good unit decrease over comparable productive periods? Evaluates active manufacturing windows; if baseline output is zero, cost intensity is mathematically undefined (INCONCLUSIVE).',
      },
      {
        step: 2,
        title: 'Production protection',
        desc: 'Did output, rejects, downtime, and restart performance stay within the approved limits? Directional evaluation (MIN output, MAX scrap/downtime/restart); breach takes precedence over cost drops.',
      },
      {
        step: 3,
        title: 'Attribution integrity',
        desc: 'How much of the observed change can the evidence attribute to the action? Employs REPEATED_STOPPAGES_DEDICATED_METER_V1 with reference baselines and 95% confidence intervals; retrospective/demo claims receive null.',
      },
    ],
    linkText: 'Open Savings Ledger',
    linkRoute: '/investigation-actions?tab=ledger',
  },
];

/**
 * 5 Core Problems Addressed by the Agent
 */
const CORE_PROBLEMS = [
  {
    id: '01',
    code: '01',
    label: 'Rising electricity cost per good unit',
    linkedStageId: 3,
    colorClass: 'problem-rose',
    icon: 'trending-up',
    detail:
      'The agent flags when electricity cost per good unit drifts upward, isolating whether the shift was driven by machine degradation, lower throughput, or unmitigated idle load.',
  },
  {
    id: '02',
    code: '02',
    label: 'Electricity use during zero production',
    linkedStageId: 3,
    colorClass: 'problem-amber',
    icon: 'alert-triangle',
    detail:
      'Standby energy is isolated across line stoppages. The agent applies the REPEATED_STOPPAGES_DEDICATED_METER_V1 model on dedicated process meters to quantify genuine avoidable load.',
  },
  {
    id: '03',
    code: '03',
    label: 'Unusual consumption and low power factor',
    linkedStageId: 3,
    colorClass: 'problem-purple',
    icon: 'zap',
    detail:
      'Multi-detector surveillance catches statistical Z-score excursions, rolling baseline shifts, and power factor deficits below the 0.90 threshold before utility penalty charges apply.',
  },
  {
    id: '04',
    code: '04',
    label: 'Missing or conflicting meter readings',
    linkedStageId: 2,
    colorClass: 'problem-cyan',
    icon: 'database',
    detail:
      'Pre-ingestion guards quarantine corrupt files, detect timestamp gaps or clock regression, and enforce strict monotonic hourly intervals to maintain an unbroken audit trail.',
  },
  {
    id: '05',
    code: '05',
    label: 'Unverified savings after corrective action',
    linkedStageId: 5,
    colorClass: 'problem-red',
    icon: 'shield-alert',
    detail:
      'The platform prevents unearned savings claims. It enforces frozen prospective plans, evaluates 4 production guardrails, and requires an authenticated operational sign-off.',
  },
];

/**
 * Month Formatter (e.g. '2026-08' -> 'Aug 2026')
 */
function formatMonthShort(monthKey) {
  if (!monthKey) return '';
  const [year, month] = monthKey.split('-');
  const date = new Date(parseInt(year, 10), parseInt(month, 10) - 1, 1);
  return date.toLocaleString('en-US', { month: 'short', year: 'numeric' });
}

function formatMonthFull(monthKey) {
  if (!monthKey) return '';
  const [year, month] = monthKey.split('-');
  const date = new Date(parseInt(year, 10), parseInt(month, 10) - 1, 1);
  return date.toLocaleString('en-US', { month: 'long', year: 'numeric' });
}

/**
 * Helper icon renderer
 */
function StageIcon({ name }) {
  switch (name) {
    case 'zap':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      );
    case 'box':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
          <line x1="12" y1="22.08" x2="12" y2="12" />
        </svg>
      );
    case 'sliders':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
          <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
          <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
          <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
        </svg>
      );
    case 'shield-check':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <polyline points="9 12 11 14 15 10" />
        </svg>
      );
    case 'database':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        </svg>
      );
    case 'git-commit':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" /><line x1="1.05" y1="12" x2="7" y2="12" /><line x1="17.01" y1="12" x2="22.96" y2="12" />
        </svg>
      );
    case 'clock':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
        </svg>
      );
    case 'calculator':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="2" width="16" height="20" rx="2" />
          <line x1="8" y1="6" x2="16" y2="6" /><line x1="16" y1="14" x2="16" y2="18" />
          <path d="M16 10h.01" /><path d="M12 10h.01" /><path d="M8 10h.01" />
          <path d="M12 14h.01" /><path d="M8 14h.01" /><path d="M12 18h.01" /><path d="M8 18h.01" />
        </svg>
      );
    case 'activity':
    case 'trending-up':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
      );
    case 'search':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
      );
    case 'user-check':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="8.5" cy="7" r="4" /><polyline points="17 11 19 13 23 9" />
        </svg>
      );
    case 'lock':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      );
    case 'columns':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <line x1="12" y1="3" x2="12" y2="21" />
        </svg>
      );
    case 'check-circle-2':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      );
    case 'award':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="8" r="7" /><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
        </svg>
      );
    case 'alert-triangle':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      );
    case 'shield-alert':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      );
    default:
      return null;
  }
}

/**
 * Recognizable white header pictograms for the infographic pipeline diagram
 */
function StagePictogram({ name }) {
  switch (name) {
    case 'factory':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z" />
          <path d="M17 18h1" />
          <path d="M12 18h1" />
          <path d="M7 18h1" />
        </svg>
      );
    case 'database':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
          <path d="M21 12v7c0 1.66-4 3-9 3s-9-1.34-9-3v-7" />
        </svg>
      );
    case 'chart':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
          <line x1="2" y1="20" x2="22" y2="20" />
        </svg>
      );
    case 'users':
    case 'people':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case 'checklist':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
          <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
          <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
          <path d="m9 14 2 2 4-4" />
        </svg>
      );
    default:
      return null;
  }
}

/**
 * ArchitectureOverview Component
 * 
 * Implements the 4-panel executive operations layout:
 * - TOP-LEFT: System Architecture Pipeline (5 compact horizontal cards)
 * - TOP-RIGHT: Problems the Agent Addresses (5 tinted rows)
 * - BOTTOM-LEFT: Selected Stage Inspector (Closed-loop execution & 3 decisions)
 * - BOTTOM-RIGHT: Plant Energy Intensity Heatmap (₹/good unit by plant & month)
 */
export default function ArchitectureOverview({
  selectedStageId = 5,
  onSelectStageId,
  onOpenDetailedWorkflow,
}) {
  const navigate = useNavigate();

  // Internal stage selection state if not driven externally
  const [activeStageId, setActiveStageId] = useState(selectedStageId || 5);
  const [selectedProblemId, setSelectedProblemId] = useState(null);
  const [selectedItemId, setSelectedItemId] = useState(null);

  // Sync prop changes
  useEffect(() => {
    if (selectedStageId && selectedStageId !== activeStageId) {
      setActiveStageId(selectedStageId);
      setSelectedItemId(null);
    }
  }, [selectedStageId]);

  const handleStageClick = useCallback((id) => {
    setActiveStageId(id);
    setSelectedItemId(null);
    setSelectedProblemId(null);
    if (onSelectStageId) onSelectStageId(id);
  }, [onSelectStageId]);

  const handleItemClick = useCallback((stageId, itemId) => {
    setActiveStageId(stageId);
    setSelectedItemId(itemId);
    setSelectedProblemId(null);
    if (onSelectStageId) onSelectStageId(stageId);
  }, [onSelectStageId]);

  const handleProblemClick = useCallback((prob) => {
    setSelectedProblemId(prob.id);
    setActiveStageId(prob.linkedStageId);
    setSelectedItemId(null);
    if (onSelectStageId) onSelectStageId(prob.linkedStageId);
  }, [onSelectStageId]);

  // Active Stage Object
  const currentStage = useMemo(() => {
    return SYSTEM_STAGES.find((s) => s.id === activeStageId) || SYSTEM_STAGES[4];
  }, [activeStageId]);

  // Active Selected Item
  const selectedItem = useMemo(() => {
    if (!selectedItemId) return null;
    for (const stage of SYSTEM_STAGES) {
      const match = stage.items?.find((it) => it.id === selectedItemId);
      if (match) {
        return {
          ...match,
          stage,
        };
      }
    }
    return null;
  }, [selectedItemId]);

  const activeProblem = useMemo(() => {
    return CORE_PROBLEMS.find((p) => p.id === selectedProblemId);
  }, [selectedProblemId]);

  // Heatmap State
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapLoading, setHeatmapLoading] = useState(true);
  const [heatmapError, setHeatmapError] = useState(null);
  const [selectedCell, setSelectedCell] = useState(null);

  const fetchHeatmapTrends = useCallback(async () => {
    setHeatmapLoading(true);
    setHeatmapError(null);
    try {
      const res = await energyIntensityApi.getTrends({
        grain: 'monthly',
        group_by_plant: true,
      });
      setHeatmapData(res);
      // Default selected cell: latest month for first plant
      if (res && res.buckets && res.buckets.length > 0) {
        const sorted = [...res.buckets].sort((a, b) => b.period_start.localeCompare(a.period_start));
        setSelectedCell(sorted[0]);
      }
    } catch (err) {
      setHeatmapError(err.message || 'Failed to load plant energy intensity heatmap.');
    } finally {
      setHeatmapLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHeatmapTrends();
  }, [fetchHeatmapTrends]);

  // Process Heatmap Grid Matrix
  const { plantList, monthList, cellMatrix, costMin, costMax } = useMemo(() => {
    if (!heatmapData || !heatmapData.buckets || heatmapData.buckets.length === 0) {
      return { plantList: [], monthList: [], cellMatrix: {}, costMin: 0, costMax: 0 };
    }

    const plantsSet = new Set();
    const monthsSet = new Set();
    const matrix = {};
    let minC = Infinity;
    let maxC = -Infinity;

    heatmapData.buckets.forEach((b) => {
      const plant = b.plant_id || 'UNKNOWN';
      const mKey = b.period_start ? b.period_start.slice(0, 7) : 'UNKNOWN';
      plantsSet.add(plant);
      monthsSet.add(mKey);

      const cellKey = `${plant}__${mKey}`;
      matrix[cellKey] = b;

      if (b.cost_intensity_inr_per_good_unit !== null && b.cost_intensity_inr_per_good_unit !== undefined) {
        const costVal = parseFloat(b.cost_intensity_inr_per_good_unit);
        if (!isNaN(costVal)) {
          if (costVal < minC) minC = costVal;
          if (costVal > maxC) maxC = costVal;
        }
      }
    });

    const sortedPlants = Array.from(plantsSet).sort();
    const sortedMonths = Array.from(monthsSet).sort();

    return {
      plantList: sortedPlants,
      monthList: sortedMonths,
      cellMatrix: matrix,
      costMin: minC === Infinity ? 0 : minC,
      costMax: maxC === -Infinity ? 0 : maxC,
    };
  }, [heatmapData]);

  /**
   * Derive cell background color from cost intensity
   */
  const getCellBgStyle = (costVal, isSelected) => {
    if (costVal === null || costVal === undefined || isNaN(costVal)) {
      return {
        background: 'var(--bg-surface-elevated, rgba(148, 163, 184, 0.08))',
        border: isSelected ? '2px solid #6f3dba' : '1px dashed var(--border-color, #cbd5e1)',
        color: 'var(--text-muted, #94a3b8)',
      };
    }

    // Color gradient interpolation:
    // lowest cost -> soft emerald/teal; higher cost -> soft amber/rose
    const range = costMax - costMin;
    const ratio = range > 0 ? Math.min(1, Math.max(0, (costVal - costMin) / range)) : 0.5;

    // Green (16, 185, 129) to Amber (245, 158, 11)
    const r = Math.round(16 + ratio * (245 - 16));
    const g = Math.round(185 - ratio * (185 - 158));
    const b = Math.round(129 - ratio * (129 - 11));
    const alpha = 0.14 + ratio * 0.12;

    return {
      background: `rgba(${r}, ${g}, ${b}, ${alpha})`,
      border: isSelected ? '2px solid #6f3dba' : `1px solid rgba(${r}, ${g}, ${b}, 0.35)`,
      boxShadow: isSelected ? '0 0 0 2px rgba(111, 61, 186, 0.4), 0 2px 8px rgba(0,0,0,0.08)' : 'none',
      color: 'var(--text-primary)',
    };
  };

  return (
    <div className="ps-ref-layout-root home-architecture" role="region" aria-label="Application Architecture & Operations Command">
      {/* 1. COMPACT CONTROL ROW */}
      <div className="ps-ref-control-row">
        <div className="ps-ref-control-buttons">
          <button
            type="button"
            className="ps-ref-btn-active"
            aria-current="page"
            title="Application Architecture & Operations Command (Active Overview)"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="14" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
            </svg>
            <span>Application Architecture &amp; Operations Command</span>
          </button>

          <button
            type="button"
            className="ps-ref-btn-secondary"
            onClick={onOpenDetailedWorkflow}
            title="Open the interactive 9-stage engineering walkthrough"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
            <span>Executive Overview &amp; Analytics</span>
          </button>
        </div>
      </div>

      {/* 2. MAIN ARCHITECTURE COMMAND LAYOUT */}
      <div className="ps-ref-main-grid home-architecture-grid">
        {/* ROW 1: System Architecture Pipeline (Left ~72%) & Problems Solved by the Agent (Right ~28%) */}
        <div className="ps-architecture-top-row">
          {/* ===================================================================
              PANEL 1 (TOP-LEFT): SYSTEM ARCHITECTURE PIPELINE
              =================================================================== */}
          <section className="ps-ref-card ps-panel-pipeline home-pipeline" aria-labelledby="pipeline-heading">
          <div className="ps-ref-card-header">
            <div className="ps-ref-card-header-left">
              <div className="ps-ref-header-icon ps-icon-purple" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
                  <line x1="4" y1="22" x2="4" y2="15" />
                </svg>
              </div>
              <h2 id="pipeline-heading" className="ps-ref-card-title">System Architecture Pipeline</h2>
            </div>
            <span className="ps-ref-card-hint">Select a stage or item to see how it works.</span>
          </div>

          <div className="ps-pipeline-strip-flow" role="region" aria-label="System architecture pipeline stages">
            {SYSTEM_STAGES.map((st, idx) => {
              const isSelected = st.id === activeStageId;
              return (
                <div
                  key={st.id}
                  id={`stage-card-${st.id}`}
                  className={`ps-pipeline-stage-card stage-theme-${st.id} ${isSelected ? 'is-selected' : ''}`}
                  style={{
                    '--stage-color': st.headerColor,
                    '--stage-tint': `${st.headerColor}0a`,
                  }}
                >
                  {/* Full-width colored header band: Button to select stage overview */}
                  <button
                    type="button"
                    className="ps-stage-header-band"
                    style={{ background: st.headerColor }}
                    onClick={() => handleStageClick(st.id)}
                    aria-label={`Select Stage ${st.number}: ${st.headerLabel} overview`}
                    aria-pressed={isSelected && !selectedItemId}
                  >
                    <div className="ps-stage-header-inner">
                      <div className="ps-stage-header-icon-box" aria-hidden="true">
                        <StagePictogram name={st.pictogram} />
                      </div>
                      <div className="ps-stage-header-title-box">
                        <span className="ps-stage-header-title-text">{st.number}. {st.headerLabel}</span>
                        {st.headerSub && <span className="ps-stage-header-sub-text">{st.headerSub}</span>}
                      </div>
                    </div>
                  </button>

                  {/* Body: Two distinct layouts */}
                  <div
                    className="ps-stage-card-body"
                    onClick={() => {
                      if (selectedItemId) handleStageClick(st.id);
                    }}
                  >
                    {st.layoutType === 'rows' ? (
                      <div className="ps-stage-rows-body">
                        {st.items.map((item) => {
                          const isItemActive = isSelected && selectedItemId === item.id;
                          return (
                            <button
                              type="button"
                              key={item.id}
                              className={`ps-stage-tint-row ${item.tint} ${isItemActive ? 'is-item-selected' : ''}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleItemClick(st.id, item.id);
                              }}
                              aria-label={`Inspect ${item.text}`}
                              aria-pressed={isItemActive}
                            >
                              <div className="ps-stage-row-img-box">
                                <img
                                  src={item.iconImg || item.fallbackImg}
                                  alt=""
                                  className="ps-stage-row-img"
                                  loading="eager"
                                />
                              </div>
                              <div className="ps-stage-row-text-content">
                                <span className="ps-stage-row-text">{item.text}</span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="ps-stage-illust-body">
                        <div
                          className="ps-stage-center-illust-box"
                          role="button"
                          tabIndex={0}
                          onClick={() => handleStageClick(st.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              handleStageClick(st.id);
                            }
                          }}
                          aria-label={`Stage ${st.number} illustration, click for stage overview`}
                        >
                          <img
                            src={st.image || st.fallbackImage}
                            alt=""
                            className="ps-stage-center-illust"
                            loading="eager"
                          />
                        </div>
                        <div className="ps-stage-sublabels-box">
                          {st.items.map((sub) => {
                            const isSubActive = isSelected && selectedItemId === sub.id;
                            return (
                              <button
                                type="button"
                                key={sub.id}
                                className={`ps-stage-sublabel-row ${isSubActive ? 'is-item-selected' : ''}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleItemClick(st.id, sub.id);
                                }}
                                aria-label={`Inspect ${sub.text}`}
                                aria-pressed={isSubActive}
                              >
                                <span className="ps-stage-sublabel-text">{sub.text}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Connecting arrow in gap between cards */}
                  {idx < SYSTEM_STAGES.length - 1 && (
                    <div className="ps-stage-connector-arrow" aria-hidden="true">
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <line x1="4" y1="12" x2="20" y2="12" />
                        <polyline points="14 6 20 12 14 18" />
                      </svg>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* ===================================================================
            PANEL 2 (TOP-RIGHT): PROBLEMS THE AGENT ADDRESSES
            =================================================================== */}
        <section className="ps-ref-card ps-panel-problems home-problems" aria-labelledby="problems-heading">
          <div className="ps-ref-card-header">
            <div className="ps-ref-card-header-left">
              <div className="ps-ref-header-icon ps-icon-rose" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <h2 id="problems-heading" className="ps-ref-card-title">Problems Solved by the Agent</h2>
            </div>
            <span className="ps-badge-counter">{CORE_PROBLEMS.length}</span>
          </div>

          <ol className="ps-problems-list-container">
            {CORE_PROBLEMS.map((prob) => {
              const isSelected = prob.id === selectedProblemId;
              return (
                <li
                  key={prob.id}
                  className={`ps-problem-row ${prob.colorClass} ${isSelected ? 'is-problem-active' : ''}`}
                  onClick={() => handleProblemClick(prob)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleProblemClick(prob);
                    }
                  }}
                  title={`Inspect how the agent addresses problem ${prob.code}`}
                >
                  <span className="ps-problem-num">{prob.code}</span>
                  <span className="ps-problem-label">{prob.label}</span>
                  <span className="ps-problem-icon-wrap" aria-hidden="true">
                    <StageIcon name={prob.icon} />
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      </div>

      {/* ROW 2: Selected Stage Inspector (Left) & Plant Energy Intensity Heatmap (Right) */}
      <div className="ps-architecture-bottom-row">
        {/* ===================================================================
            PANEL 3 (BOTTOM-LEFT): SELECTED STAGE INSPECTOR
            =================================================================== */}
        <section
          id="stage-inspector-panel"
          className="ps-ref-card ps-panel-inspector home-inspector"
          role="region"
          aria-labelledby="inspector-heading"
        >
          {selectedItem ? (
            <>
              {/* Header with Parent Stage Label, Item Title & Stage Tag */}
              <div className="ps-ref-card-header ps-inspector-header">
                <div className="ps-inspector-header-left">
                  <span className="ps-stage-num-badge" style={{ background: currentStage.headerColor }}>
                    {currentStage.number}
                  </span>
                  <div className="ps-inspector-title-group">
                    <span className="ps-inspector-parent-label">
                      {currentStage.headerLabel} › {selectedItem.text}
                    </span>
                    <h3 id="inspector-heading" className="ps-inspector-card-title">
                      {selectedItem.text}
                    </h3>
                  </div>
                </div>
                <button
                  type="button"
                  className="ps-badge-stage-tag ps-inspector-stage-restore-btn"
                  style={{ color: currentStage.headerColor, borderColor: `${currentStage.headerColor}40` }}
                  onClick={() => setSelectedItemId(null)}
                  title={`Clear item selection and view full Stage ${currentStage.number} overview`}
                >
                  STAGE {currentStage.id} OF {SYSTEM_STAGES.length}
                </button>
              </div>

              {/* Item explanation bullets */}
              <div className="ps-item-detail-content">
                <ul className="ps-item-bullets-list" aria-label={`Explanations for ${selectedItem.text}`}>
                  {selectedItem.explanation.map((bullet, idx) => (
                    <li key={idx} className="ps-item-bullet-row">
                      <span className="ps-item-bullet-marker" aria-hidden="true">•</span>
                      <p className="ps-item-bullet-text">{bullet}</p>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Destination Link Button */}
              <div className="ps-inspector-footer">
                <button
                  type="button"
                  className="ps-inspector-action-btn"
                  onClick={() => navigate(currentStage.linkRoute)}
                  title={`Navigate to ${currentStage.linkText}`}
                >
                  <span>{currentStage.linkText}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                </button>
              </div>
            </>
          ) : (
            <>
              {/* Header with Stage Title & Badge */}
              <div className="ps-ref-card-header ps-inspector-header">
                <div className="ps-inspector-header-left">
                  <span className="ps-stage-num-badge" style={{ background: currentStage.headerColor }}>
                    {currentStage.number}
                  </span>
                  <h3 id="inspector-heading" className="ps-inspector-card-title">
                    {currentStage.number}. {currentStage.title.replace(/^\d+\.\s*/, '')}
                  </h3>
                </div>
                <span className="ps-badge-stage-tag" style={{ color: currentStage.headerColor, borderColor: `${currentStage.headerColor}40` }}>
                  STAGE {currentStage.id} OF {SYSTEM_STAGES.length}
                </span>
              </div>

              {/* Detailed bullet points from selected stage */}
              <div className="ps-inspector-items-strip" aria-label="Stage core deliverables">
                {currentStage.items.map((it, itemIdx) => (
                  <button
                    type="button"
                    key={it.id || itemIdx}
                    className={`ps-inspector-item-badge ${it.tint || ''}`}
                    title={it.hint || `Inspect ${it.text}`}
                    onClick={() => handleItemClick(currentStage.id, it.id)}
                  >
                    <span className="ps-inspector-item-icon" aria-hidden="true">
                      <StageIcon name={it.icon} />
                    </span>
                    <div className="ps-inspector-item-info">
                      <strong className="ps-inspector-item-name">{it.text}</strong>
                      {it.hint && <span className="ps-inspector-item-hint">{it.hint}</span>}
                    </div>
                  </button>
                ))}
              </div>

              {/* Active Problem Callout (when triggered from Top-Right list) */}
              {activeProblem && (
                <div className={`ps-inspector-problem-banner ${activeProblem.colorClass}`}>
                  <div className="ps-prob-banner-top">
                    <span className="ps-prob-banner-tag">Addressing Problem {activeProblem.code}</span>
                    <button
                      type="button"
                      className="ps-prob-banner-dismiss"
                      onClick={() => setSelectedProblemId(null)}
                      title="Dismiss problem highlight"
                    >
                      ✕
                    </button>
                  </div>
                  <p className="ps-prob-banner-detail">{activeProblem.detail}</p>
                </div>
              )}

              {/* Plain-English Explanation */}
              <p className="ps-inspector-explanation">
                {currentStage.explanation}
              </p>

              {/* Technical Details Strip in Expandable Section */}
              <details className="ps-tech-details-accordion">
                <summary className="ps-tech-accordion-summary">
                  <span>Technical details &amp; schema</span>
                  <svg className="ps-accordion-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </summary>
                <div className="ps-tech-details-strip">
                  <div className="ps-tech-strip-item">
                    <span className="ps-tech-label">PROTOCOLS &amp; WORKSPACE:</span>
                    <span className="ps-tech-value">{currentStage.technicalDetails.protocols}</span>
                  </div>
                  <div className="ps-tech-strip-item ps-tech-tables-row">
                    <span className="ps-tech-label">DATABASE TABLES:</span>
                    <div className="ps-tech-tables-list">
                      {currentStage.technicalDetails.tables.map((tName) => (
                        <code key={tName} className="ps-table-code-pill">{tName}</code>
                      ))}
                    </div>
                  </div>
                </div>
              </details>

              {/* Workflow & Operational Flow */}
              <div className="ps-inspector-workflow-block">
                <h4 className="ps-workflow-heading">{currentStage.flowHeading}</h4>
                <div className="ps-workflow-steps-list">
                  {currentStage.workflow.map((wf) => (
                    <div key={wf.step} className="ps-workflow-step-row">
                      <span className="ps-step-num-circle">{wf.step}</span>
                      <div className="ps-step-text-content">
                        <strong className="ps-step-title">{wf.title}:</strong>
                        <span className="ps-step-desc"> {wf.desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Destination Link Button */}
              <div className="ps-inspector-footer">
                <button
                  type="button"
                  className="ps-inspector-action-btn"
                  onClick={() => navigate(currentStage.linkRoute)}
                  title={`Navigate to ${currentStage.linkText}`}
                >
                  <span>{currentStage.linkText}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                </button>
              </div>
            </>
          )}
        </section>

        {/* ===================================================================
            PANEL 4 (BOTTOM-RIGHT): PLANT ENERGY INTENSITY HEATMAP
            =================================================================== */}
        <section className="ps-ref-card ps-panel-heatmap home-heatmap" aria-labelledby="heatmap-heading">
          <div className="ps-ref-card-header">
            <div className="ps-ref-card-header-left">
              <div className="ps-ref-header-icon ps-icon-emerald" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <line x1="3" y1="9" x2="21" y2="9" />
                  <line x1="3" y1="15" x2="21" y2="15" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                  <line x1="15" y1="3" x2="15" y2="21" />
                </svg>
              </div>
              <h2 id="heatmap-heading" className="ps-ref-card-title">Plant Energy Intensity Heatmap</h2>
            </div>
            <span className="ps-heatmap-unit-badge">₹ per good finished unit</span>
          </div>

          {/* Heatmap Grid Content */}
          {heatmapLoading ? (
            <div className="ps-heatmap-loading-state">
              <div className="ps-pulse-spinner" />
              <span>Loading plant energy intensity trends from database…</span>
            </div>
          ) : heatmapError ? (
            <div className="ps-heatmap-error-state">
              <span className="err-msg">{heatmapError}</span>
              <button type="button" className="btn-retry" onClick={fetchHeatmapTrends}>
                Retry
              </button>
            </div>
          ) : plantList.length === 0 || monthList.length === 0 ? (
            <div className="ps-heatmap-empty-state">
              <span>No monthly plant energy intensity records available.</span>
            </div>
          ) : (
            <>
              {/* Heatmap Table Matrix */}
              <div className="ps-heatmap-table-container">
                <table className="ps-heatmap-table" role="grid" aria-label="Plant electricity cost per good unit by month">
                  <thead>
                    <tr>
                      <th scope="col" className="ps-th-plant">PLANT</th>
                      {monthList.map((mKey) => (
                        <th key={mKey} scope="col" className="ps-th-month">
                          {formatMonthShort(mKey)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {plantList.map((pId) => (
                      <tr key={pId}>
                        <th scope="row" className="ps-td-plant-name">
                          <span className="ps-plant-dot" />
                          <span>{pId}</span>
                        </th>
                        {monthList.map((mKey) => {
                          const cellKey = `${pId}__${mKey}`;
                          const bucket = cellMatrix[cellKey];
                          const hasData = bucket && bucket.cost_intensity_inr_per_good_unit !== null && bucket.cost_intensity_inr_per_good_unit !== undefined;
                          const costVal = hasData ? parseFloat(bucket.cost_intensity_inr_per_good_unit) : null;
                          const isSelected = selectedCell && selectedCell.plant_id === pId && selectedCell.period_start?.startsWith(mKey);

                          return (
                            <td key={mKey} className="ps-td-heatmap-cell">
                              <button
                                type="button"
                                className={`ps-heatmap-cell-btn ${isSelected ? 'is-selected' : ''}`}
                                style={getCellBgStyle(costVal, isSelected)}
                                onClick={() => setSelectedCell(bucket || { plant_id: pId, period_start: `${mKey}-01`, noData: true })}
                                title={`${pId} (${formatMonthFull(mKey)}): ${hasData ? `₹${costVal.toFixed(2)}/unit, ${bucket.coverage?.coverage_percentage}% coverage` : 'No data'}`}
                              >
                                {hasData ? (
                                  <>
                                    <span className="ps-cell-cost-val">₹{costVal.toFixed(2)}</span>
                                    <span className={`ps-cell-cov-sub ${(bucket.coverage?.coverage_percentage || 0) >= 99 ? 'is-full-cov' : 'is-partial-cov'}`}>
                                      {parseFloat(bucket.coverage?.coverage_percentage || 0).toFixed(0)}% cov
                                    </span>
                                  </>
                                ) : (
                                  <>
                                    <span className="ps-cell-cost-val">—</span>
                                    <span className="ps-cell-cov-sub is-nodata">No data</span>
                                  </>
                                )}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Heatmap Legend Bar */}
              <div className="ps-heatmap-legend-row">
                <div className="ps-legend-bar-wrap">
                  <span className="ps-legend-label">Cost intensity:</span>
                  <span className="ps-legend-scale-num">₹{costMin.toFixed(2)}</span>
                  <div className="ps-legend-gradient-track" />
                  <span className="ps-legend-scale-num">₹{costMax.toFixed(2)}</span>
                </div>
                <div className="ps-legend-pills-group">
                  <span className="ps-legend-cov-pill is-full" title="100% of expected plant hours have complete telemetry & production">
                    <span className="dot-cov dot-full" /> 100% Full cov
                  </span>
                  <span className="ps-legend-cov-pill is-partial" title="Less than 100% coverage recorded in dataset">
                    <span className="dot-cov dot-partial" /> &lt;100% Partial
                  </span>
                  <span className="ps-legend-cov-pill is-nodata" title="No complete telemetry recorded for this plant & month">
                    <span className="dot-cov dot-nodata" /> No data
                  </span>
                </div>
              </div>

              {/* Selected Cell Detail Breakdown in Expandable Section */}
              {selectedCell && (
                <details className="ps-cell-detail-accordion" open>
                  <summary className="ps-cell-accordion-summary">
                    <div className="ps-cell-summary-left">
                      <span className="ps-detail-plant-badge">{selectedCell.plant_id}</span>
                      <span className="ps-detail-month-label">{formatMonthFull(selectedCell.period_start?.slice(0, 7))}</span>
                      {selectedCell.coverage?.coverage_status && (
                        <span className={`ps-detail-cov-pill ${selectedCell.coverage.coverage_percentage < 50 ? 'is-low' : 'is-full'}`}>
                          {selectedCell.coverage.coverage_percentage}% Coverage
                        </span>
                      )}
                    </div>
                    <svg className="ps-accordion-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </summary>
                  <div className="ps-cell-detail-inspector">
                    {selectedCell.noData ? (
                      <p className="ps-detail-nodata-msg">
                        No complete matched hourly telemetry or production records were recorded for {selectedCell.plant_id} during this month.
                      </p>
                    ) : (
                      <div className="ps-detail-metrics-grid">
                        <div className="ps-detail-metric-card">
                          <span className="ps-metric-label">Estimated electricity cost per good unit</span>
                          <div className="ps-metric-value-highlight">
                            {selectedCell.cost_intensity_inr_per_good_unit !== null && selectedCell.cost_intensity_inr_per_good_unit !== undefined
                              ? `₹${parseFloat(selectedCell.cost_intensity_inr_per_good_unit).toFixed(2)} / unit`
                              : 'Undefined (Zero output)'}
                          </div>
                          <span className="ps-metric-sub">Ratio of sums: Cost ÷ Good units</span>
                        </div>

                        <div className="ps-detail-metric-card">
                          <span className="ps-metric-label">Eligible electricity &amp; cost</span>
                          <div className="ps-metric-value-plain">
                            {formatNumber(selectedCell.eligible_energy_kwh)} kWh
                          </div>
                          <span className="ps-metric-sub">{formatCurrency(selectedCell.eligible_cost_inr)} (Dataset-derived)</span>
                        </div>

                        <div className="ps-detail-metric-card">
                          <span className="ps-metric-label">FAL finished good output</span>
                          <div className="ps-metric-value-plain">
                            {formatNumber(selectedCell.matched_good_qty)} units
                          </div>
                          <span className="ps-metric-sub">
                            Yield: {selectedCell.production_context?.fal_yield_pct ? `${selectedCell.production_context.fal_yield_pct}%` : '100%'}
                          </span>
                        </div>

                        <div className="ps-detail-metric-card">
                          <span className="ps-metric-label">Matched plant coverage</span>
                          <div className="ps-metric-value-plain">
                            {selectedCell.coverage?.complete_matched_hours || 0} / {selectedCell.coverage?.expected_plant_hours || 0} hrs
                          </div>
                          <span className="ps-metric-sub">
                            {selectedCell.coverage?.incomplete_hours || 0} incomplete hrs
                          </span>
                        </div>
                      </div>
                    )}

                    <p className="ps-detail-disclaimer">
                      <strong>Operational Rule:</strong> Estimated electricity cost per good unit. A lower cell value alone cannot establish intervention savings without an approved M&amp;V plan and counterfactual attribution.
                    </p>
                  </div>
                </details>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  </div>
);
}
