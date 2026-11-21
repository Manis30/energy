import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ArchitectureOverview from './platform-story/ArchitectureOverview';
import './platform-story/platform-story.css';

/**
 * 9 Sequential Operational Workflow Stages of Energy Intel.
 * Strictly reflects actual application capabilities.
 */
const WORKFLOW_STAGES = [
  {
    id: 1,
    step: '01',
    title: 'Data Sources',
    shortName: 'Sources',
    badge: 'Stage 1 · Input Feeds',
    purpose: 'Aggregate raw electrical telemetry, line output records, and plant master data across approved channels.',
    scope: 'Daily energy reports, daily production reports, plant submeter hierarchy, and approved external connectors.',
    tech: 'CSV/XLSX Files (Operational Intake) · PostgreSQL Primary Storage · SharePoint & MongoDB Sandboxes',
    boundary: 'Telemetry is sourced from recorded plant files and staging databases; no synthetic generation.',
    simulatedData: {
      feeds: [
        { name: 'Daily Energy Report', format: 'CSV / XLSX', source: 'Plant Electrical Substations (IN-TN-01, IN-KA-01)', status: 'Active' },
        { name: 'Daily Production Report', format: 'XLSX / XLS', source: 'Line Production Stations (SMT-1, SMT-2, FAL-1)', status: 'Active' },
        { name: 'Submeter Master Hierarchy', format: 'PostgreSQL Dimension', source: 'Main Incomer, SMT, FAL, Utilities, HVAC', status: 'Verified' },
        { name: 'Approved Connectors', format: 'PostgreSQL, File Intake, Mongo/SharePoint Sims', source: 'PostgreSQL Primary & Manual File Intake Path', status: 'Operational Intake Active' },
      ],
      activeSample: 'IN-TN-01_2026-10-14_Energy_Telemetry.xlsx (24 hourly intervals, 6 meters)',
    },
  },
  {
    id: 2,
    step: '02',
    title: 'Upload & Validation',
    shortName: 'Validation',
    badge: 'Stage 2 · Pre-Ingestion Guard',
    purpose: 'Execute two-stage pre-ingestion validation to verify headers, data bounds, units, and timestamps.',
    scope: 'Enforce required columns, physical voltage/current/hourly kWh thresholds, strictly monotonic time, and foreign key references.',
    tech: 'Two-Stage Validator · Pandas / OpenPyXL · Ingestion Error Remediation · FastAPI Upload',
    boundary: 'Invalid rows or corrupted schema columns are rejected before commit; never silently coerced.',
    simulatedData: {
      checks: [
        { name: 'Header Schema & Column Types', result: 'PASS', detail: 'All 14 mandatory meter columns present and typed' },
        { name: 'Electrical Range & Value Bounds', result: 'PASS', detail: 'Voltage: 415±10% V, PF: 0.00–1.00, Hourly Energy > 0' },
        { name: 'Timestamp Monotonicity & Interval', result: 'PASS', detail: 'Strict 1-hour interval spacing, zero clock regression' },
        { name: 'Foreign Key & Master Plant Validation', result: 'PASS', detail: 'Plant IN-TN-01 and meter IDs match dimension tables' },
      ],
      quarantineCount: '0 errors quarantined (Clean batch)',
    },
  },
  {
    id: 3,
    step: '03',
    title: 'Database Ingestion',
    shortName: 'Ingestion',
    badge: 'Stage 3 · Immutable Storage',
    purpose: 'Commit valid telemetry and production records into authoritative PostgreSQL fact tables with batch lineage.',
    scope: 'Store valid records in Neon PostgreSQL, log upload history, and stamp row-level upload provenance.',
    tech: 'PostgreSQL 16 · SQLAlchemy ORM · upload_history Provenance Engine · Star Schema',
    boundary: 'All committed rows carry immutable upload_id for 100% forensic auditability back to the source file.',
    simulatedData: {
      commitBatch: {
        uploadId: 'upl-20261014-tn01-0941',
        targetTable: 'fact_energy_meter_hourly',
        rowsInserted: 144,
        provenanceHash: 'sha256:4a8b9e12...7f3c',
        commitState: 'ATOMIC COMMIT SUCCESSFUL',
      },
      auditEntry: 'Recorded in upload_history with operator ID, file hash, row counts, and timestamp.',
    },
  },
  {
    id: 4,
    step: '04',
    title: 'Data Reconciliation',
    shortName: 'Reconciliation',
    badge: 'Stage 4 · Integrity Audit',
    purpose: 'Execute cross-source reconciliation to audit coverage, temporal alignment, and duplicate records.',
    scope: 'Check energy vs production temporal coverage, detect duplicates, and score cross-source integrity.',
    tech: 'Reconciliation Engine · 12 Deterministic Cross-Checks · Shift Boundary Aligner',
    boundary: 'Mismatched timestamps or incomplete hours are flagged with transparent integrity warnings.',
    simulatedData: {
      reconciliationMetrics: [
        { check: 'Temporal Coverage Alignment', status: '100% Complete', score: '24 / 24 Hours Covered' },
        { check: 'Shift Boundary Synchronisation', status: 'Verified', score: 'Shift A, B, C Aligned' },
        { check: 'Duplicate Record Audit', status: 'Zero Duplicates', score: '0 Conflicting Intervals' },
        { check: 'Overall Data Quality Score', status: 'High Confidence', score: '99.4% Integrity Index' },
      ],
      notice: 'Coverage verified: 24 active hours across SMT & FAL production lines.',
    },
  },
  {
    id: 5,
    step: '05',
    title: 'Deterministic Analytics',
    shortName: 'Analytics',
    badge: 'Stage 5 · Metric Calculations',
    purpose: 'Calculate energy, cost, emissions, and Specific Energy Consumption (SEC) with configured dataset rules.',
    scope: 'Formulate active kWh, tariff costs, carbon emissions, and process SEC (SMT kWh/board vs FAL kWh/assembly unit).',
    tech: 'Deterministic Formulations · Tariff Matrix Engine · SMT/FAL SEC Separator · NumPy',
    boundary: 'All numbers are computed by backend Python functions; no generative estimation or floating assumptions.',
    simulatedData: {
      kpiCalculations: [
        { metric: 'Active Energy Consumed', value: '21,283.6 kWh', formula: 'SUM(hourly active kWh per meter)' },
        { metric: 'Electricity Tariff Cost', value: '₹1,75,589.70', formula: 'Time-of-Day (ToD) tariff tier multiplier' },
        { metric: 'Grid Carbon Emissions', value: '15,324.2 kg CO₂', formula: '0.72 kg CO₂/kWh grid emission factor' },
        { metric: 'SMT Specific Energy (SEC)', value: '0.412 kWh/board', formula: 'SMT submeter kWh / Good SMT boards' },
        { metric: 'FAL Specific Energy (SEC)', value: '1.845 kWh/unit', formula: 'FAL assembly kWh / FAL assembly units' },
      ],
      baselineStatus: 'Qualified (21-day rolling historical baseline satisfied)',
    },
  },
  {
    id: 6,
    step: '06',
    title: 'Anomaly Detection',
    shortName: 'Anomalies',
    badge: 'Stage 6 · Mathematical Surveillance',
    purpose: 'Run four mathematical surveillance detectors to identify statistical spikes, drift, and unneeded power draw.',
    scope: 'Z-Score 3σ spike detector, 24h rolling baseline comparator, power factor < 0.90 monitor, and standby waste detector.',
    tech: 'Statistical Z-Score · Rolling Baseline · Power Factor Compliance Engine · Standby Correlator',
    boundary: 'Distinguishes trusted from tentative signals; rule thresholds are explicit and deterministic.',
    simulatedData: {
      detectors: [
        { name: 'Statistical Z-Score (3.0σ)', status: 'TRIGGERED', detail: 'MTR-SMT peak hourly consumption (kWh) at 14:00 (Z = +3.42σ)', confidence: 'HIGH' },
        { name: '24h Rolling Baseline Drift', status: 'NORMAL', detail: 'SMT Line 2 within ±1.5σ baseline envelope', confidence: 'TRUSTED' },
        { name: 'Power Factor Compliance (<0.90)', status: 'TRIGGERED', detail: 'MTR-FAL dropped to 0.884 at 16:00 (Grid penalty)', confidence: 'HIGH' },
        { name: 'Zero-Output Electricity Observation', status: 'TRIGGERED', detail: 'Line 1 drew electricity during 45 min scheduled stoppage (flagged for investigation)', confidence: 'HIGH' },
      ],
      activeSignal: 'FND-TN01-20261014-001 (Zero-Output Electricity Observation on SMT-1)',
    },
  },
  {
    id: 7,
    step: '07',
    title: 'AI Investigation',
    shortName: 'AI Agent',
    badge: 'Stage 7 · Evidence-Grounded Reasoning',
    purpose: 'Investigate operational findings using deterministic domain tools, auditing numeric claims against raw data.',
    scope: 'Explain analytical evidence, query 21 backend tools, verify numbers against payloads, and prevent hallucinations.',
    tech: 'ReAct Agent · 21 Deterministic Tools · EvidenceVerifier Sub-Agent · Scope Context Injector',
    boundary: 'The AI interprets validated backend data; it never invents measurements or calculates metrics directly.',
    simulatedData: {
      investigationTrace: [
        { step: '1. User / Finding Trigger', text: 'Analyze 18.4 kW standby draw on SMT-1 during shift B downtime' },
        { step: '2. Tool Execution', text: 'get_energy_standby_breakdown(plant="IN-TN-01", line="SMT-1", date="2026-10-14")' },
        { step: '3. Backend Evidence', text: 'Payload: { idle_kw: 18.4, duration_min: 45, wasted_kwh: 13.8, cost_inr: 113.85 }' },
        { step: '4. Evidence Verification', text: 'EvidenceVerifier: 4/4 numeric claims verified against tool response (Green Check)' },
        { step: '5. Grounded Explanation', text: 'Reflow oven heaters maintained at full temperature during feeder changeover.' },
      ],
      guarantee: 'Zero Numeric Hallucination: 100% of figures verified against backend responses.',
    },
  },
  {
    id: 8,
    step: '08',
    title: 'Findings & Recommendations',
    shortName: 'Findings',
    badge: 'Stage 8 · Operational Synthesis',
    purpose: 'Synthesize persistent operational findings and evidence-linked energy conservation recommendations.',
    scope: 'Track finding state, evaluate priority, calculate ROI/payback, and link energy conservation measures.',
    tech: 'Finding Lifecycle Service · Recommendation Synthesizer · Tariff ROI Calculator · PostgreSQL',
    boundary: 'Recommendations are derived from verified engineering catalogs and exact tariff rate matrices.',
    simulatedData: {
      recommendation: {
        recId: 'REC-IN-TN-01-BD2F76E972',
        title: 'Configure Auto-Sleep Thermostat on SMT-1 Reflow Oven',
        priority: 'HIGH',
        category: 'Standby Power Reduction',
        annualSavings: '₹1,42,800 / year (17,300 kWh saved)',
        implementationEffort: 'Low (PLC parameter update)',
        paybackPeriod: 'Immediate (< 1 month)',
        linkedFinding: 'FND-TN01-20261014-001',
      },
      status: 'OPEN · Ready for Maintenance Assignment',
    },
  },
  {
    id: 9,
    step: '09',
    title: 'Operational Follow-through',
    shortName: 'Follow-through',
    badge: 'Stage 9 · Closed-Loop Resolution',
    purpose: 'Assign discrete corrective tasks to technicians, monitor progress, and verify resolution independently.',
    scope: 'Assign owners with mandatory due dates, track overdue actions, and record append-only audit trail.',
    tech: 'Action Management Engine · Independent Verification Gate · Append-Only Audit Logging',
    boundary: 'Findings require telemetry re-validation before closure; action completion alone does not auto-resolve.',
    simulatedData: {
      correctiveAction: {
        actionId: 'ACT-20261014-081',
        task: 'Reprogram PLC sleep mode timeout from 60 min to 10 min',
        assignee: 'K. Raman (Senior Automation Engineer)',
        dueDate: '2026-10-18 (Mandatory)',
        status: 'IN_PROGRESS',
        verificationGate: 'Eligible M&V assessment required: output guardrails protected before savings verification',
      },
      auditTrail: 'Logged: CREATED -> ASSIGNED -> IN_PROGRESS with timestamp and attribution.',
    },
  },
];

export default function PlatformStory() {
  const [viewMode, setViewMode] = useState('overview');
  const [selectedArchStageId, setSelectedArchStageId] = useState(5);
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const timerRef = useRef(null);
  const simulatorRef = useRef(null);

  const handleSwitchToOverview = () => {
    setIsPlaying(false);
    setProgress(0);
    setViewMode('overview');
  };

  const handleSwitchToWalkthrough = () => {
    setViewMode('walkthrough');
  };

  const activeStage = WORKFLOW_STAGES[activeStageIndex];
  const STAGE_DURATION_MS = 4000;
  const TICK_INTERVAL_MS = 50;

  // Auto-play simulation timer with smooth progress bar
  useEffect(() => {
    if (!isPlaying) {
      if (timerRef.current) clearInterval(timerRef.current);
      setProgress(0);
      return;
    }

    const startTime = Date.now();
    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(100, (elapsed / STAGE_DURATION_MS) * 100);
      setProgress(pct);

      if (elapsed >= STAGE_DURATION_MS) {
        clearInterval(timerRef.current);
        setProgress(0);
        setActiveStageIndex((prev) => {
          if (prev < WORKFLOW_STAGES.length - 1) {
            return prev + 1;
          } else {
            setIsPlaying(false);
            return prev;
          }
        });
      }
    }, TICK_INTERVAL_MS);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, activeStageIndex]);

  const handlePlayToggle = () => {
    if (!isPlaying && activeStageIndex === WORKFLOW_STAGES.length - 1) {
      setActiveStageIndex(0);
    }
    setIsPlaying((prev) => !prev);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setProgress(0);
    setActiveStageIndex(0);
  };

  const handleNext = () => {
    setIsPlaying(false);
    setProgress(0);
    if (activeStageIndex < WORKFLOW_STAGES.length - 1) {
      setActiveStageIndex((prev) => prev + 1);
    }
  };

  const handlePrev = () => {
    setIsPlaying(false);
    setProgress(0);
    if (activeStageIndex > 0) {
      setActiveStageIndex((prev) => prev - 1);
    }
  };

  const handleSelectStage = (index) => {
    setIsPlaying(false);
    setProgress(0);
    setActiveStageIndex(index);
    if (simulatorRef.current) {
      simulatorRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  if (viewMode === 'overview') {
    return (
      <div className="platform-story-page">
        <ArchitectureOverview
          selectedStageId={selectedArchStageId}
          onSelectStageId={setSelectedArchStageId}
          onOpenDetailedWorkflow={handleSwitchToWalkthrough}
        />
      </div>
    );
  }

  return (
    <div className="platform-story-page">
      {/* 1. Header & Live Simulation Controls Toolbar */}
      <section ref={simulatorRef} className="ps-toolbar" role="region" aria-label="Interactive Simulation Controls">
        <div className="ps-toolbar-left">
          <div className="ps-toolbar-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>
          <div className="ps-toolbar-text">
            <h1 className="ps-toolbar-title">Operational Pipeline Walkthrough</h1>
            <p className="ps-toolbar-subtitle">
              Interactive 9-stage operational sequence from plant telemetry to physical verification gate.
            </p>
          </div>
        </div>

        <div className="ps-toolbar-controls">
          <button
            type="button"
            className="ps-mode-toggle-btn secondary"
            onClick={handleSwitchToOverview}
            title="Return to the architecture overview diagram"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            <span>Back to architecture overview</span>
          </button>

          <div className="ps-stage-counter-pill">
            <span className="ps-pulse-indicator" aria-hidden="true" />
            <span>
              Stage {activeStage.id} of {WORKFLOW_STAGES.length}
            </span>
          </div>

          <div className="ps-btn-group">
            <button
              type="button"
              className="ps-control-btn"
              onClick={handlePrev}
              disabled={activeStageIndex === 0}
              title="Previous Stage"
              aria-label="Previous Stage"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>

            <button
              type="button"
              className={`ps-control-btn play-btn ${isPlaying ? 'is-playing' : ''}`}
              onClick={handlePlayToggle}
              title={isPlaying ? 'Pause Walkthrough' : 'Play Interactive Walkthrough'}
              aria-label={isPlaying ? 'Pause Walkthrough' : 'Play Interactive Walkthrough'}
            >
              {isPlaying ? (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="4" width="4" height="16" />
                    <rect x="14" y="4" width="4" height="16" />
                  </svg>
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span>{activeStageIndex === WORKFLOW_STAGES.length - 1 ? 'Replay' : 'Play'}</span>
                </>
              )}
            </button>

            <button
              type="button"
              className="ps-control-btn"
              onClick={handleNext}
              disabled={activeStageIndex === WORKFLOW_STAGES.length - 1}
              title="Next Stage"
              aria-label="Next Stage"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>

            <button
              type="button"
              className="ps-control-btn reset-btn"
              onClick={handleReset}
              title="Reset to Stage 1"
              aria-label="Reset to Stage 1"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
              </svg>
              <span>Reset</span>
            </button>
          </div>
        </div>

        {/* Dynamic Progress Line */}
        {isPlaying && (
          <div className="ps-toolbar-progress-track" aria-hidden="true">
            <div className="ps-toolbar-progress-bar" style={{ width: `${progress}%` }} />
          </div>
        )}
      </section>

      {/* 2. Horizontal Process Stepper Bar (9 Numbered Stages) */}
      <section className="ps-stepper-section" aria-label="Horizontal Pipeline Process Overview">
        <div className="ps-stepper-scrollable">
          <div className="ps-stepper-track">
            {WORKFLOW_STAGES.map((stage, idx) => {
              const isActive = idx === activeStageIndex;
              const isPast = idx < activeStageIndex;
              return (
                <div key={stage.id} className="ps-stepper-node-wrapper">
                  <button
                    type="button"
                    className={`ps-stepper-node ${isActive ? 'is-active' : ''} ${isPast ? 'is-past' : ''}`}
                    onClick={() => handleSelectStage(idx)}
                    aria-label={`Select Stage ${stage.step}: ${stage.title}`}
                    aria-current={isActive ? 'step' : undefined}
                  >
                    <div className="ps-node-header">
                      <span className="ps-node-number">{stage.step}</span>
                      <span className="ps-node-dot" />
                    </div>
                    <span className="ps-node-title">{stage.shortName}</span>
                  </button>

                  {idx < WORKFLOW_STAGES.length - 1 && (
                    <div
                      className={`ps-stepper-connector ${idx < activeStageIndex ? 'is-completed' : ''}`}
                      aria-hidden="true"
                    >
                      <div className="ps-connector-line" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* 3. Active Stage Detail Panel (Interactive Walkthrough Card with Framer Motion) */}
      <AnimatePresence mode="wait">
        <motion.section
          key={activeStage.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="ps-stage-detail-panel"
          aria-live="polite"
        >
          <div className="ps-detail-grid">
            {/* Left Column: Stage Specifications & Boundaries */}
            <div className="ps-detail-card left-card">
              <div className="ps-detail-badge-row">
                <span className="ps-badge-stage">{activeStage.badge}</span>
                <span className="ps-badge-implemented">Deterministic Pipeline</span>
              </div>

              <h2 className="ps-detail-title">{activeStage.title}</h2>
              <p className="ps-detail-purpose">{activeStage.purpose}</p>

              <div className="ps-meta-block">
                <span className="ps-meta-label">Application Scope &amp; Targets:</span>
                <p className="ps-meta-value">{activeStage.scope}</p>
              </div>

              <div className="ps-meta-block">
                <span className="ps-meta-label">Backend Engine &amp; Technologies:</span>
                <p className="ps-meta-value tech-tag">{activeStage.tech}</p>
              </div>

              <div className="ps-governance-box">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                <span>
                  <strong>Operational Boundary:</strong> {activeStage.boundary}
                </span>
              </div>
            </div>

            {/* Right Column: Live Simulated Artifact / Interactive Output Inspector */}
            <div className="ps-detail-card right-card">
              <div className="ps-artifact-header">
                <div className="ps-artifact-title-group">
                  <span className="ps-artifact-live-badge">Live Output Simulation</span>
                  <h3 className="ps-artifact-title">Verified Artifact &amp; Data State</h3>
                </div>
                <span className="ps-artifact-step-pill">Stage {activeStage.step} Output</span>
              </div>

              <div className="ps-artifact-content">
                {/* Stage 1 Simulator: Data Feeds Matrix */}
                {activeStage.id === 1 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">Ingestion Feeds &amp; Master Catalogs:</div>
                    <div className="ps-sim-list">
                      {activeStage.simulatedData.feeds.map((f, i) => (
                        <div key={i} className="ps-sim-feed-row">
                          <div className="ps-feed-main">
                            <span className="ps-feed-name">{f.name}</span>
                            <span className="ps-feed-source">{f.source}</span>
                          </div>
                          <span className="ps-feed-status">{f.status}</span>
                        </div>
                      ))}
                    </div>
                    <div className="ps-sim-sample-pill">
                      <span className="pill-dot" />
                      <span>Sample: {activeStage.simulatedData.activeSample}</span>
                    </div>
                  </div>
                )}

                {/* Stage 2 Simulator: Two-Stage Validation Matrix */}
                {activeStage.id === 2 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">Two-Stage Validation Checks (Pre-Commit Guard):</div>
                    <div className="ps-sim-list">
                      {activeStage.simulatedData.checks.map((c, i) => (
                        <div key={i} className="ps-sim-check-row">
                          <div className="ps-check-main">
                            <span className="ps-check-name">{c.name}</span>
                            <span className="ps-check-detail">{c.detail}</span>
                          </div>
                          <span className="ps-check-badge pass">{c.result}</span>
                        </div>
                      ))}
                    </div>
                    <div className="ps-sim-sample-pill clean">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span>{activeStage.simulatedData.quarantineCount}</span>
                    </div>
                  </div>
                )}

                {/* Stage 3 Simulator: PostgreSQL Commit Lineage */}
                {activeStage.id === 3 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">PostgreSQL Fact Ingestion &amp; Batch Lineage:</div>
                    <div className="ps-sim-code-box">
                      <div className="code-line">
                        <span className="code-key">Upload Batch ID:</span>
                        <span className="code-val">{activeStage.simulatedData.commitBatch.uploadId}</span>
                      </div>
                      <div className="code-line">
                        <span className="code-key">Target Fact Table:</span>
                        <span className="code-val">{activeStage.simulatedData.commitBatch.targetTable}</span>
                      </div>
                      <div className="code-line">
                        <span className="code-key">Committed Intervals:</span>
                        <span className="code-val">{activeStage.simulatedData.commitBatch.rowsInserted} rows (Atomic Transaction)</span>
                      </div>
                      <div className="code-line">
                        <span className="code-key">SHA-256 Provenance:</span>
                        <span className="code-val">{activeStage.simulatedData.commitBatch.provenanceHash}</span>
                      </div>
                    </div>
                    <div className="ps-sim-sample-pill">
                      <span className="pill-dot" />
                      <span>{activeStage.simulatedData.auditEntry}</span>
                    </div>
                  </div>
                )}

                {/* Stage 4 Simulator: 12-Check Reconciliation */}
                {activeStage.id === 4 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">12-Point Cross-Source Reconciliation Audit:</div>
                    <div className="ps-sim-grid-2">
                      {activeStage.simulatedData.reconciliationMetrics.map((m, i) => (
                        <div key={i} className="ps-reconcile-card">
                          <span className="ps-reconcile-name">{m.check}</span>
                          <div className="ps-reconcile-stat">
                            <span className="ps-reconcile-val">{m.score}</span>
                            <span className="ps-reconcile-status">{m.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="ps-sim-sample-pill">
                      <span className="pill-dot" />
                      <span>{activeStage.simulatedData.notice}</span>
                    </div>
                  </div>
                )}

                {/* Stage 5 Simulator: SEC & Cost Formulations */}
                {activeStage.id === 5 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">Calculated KPIs &amp; Process SEC Formulations:</div>
                    <div className="ps-sim-list">
                      {activeStage.simulatedData.kpiCalculations.map((k, i) => (
                        <div key={i} className="ps-kpi-calc-row">
                          <div className="ps-kpi-calc-left">
                            <span className="ps-kpi-name">{k.metric}</span>
                            <span className="ps-kpi-formula">{k.formula}</span>
                          </div>
                          <span className="ps-kpi-val">{k.value}</span>
                        </div>
                      ))}
                    </div>
                    <div className="ps-sim-sample-pill">
                      <span className="pill-dot" />
                      <span>{activeStage.simulatedData.baselineStatus}</span>
                    </div>
                  </div>
                )}

                {/* Stage 6 Simulator: 4 Mathematical Detectors */}
                {activeStage.id === 6 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">Mathematical Surveillance Detector Matrix:</div>
                    <div className="ps-sim-list">
                      {activeStage.simulatedData.detectors.map((d, i) => (
                        <div key={i} className="ps-detector-row">
                          <div className="ps-detector-left">
                            <span className="ps-detector-name">{d.name}</span>
                            <span className="ps-detector-detail">{d.detail}</span>
                          </div>
                          <span className={`ps-detector-badge ${d.status.toLowerCase()}`}>
                            {d.status} ({d.confidence})
                          </span>
                        </div>
                      ))}
                    </div>
                    <div className="ps-sim-sample-pill critical">
                      <span className="pill-dot red" />
                      <span>Persistent Signal: {activeStage.simulatedData.activeSignal}</span>
                    </div>
                  </div>
                )}

                {/* Stage 7 Simulator: Evidence-Grounded AI Trace */}
                {activeStage.id === 7 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">EvidenceVerifier Agent Investigation Trace:</div>
                    <div className="ps-ai-trace-list">
                      {activeStage.simulatedData.investigationTrace.map((t, i) => (
                        <div key={i} className="ps-ai-trace-item">
                          <span className="ps-trace-step">{t.step}</span>
                          <span className="ps-trace-text">{t.text}</span>
                        </div>
                      ))}
                    </div>
                    <div className="ps-sim-sample-pill verified">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span>{activeStage.simulatedData.guarantee}</span>
                    </div>
                  </div>
                )}

                {/* Stage 8 Simulator: Synthesized Finding Card */}
                {activeStage.id === 8 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">Synthesized Energy Conservation Measure (ECM):</div>
                    <div className="ps-finding-card">
                      <div className="ps-finding-header">
                        <span className="ps-finding-id">{activeStage.simulatedData.recommendation.recId}</span>
                        <span className="ps-finding-priority high">{activeStage.simulatedData.recommendation.priority}</span>
                      </div>
                      <div className="ps-finding-title">{activeStage.simulatedData.recommendation.title}</div>
                      <div className="ps-finding-grid">
                        <div className="ps-finding-metric">
                          <span className="m-label">Annual Savings</span>
                          <span className="m-val savings">{activeStage.simulatedData.recommendation.annualSavings}</span>
                        </div>
                        <div className="ps-finding-metric">
                          <span className="m-label">Payback Period</span>
                          <span className="m-val">{activeStage.simulatedData.recommendation.paybackPeriod}</span>
                        </div>
                      </div>
                    </div>
                    <div className="ps-sim-sample-pill">
                      <span className="pill-dot" />
                      <span>State: {activeStage.simulatedData.status}</span>
                    </div>
                  </div>
                )}

                {/* Stage 9 Simulator: Corrective Action & Verification Gate */}
                {activeStage.id === 9 && (
                  <div className="ps-sim-matrix">
                    <div className="ps-sim-subtitle">Assigned Action &amp; Verification Gate:</div>
                    <div className="ps-action-card">
                      <div className="ps-action-header">
                        <span className="ps-action-id">{activeStage.simulatedData.correctiveAction.actionId}</span>
                        <span className="ps-action-status">{activeStage.simulatedData.correctiveAction.status}</span>
                      </div>
                      <div className="ps-action-task">{activeStage.simulatedData.correctiveAction.task}</div>
                      <div className="ps-action-assignee">
                        <span>Owner: <strong>{activeStage.simulatedData.correctiveAction.assignee}</strong></span>
                        <span>Due: <strong>{activeStage.simulatedData.correctiveAction.dueDate}</strong></span>
                      </div>
                      <div className="ps-action-gate">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        </svg>
                        <span>{activeStage.simulatedData.correctiveAction.verificationGate}</span>
                      </div>
                    </div>
                    <div className="ps-sim-sample-pill">
                      <span className="pill-dot" />
                      <span>Audit Trail: {activeStage.simulatedData.auditTrail}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </motion.section>
      </AnimatePresence>

      {/* 4. Completion State (Shown when on final stage) */}
      {activeStageIndex === WORKFLOW_STAGES.length - 1 && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2 }}
          className="ps-completion-banner"
        >
          <div className="ps-completion-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div className="ps-completion-content">
            <h3 className="ps-completion-title">Complete 9-Stage Operational Pipeline Verified</h3>
            <p className="ps-completion-desc">
              All 9 stages operate deterministically across Energy Intel. From file upload and schema validation through mathematical surveillance, AI evidence auditing, and corrective task assignment with an independent verification gate.
            </p>
          </div>
          <button type="button" className="ps-replay-btn" onClick={handleReset}>
            Replay Simulation
          </button>
        </motion.div>
      )}

      {/* 5. Continuous Pipeline Architecture Storyboard Grid (Replaces the 3 old tabs) */}
      <section className="ps-storyboard-section" aria-label="Continuous Operational Pipeline Architecture Storyboard">
        <div className="ps-storyboard-header">
          <div className="ps-storyboard-title-group">
            <span className="ps-storyboard-eyebrow">CONTINUOUS ARCHITECTURE FLOW</span>
            <h2 className="ps-storyboard-title">9-Stage Operational Architecture Storyboard</h2>
            <p className="ps-storyboard-desc">
              Comprehensive architectural narrative detailing each stage from raw telemetry to physical resolution. Select any card to jump to its live simulation above.
            </p>
          </div>
        </div>

        <div className="ps-storyboard-grid">
          {WORKFLOW_STAGES.map((st, idx) => {
            const isSelected = idx === activeStageIndex;
            return (
              <motion.div
                key={st.id}
                whileHover={{ y: -3, transition: { duration: 0.15 } }}
                className={`ps-storyboard-card ${isSelected ? 'is-selected' : ''}`}
                onClick={() => handleSelectStage(idx)}
                role="button"
                tabIndex={0}
                aria-label={`Inspect Stage ${st.step}: ${st.title}`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleSelectStage(idx);
                  }
                }}
              >
                <div className="ps-storyboard-card-top">
                  <div className="ps-storyboard-num-pill">
                    <span className="num">{st.step}</span>
                  </div>
                  <span className="ps-storyboard-badge">{st.badge.replace(/^Stage \d+ · /, '')}</span>
                  {isSelected && <span className="ps-storyboard-active-tag">Active</span>}
                </div>

                <h3 className="ps-storyboard-card-title">{st.title}</h3>
                <p className="ps-storyboard-card-purpose">{st.purpose}</p>

                <div className="ps-storyboard-card-tech">
                  <span className="tech-label">Engine:</span>
                  <span className="tech-value">{st.tech}</span>
                </div>

                <div className="ps-storyboard-card-boundary">
                  <span className="boundary-label">Boundary:</span>
                  <span className="boundary-value">{st.boundary}</span>
                </div>

                <div className="ps-storyboard-card-footer">
                  <span className="ps-inspect-link">
                    Inspect in Simulator &rarr;
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
