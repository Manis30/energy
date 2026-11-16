import React, { useState } from 'react';
import './platform-story/platform-story.css';

const WORKFLOW_STAGES = [
  {
    step: '01',
    title: 'Daily Telemetry & Output Upload',
    purpose: 'Factory operators submit daily CSV/Excel spreadsheets containing electrical meter intervals and line output logs.',
    relation: 'Feeds raw, uncommitted data payloads into the validation pipeline.',
    tech: ['CSV/XLSX Parser', 'FastAPI UploadFile', 'Size & Chunk Guard'],
    status: 'IMPLEMENTED',
  },
  {
    step: '02',
    title: 'Schema & Range Validation',
    purpose: 'Verifies header schemas, column types, value bounds (voltage, current, active power, units), timestamp monotonicity, and duplicate keys.',
    relation: 'Prevents corrupted, out-of-range, or malformed data from ever touching PostgreSQL fact tables.',
    tech: ['Pandas', 'OpenPyXL', 'Two-Stage Validator', 'Interactive Remediation'],
    status: 'IMPLEMENTED',
  },
  {
    step: '03',
    title: 'Authoritative Database Ingestion',
    purpose: 'Executes atomic commit into fact tables (fact_energy_meter_hourly, fact_hourly_production) stamped with unique upload_id provenance.',
    relation: 'Establishes immutable source ground-truth and upload audit trails in upload_history.',
    tech: ['SQLAlchemy Core', 'PostgreSQL 16', 'UploadHistory Lineage'],
    status: 'IMPLEMENTED',
  },
  {
    step: '04',
    title: 'Cross-Source Data Reconciliation',
    purpose: 'Executes 12 deterministic cross-validation checks comparing meter intervals with production line timestamps.',
    relation: 'Detects missing hours, clock drift, or operational discrepancies before downstream calculations run.',
    tech: ['Reconciliation Engine', 'Coverage Auditing', 'Shift Alignment Checks'],
    status: 'IMPLEMENTED',
  },
  {
    step: '05',
    title: 'Daily Analytics & SEC Formulations',
    purpose: 'Calculates active energy consumption (kWh), electricity costs (INR), carbon emissions, production throughput, scrap rates, and process Specific Energy Consumption (SEC).',
    relation: 'Supplies verified KPIs to the operational briefing and provides inputs for anomaly baselining.',
    tech: ['NumPy/SciPy', 'Tariff Tier Engine', 'Process SEC Separator', 'Factory SEC Aligner'],
    status: 'IMPLEMENTED',
  },
  {
    step: '06',
    title: 'Multi-Algorithm Anomaly Surveillance',
    purpose: 'Applies four distinct mathematical surveillance detectors: Statistical Z-Score, 24h Rolling Baseline, Power Factor Compliance (<0.90), and Zero-Production Standby Waste.',
    relation: 'Transforms raw telemetry spikes and waste into qualified anomaly signal events.',
    tech: ['Sample Z-Score Engine', 'Rolling Window Baseline', 'Standby Correlator'],
    status: 'IMPLEMENTED',
  },
  {
    step: '07',
    title: 'Operational Findings & Evidence Lineage',
    purpose: 'Correlates anomaly events into persistent operational findings, linking multi-stream evidence, detector version, and upload provenance.',
    relation: 'Bridges transient analytical alerts into a formal corporate investigation workflow.',
    tech: ['Finding Lifecycle Engine', 'Deduplication Fingerprints', 'Provenance Explorer'],
    status: 'IMPLEMENTED',
  },
  {
    step: '08',
    title: 'Deterministic Recommendation Synthesis',
    purpose: 'Generates targeted energy conservation measures (ECMs) directly derived from the verified anomaly characteristics.',
    relation: 'Provides plant engineers with actionable technical interventions rather than open-ended alerts.',
    tech: ['Rule-Based Recommendation Engine', 'Tariff ROI Modeling', 'Energy Conservation Catalog'],
    status: 'IMPLEMENTED',
  },
  {
    step: '09',
    title: 'Corrective Actions & Owner Assignment',
    purpose: 'Enables engineering management to assign discrete corrective tasks to maintenance technicians with mandatory due dates.',
    relation: 'Ensures plant floor follow-through with dedicated ownership and overdue surveillance.',
    tech: ['Action Management API', 'Overdue Tracking', 'Append-Only Action Audit Trail'],
    status: 'IMPLEMENTED',
  },
  {
    step: '10',
    title: 'Independent Resolution Verification',
    purpose: 'Requires independent engineering verification of normalized telemetry before a finding can be transitioned to RESOLVED with mandatory resolution notes.',
    relation: 'Guarantees that completing an action does not prematurely close a finding without physical verification.',
    tech: ['Lifecycle State Machine', 'Independent Verification Gate', 'Append-Only Finding Audit Log'],
    status: 'IMPLEMENTED',
  },
];

const ARCHITECTURE_LAYERS = [
  {
    name: '1. Data & Input Layer',
    tech: 'CSV, Excel (XLSX/XLS), REST/ODBC Connectors (SharePoint Graph API, MongoDB, Neon)',
    responsibilities: [
      'Daily Energy Telemetry files (hourly active kWh, PF, voltage, current per meter)',
      'Daily Production Output files (hourly good units, scrap units, downtime per line)',
      'Enterprise Connector discovery and credential-masked connection health monitoring',
      'Chunked streaming file read with strict size enforcement (MAX_UPLOAD_SIZE_MB)',
    ],
  },
  {
    name: '2. Processing & Analytical Layer',
    tech: 'Python 3.12, Pandas, OpenPyXL, NumPy, SciPy, Two-Stage File Validator',
    responsibilities: [
      'Pre-ingestion structural and semantic validation (range, types, key existence, dates)',
      'Reconciliation Engine executing 12 cross-source data consistency checks',
      'Specific Energy Consumption (SEC) formulation: SMT (kWh/board) vs FAL (kWh/phone)',
      'Deterministic mathematical surveillance (Z-score 3σ, 24h rolling, low PF, standby waste)',
    ],
  },
  {
    name: '3. Backend API & Persistence Layer',
    tech: 'FastAPI, Uvicorn, SQLAlchemy ORM, PostgreSQL 16 (Local Disposable), Alembic Migrations',
    responsibilities: [
      'Deterministic REST API endpoints (/api/energy, /api/production, /api/daily-reports, /api/findings, /api/recommendations)',
      'Kimball star-schema persistence: fact_energy_meter_hourly, fact_hourly_production, dimension tables',
      'Stateful lifecycle tracking: operational_findings, finding_occurrences, corrective_actions',
      'Immutable audit logging: finding_audit_log, recommendation_audit_log, action_audit_log',
    ],
  },
  {
    name: '4. Guardrailed AI Intelligence Layer',
    tech: 'ReAct Agent (IndustrialEnergyAgent), Claude 3.5 Sonnet via Domo Gateway, EvidenceVerifier Sub-Agent',
    responsibilities: [
      'Zero numeric hallucination architecture: all calculations remain strictly backend-owned',
      '21 deterministic domain tools covering energy, production, SEC, and ad-hoc read-only SQL',
      'EvidenceVerifier post-processor auditing every numeric claim against raw tool payload',
      'Deterministic conversational greeting router (zero tool calls for greetings, claim-free responses)',
      'Bounded exponential backoff retries (3 total attempts: 1 initial + 2 retries, 0.5s/1.0s delays)',
    ],
  },
  {
    name: '5. Frontend Presentation Layer',
    tech: 'React 18, Vite, React Router 6, Native CSS Variables (Light/Dark Theme), Chart.js / SVG',
    responsibilities: [
      '8 unified operational pages: Dashboard, Daily Operations, Energy, Production, Investigation & Actions Centre, Data Connectors, AI Assistant, Platform Story',
      'Master-detail Investigation & Actions Centre with inline provenance explorer and action tracker',
      'Vertical Stepper for Daily Operations pipeline tracking stages 1 through 8 with crash recovery',
      'Real-time Claim Verification drawer in AI Assistant displaying green verified badges',
    ],
  },
];

export default function PlatformStory() {
  const [activeTab, setActiveTab] = useState('overview');

  const scrollToSection = (id) => {
    setActiveTab(id);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="platform-story-page">
      {/* Top Hero Section */}
      <section className="ps-hero">
        <div className="ps-hero-eyebrow">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
            <polyline points="2 17 12 22 22 17"/>
            <polyline points="2 12 12 17 22 12"/>
          </svg>
          Industrial Energy Intelligence Platform &bull; System Architecture &amp; Domain Story
        </div>

        <h1 className="ps-hero-title">
          Deterministic Energy Intelligence &amp; Verified Industrial Operations
        </h1>

        <p className="ps-hero-subtitle">
          An enterprise manufacturing intelligence system built for electronics and smart device assembly plants.
          Eliminating energy waste, validating Specific Energy Consumption (SEC), automating mathematical anomaly surveillance,
          and delivering conversational intelligence grounded by an independent deterministic evidence auditor.
        </p>

        <div className="ps-hero-stats">
          <div className="ps-stat-box">
            <span className="ps-stat-value">10 Stages</span>
            <span className="ps-stat-label">End-to-End Pipeline</span>
            <span className="ps-stat-desc">From raw CSV/Excel upload to verified finding resolution</span>
          </div>
          <div className="ps-stat-box">
            <span className="ps-stat-value">4 Detectors</span>
            <span className="ps-stat-label">Mathematical Surveillance</span>
            <span className="ps-stat-desc">Z-Score (3σ), 24h Rolling, Low PF (&lt;0.90), Zero-Prod Standby</span>
          </div>
          <div className="ps-stat-box">
            <span className="ps-stat-value">21 Tools</span>
            <span className="ps-stat-label">Deterministic AI Tooling</span>
            <span className="ps-stat-desc">Zero numeric hallucination: 100% backend-calculated metrics</span>
          </div>
          <div className="ps-stat-box">
            <span className="ps-stat-value">100% Lineage</span>
            <span className="ps-stat-label">Provenance Traceability</span>
            <span className="ps-stat-desc">Upload batch ID to fact record and finding occurrence mapping</span>
          </div>
        </div>
      </section>

      {/* Quick Jump Navigation Bar */}
      <nav className="ps-nav-pills">
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => scrollToSection('overview')}
        >
          Overview
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'workflow' ? 'active' : ''}`}
          onClick={() => scrollToSection('workflow')}
        >
          Operational Workflow
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'architecture' ? 'active' : ''}`}
          onClick={() => scrollToSection('architecture')}
        >
          Technical Architecture
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'data' ? 'active' : ''}`}
          onClick={() => scrollToSection('data')}
        >
          Data &amp; Provenance
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => scrollToSection('analytics')}
        >
          Analytics &amp; Intensity
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'ai' ? 'active' : ''}`}
          onClick={() => scrollToSection('ai')}
        >
          AI &amp; Verification
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'findings' ? 'active' : ''}`}
          onClick={() => scrollToSection('findings')}
        >
          Findings &amp; Actions
        </button>
        <button
          type="button"
          className={`ps-pill-btn ${activeTab === 'roadmap' ? 'active' : ''}`}
          onClick={() => scrollToSection('roadmap')}
        >
          Roadmap &amp; Boundaries
        </button>
      </nav>

      {/* ========================================================================= */}
      {/* SECTION A: PLATFORM OVERVIEW                                              */}
      {/* ========================================================================= */}
      <section id="overview" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section A</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            Platform Purpose, Operational Value &amp; Users
          </h2>
          <p className="ps-section-subtitle">
            The operational problems addressed, key user personas, and the core distinction between historical analytics and daily operational intelligence.
          </p>
        </div>

        <div className="ps-grid-3">
          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🏭 The Industrial Challenge</h3>
              <span className="ps-badge ps-badge-impl">Problem Solved</span>
            </div>
            <div className="ps-card-body">
              <p>
                Modern high-volume device assembly plants consume millions of kilowatt-hours annually. Plant managers face severe operational blind spots:
              </p>
              <ul>
                <li><strong>Unmonitored Standby Waste:</strong> Machinery running heaters and conveyors during unstaffed breaks and line stoppages.</li>
                <li><strong>Power Factor Penalties:</strong> Industrial utility charges caused by uncalibrated inductive loads dropping PF below 0.90.</li>
                <li><strong>Misleading Unit Intensity:</strong> Cross-unit averaging that conflates printed circuit boards with fully assembled smartphones.</li>
                <li><strong>AI Hallucination Risk:</strong> Generative AI models inventing metrics or misquoting tariff figures without proof.</li>
              </ul>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">👥 User Personas &amp; Value</h3>
              <span className="ps-badge ps-badge-impl">Target Audience</span>
            </div>
            <div className="ps-card-body">
              <p>
                The platform empowers four operational stakeholders across the manufacturing enterprise:
              </p>
              <ul>
                <li><strong>Plant Energy Managers:</strong> Track daily electrical bills, carbon emissions (0.82 kg CO2e/kWh), and SEC efficiency.</li>
                <li><strong>Shift Supervisors:</strong> Detect off-shift standby power drawing and line downtime correlations.</li>
                <li><strong>Maintenance Technicians:</strong> Receive discrete corrective actions (e.g. capacitor bank tuning, conveyor auto-shutdown).</li>
                <li><strong>Executive Leadership:</strong> Query verified plant performance in natural language with zero-trust data auditability.</li>
              </ul>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">⚖️ Two Operational Paradigms</h3>
              <span className="ps-badge ps-badge-impl">Architectural Split</span>
            </div>
            <div className="ps-card-body">
              <p>
                The platform strictly decouples two fundamental operational modes:
              </p>
              <ul>
                <li><strong>Historical Analytics:</strong> Exploring long-term baseline trends (30–90 days), tariff sensitivity analysis, and macro performance exceptions across validated historical fact records.</li>
                <li><strong>Daily Operational Intelligence:</strong> Active daily workflow where operators upload reports, validate schemas, commit fact batches with provenance, reconcile cross-source logs, and manage immediate corrective actions.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION B: END-TO-END OPERATIONAL WORKFLOW                                */}
      {/* ========================================================================= */}
      <section id="workflow" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section B</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            End-to-End Operational Pipeline
          </h2>
          <p className="ps-section-subtitle">
            The sequential 10-stage pipeline guiding daily factory telemetry from initial file upload to verified finding resolution.
          </p>
        </div>

        <div className="ps-workflow-container">
          <div className="ps-stepper">
            {WORKFLOW_STAGES.map((s) => (
              <div key={s.step} className="ps-step-item">
                <div className="ps-step-badge">{s.step}</div>
                <div className="ps-step-content">
                  <div className="ps-step-title">
                    <span>{s.title}</span>
                    <span className="ps-badge ps-badge-impl">{s.status}</span>
                  </div>
                  <p className="ps-step-desc"><strong>Purpose:</strong> {s.purpose}</p>
                  <p className="ps-step-desc"><strong>Relationship to Next Stage:</strong> {s.relation}</p>
                  <div className="ps-step-tech">
                    {s.tech.map((t, idx) => (
                      <span key={idx} className="ps-tag">{t}</span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION C: TECHNICAL ARCHITECTURE                                         */}
      {/* ========================================================================= */}
      <section id="architecture" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section C</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="12 2 2 7 12 12 22 7 12 2"/>
              <polyline points="2 17 12 22 22 17"/>
              <polyline points="2 12 12 17 22 12"/>
            </svg>
            Technical Layer Architecture &amp; Real Technologies
          </h2>
          <p className="ps-section-subtitle">
            The five implemented layers forming the platform architecture, their technological stack, and core responsibilities.
          </p>
        </div>

        <div className="ps-layer-stack">
          {ARCHITECTURE_LAYERS.map((layer, idx) => (
            <div key={idx} className="ps-layer-box">
              <div className="ps-layer-header">
                <span className="ps-layer-name">{layer.name}</span>
                <span className="ps-layer-tech"><strong>Technologies:</strong> {layer.tech}</span>
              </div>
              <div className="ps-layer-items">
                {layer.responsibilities.map((resp, rIdx) => (
                  <div key={rIdx} className="ps-sub-item">
                    <span>&bull; {resp}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION D: DATA ARCHITECTURE & PROVENANCE                                 */}
      {/* ========================================================================= */}
      <section id="data" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section D</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <ellipse cx="12" cy="5" rx="9" ry="3"/>
              <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
              <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
            </svg>
            Data Architecture &amp; Full Lineage Traceability
          </h2>
          <p className="ps-section-subtitle">
            Dimensional star schema, upload provenance tracking via upload_id stamping, and unbroken audit trails.
          </p>
        </div>

        <div className="ps-grid-2">
          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">📊 Dimensional Star Schema</h3>
              <span className="ps-badge ps-badge-impl">PostgreSQL 16</span>
            </div>
            <div className="ps-card-body">
              <p>
                Structured under a Kimball dimensional modeling architecture with strict foreign key integrity:
              </p>
              <ul>
                <li><strong>Fact Tables:</strong> <code>fact_energy_meter_hourly</code> (hourly kWh, PF, voltage, current, cost) and <code>fact_hourly_production</code> (hourly good units, scrap units, downtime reason).</li>
                <li><strong>Dimension Tables:</strong> <code>dim_production_line</code> (line mapping SMT vs FAL, meter linkages), <code>dim_product</code> (SKU catalog, cycle times), <code>dim_plant</code>, <code>dim_meter</code>, <code>dim_tariff_slab</code>.</li>
                <li><strong>Staging &amp; Lineage:</strong> <code>upload_history</code> tracking every uploaded file, valid rows, rejected rows, and batch ID.</li>
              </ul>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🔗 Complete Lineage Traceability</h3>
              <span className="ps-badge ps-badge-impl">Zero-Trust Provenance</span>
            </div>
            <div className="ps-card-body">
              <p>
                Every reported analytical finding, metric, or recommendation can be traced backwards through four authoritative provenance hops:
              </p>
              <div className="ps-code-box">
                Recommendation (REC-001)<br/>
                &nbsp;&nbsp;&darr; Linked to Operational Finding<br/>
                Finding (FND-20261101-001)<br/>
                &nbsp;&nbsp;&darr; Occurrence Record (OCC-001)<br/>
                Fact Telemetry (fact_energy_meter_hourly: ID #1042)<br/>
                &nbsp;&nbsp;&darr; Upload Batch ID Stamp (upload_id: UPL-20261101-a1b2c3d4)<br/>
                Source File (UploadHistory: Daily_Energy_2026-11-01.xlsx)
              </div>
            </div>
          </div>
        </div>

        {/* Provenance Status Breakdown */}
        <div className="ps-table-wrapper">
          <table className="ps-table">
            <thead>
              <tr>
                <th>Lineage Status</th>
                <th>Database Ground Truth</th>
                <th>User Experience &amp; Guarantee</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong style={{ color: '#10b981' }}>VERIFIED (Daily Upload)</strong></td>
                <td><code>Fact record has upload_id matching UploadHistory record</code></td>
                <td>Full provenance available: filename, upload timestamp, batch ID, and audit details displayed in Provenance Explorer.</td>
              </tr>
              <tr>
                <td><strong style={{ color: '#f59e0b' }}>HISTORICAL BASELINE</strong></td>
                <td><code>Fact record upload_id IS NULL (seeded baseline data)</code></td>
                <td>Explicitly tagged as historical baseline telemetry. Prevents seeded data from falsely claiming a new daily upload occurred.</td>
              </tr>
              <tr>
                <td><strong style={{ color: '#ef4444' }}>UNLINKED / ORPHAN</strong></td>
                <td><code>Fact record upload_id does not resolve to UploadHistory</code></td>
                <td>Flagged with provenance warning badge. Downstream reconciliation highlights orphan attribution.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION E: ANALYTICS & INTELLIGENCE                                       */}
      {/* ========================================================================= */}
      <section id="analytics" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section E</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Analytical Formulations &amp; Surveillance Engines
          </h2>
          <p className="ps-section-subtitle">
            Specific Energy Consumption (SEC) domain rules, utility non-allocation policy, and four mathematical surveillance algorithms.
          </p>
        </div>

        <div className="ps-grid-3">
          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">⚡ SMT Process SEC</h3>
              <span className="ps-tag">kWh / board</span>
            </div>
            <div className="ps-card-body">
              <p>
                Measures electrical energy consumed exclusively by Surface Mount Technology pick-and-place lines (<code>MTR-SMT</code>) divided by intermediate printed circuit boards produced:
              </p>
              <div className="ps-code-box">
                SMT Process SEC = SMT Energy (kWh) / Intermediate Boards Produced
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Never averaged with finished phones; board production is an intermediate stage assembly.
              </p>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">📱 FAL Process SEC</h3>
              <span className="ps-tag">kWh / phone</span>
            </div>
            <div className="ps-card-body">
              <p>
                Measures electrical energy consumed exclusively by Final Assembly &amp; Testing lines (<code>MTR-FAL</code>) divided by finished mobile devices produced:
              </p>
              <div className="ps-code-box">
                FAL Process SEC = FAL Energy (kWh) / Final Finished Devices Produced
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Excludes ambient utilities; strictly reflects assembly, testing, and packaging line motors.
              </p>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🏢 Factory-Wide SEC</h3>
              <span className="ps-tag">kWh / phone (Aligned)</span>
            </div>
            <div className="ps-card-body">
              <p>
                Plant-wide electrical energy (process meters + ambient utilities) divided by finished assembled smartphones:
              </p>
              <div className="ps-code-box">
                Factory SEC = Total Plant Energy (kWh) / Finished Devices Produced
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Strict rule: Ambient utilities (HVAC, Chillers, Compressors) provide ambient environment to the whole building and are NEVER arbitrarily allocated to individual lines or SKUs.
              </p>
            </div>
          </div>
        </div>

        {/* Four Mathematical Surveillance Algorithms */}
        <div className="ps-card">
          <div className="ps-card-header">
            <h3 className="ps-card-title">🔍 The 4 Deterministic Anomaly Surveillance Algorithms</h3>
            <span className="ps-badge ps-badge-impl">Deterministic Engines</span>
          </div>
          <div className="ps-grid-2" style={{ marginTop: '0.5rem' }}>
            <div className="ps-sub-item">
              <strong>1. Statistical Z-Score ($z \ge 3.0\sigma$)</strong>
              <span>
                Compares hourly consumption against a qualified 30-day historical baseline distribution (mean &mu; and standard deviation &sigma;). Requires minimum 10 baseline observations. Flags severe consumption spikes and drops.
              </span>
            </div>
            <div className="ps-sub-item">
              <strong>2. 24-Hour Rolling Baseline Excursion</strong>
              <span>
                Calculates a 24-hour moving average baseline, dynamically excluding the current observation to prevent baseline poisoning. Requires minimum 12 observations. Detects localized drifts.
              </span>
            </div>
            <div className="ps-sub-item">
              <strong>3. Low Power Factor Surveillance (&lt; 0.90)</strong>
              <span>
                Scans meter power factor readings against the industrial compliance threshold of 0.90. Warns against inductive phase lag, kVA billing demand surcharges, and reactive distribution losses.
              </span>
            </div>
            <div className="ps-sub-item">
              <strong>4. Zero-Production Standby Waste</strong>
              <span>
                Correlates process meters (<code>MTR-SMT</code>, <code>MTR-FAL</code>) with production line output. Flags active kilowatt draw occurring when line production throughput is exactly 0 units (off-shift or stoppage waste).
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION F: AI INTELLIGENCE ARCHITECTURE                                   */}
      {/* ========================================================================= */}
      <section id="ai" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section F</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 8V4H8"/>
              <rect width="16" height="12" x="4" y="8" rx="2"/>
              <path d="M2 14h2"/>
              <path d="M20 14h2"/>
              <path d="M15 13v2"/>
              <path d="M9 13v2"/>
            </svg>
            Multi-Agent AI System &amp; Evidence Verification
          </h2>
          <p className="ps-section-subtitle">
            Zero-hallucination ReAct agent architecture, backend-owned calculations, and independent deterministic evidence auditing.
          </p>
        </div>

        <div className="ps-grid-3">
          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🤖 ReAct Cognitive Loop</h3>
              <span className="ps-badge ps-badge-impl">IndustrialEnergyAgent</span>
            </div>
            <div className="ps-card-body">
              <p>
                Orchestrates multi-turn conversation via Anthropic Claude 3.5 Sonnet through the Domo AI Gateway:
              </p>
              <ul>
                <li><strong>Strict Tool Reliance:</strong> The model is forbidden from performing arithmetic; it must invoke deterministic backend tools.</li>
                <li><strong>Safety Bounds:</strong> Capped at a maximum of 5 tool calls and 10 reasoning steps per turn to prevent infinite loops.</li>
                <li><strong>AST SQL Guardrail:</strong> <code>SQLValidator</code> inspects ad-hoc queries, rejecting mutations, semicolons, comments, and timeouts (&gt;5s).</li>
              </ul>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🛡️ EvidenceVerifier Sub-Agent</h3>
              <span className="ps-badge ps-badge-impl">Claim Auditor</span>
            </div>
            <div className="ps-card-body">
              <p>
                An independent deterministic auditor intercepts candidate answers before user delivery:
              </p>
              <ul>
                <li><strong>Regex Claim Extraction:</strong> Identifies all numeric assertions (kWh, INR, %, units, dates).</li>
                <li><strong>4-Dimension Audit:</strong> Matches value, unit, asset scope, and time window against raw tool payloads.</li>
                <li><strong>Hallucination Defense:</strong> Answers containing unverified claims are flagged as <code>CLAIM_UNVERIFIED</code> and highlighted in red in the UI.</li>
              </ul>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">💬 Greeting Router &amp; Resilience</h3>
              <span className="ps-badge ps-badge-impl">Deterministic Gateway</span>
            </div>
            <div className="ps-card-body">
              <p>
                Prevents wasteful tool execution and guarantees fault tolerance:
              </p>
              <ul>
                <li><strong>Conversational Greeting Router:</strong> Pure greetings (e.g. &ldquo;hello&rdquo;, &ldquo;hi&rdquo;) bypass tool execution and return instant capability overviews with <code>NO_ANALYTIC_CLAIMS</code>.</li>
                <li><strong>Bounded Transport Retries:</strong> <code>domo_client.py</code> enforces 3 total attempts (initial + 2 retries with 0.5s and 1.0s backoff).</li>
                <li><strong>Sanitized Error Masking:</strong> Sensitive provider credentials and stack traces are never leaked; mapped cleanly to HTTP 503/504.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION G: OPERATIONAL FINDINGS & ACTIONS LIFECYCLE                       */}
      {/* ========================================================================= */}
      <section id="findings" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section G</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
              <path d="M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1Z"/>
              <path d="m9 14 2 2 4-4"/>
            </svg>
            Operational Findings &amp; Corrective Actions Lifecycle
          </h2>
          <p className="ps-section-subtitle">
            Formal state machine governing anomaly triage, recommendation synthesis, corrective engineering actions, and independent resolution verification.
          </p>
        </div>

        <div className="ps-grid-2">
          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🔄 The 9-Stage Operational Lifecycle</h3>
              <span className="ps-badge ps-badge-impl">State Machine</span>
            </div>
            <div className="ps-card-body">
              <div className="ps-code-box">
                [1. Anomaly Signal Detected by Surveillance Engine]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [2. Operational Finding Created or Matched via Fingerprint]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [3. Evidence &amp; Provenance Reviewed by Plant Engineer]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [4. Finding Acknowledged (Status &rarr; ACKNOWLEDGED)]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [5. Investigation Initiated (Status &rarr; INVESTIGATING)]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [6. Targeted Recommendation Synthesized with Tariff ROI]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [7. Corrective Action Assigned to Plant Owner with Due Date]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr;<br/>
                [8. Corrective Action Executed &amp; Completed (Action &rarr; COMPLETED)]<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;&darr; (Independent Telemetry Verification Required)<br/>
                [9. Finding Resolved with Mandatory Notes (Status &rarr; RESOLVED)]
              </div>
            </div>
          </div>

          <div className="ps-card">
            <div className="ps-card-header">
              <h3 className="ps-card-title">🔐 Strict Decoupling Rationale</h3>
              <span className="ps-badge ps-badge-impl">Integrity Policy</span>
            </div>
            <div className="ps-card-body">
              <p>
                The platform enforces strict decoupling between completing an engineering task and resolving an operational finding:
              </p>
              <ul>
                <li><strong>No Automatic Finding Resolution:</strong> When an electrician completes a corrective action (e.g., &ldquo;Tune capacitor bank on SMT-L1&rdquo;), the action status transitions to <code>COMPLETED</code>. However, the operational finding remains <code>INVESTIGATING</code>.</li>
                <li><strong>Independent Verification Gate:</strong> The finding can only be closed after an energy manager reviews subsequent hourly telemetry to verify that the power factor or consumption has physically returned to normal.</li>
                <li><strong>Mandatory Audit Documentation:</strong> Resolving a finding requires mandatory resolution notes; reopening requires documented engineering justification. Both actions log permanent audit records in <code>finding_audit_log</code>.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* SECTION H: CAPABILITIES & ROADMAP                                         */}
      {/* ========================================================================= */}
      <section id="roadmap" className="ps-section">
        <div className="ps-section-header">
          <span className="ps-section-eyebrow">Section H</span>
          <h2 className="ps-section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            Current Capabilities vs. Future Engineering Roadmap
          </h2>
          <p className="ps-section-subtitle">
            Clear, honest delineation between fully implemented production capabilities, deferred features, and unsupported claims.
          </p>
        </div>

        <div className="ps-table-wrapper">
          <table className="ps-table">
            <thead>
              <tr>
                <th>Capability / Feature Scope</th>
                <th>Classification</th>
                <th>Technical Ground Truth &amp; Architecture Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Daily Operations 10-Stage Stepper Pipeline</strong></td>
                <td><span className="ps-badge ps-badge-impl">IMPLEMENTED</span></td>
                <td>Fully functional in UI and backend: file validation, ingestion, reconciliation, analytics, report synthesis, surveillance, and handoff.</td>
              </tr>
              <tr>
                <td><strong>4 Deterministic Anomaly Detectors</strong></td>
                <td><span className="ps-badge ps-badge-impl">IMPLEMENTED</span></td>
                <td>Sample Z-Score, 24h Rolling Baseline, Power Factor compliance (&lt;0.90), and Zero-Production Standby Waste fully active in Python backend.</td>
              </tr>
              <tr>
                <td><strong>Specific Energy Consumption (SEC) Formulation</strong></td>
                <td><span className="ps-badge ps-badge-impl">IMPLEMENTED</span></td>
                <td>SMT (kWh/board), FAL (kWh/phone), and Factory SEC (kWh/phone) calculated with strict ambient utility non-allocation rules.</td>
              </tr>
              <tr>
                <td><strong>Unified Investigation &amp; Actions Centre</strong></td>
                <td><span className="ps-badge ps-badge-impl">IMPLEMENTED</span></td>
                <td>Consolidated master-detail workstation with 5 authoritative KPIs, evidence provenance card, recommendation synthesis, and action tracking.</td>
              </tr>
              <tr>
                <td><strong>Zero-Hallucination ReAct Agent &amp; EvidenceVerifier</strong></td>
                <td><span className="ps-badge ps-badge-impl">IMPLEMENTED</span></td>
                <td>21 backend-owned tools, AST SQLValidator, greeting router, and deterministic regex-based 4-dimension claim verification sub-agent.</td>
              </tr>
              <tr>
                <td><strong>Cross-Source Data Reconciliation</strong></td>
                <td><span className="ps-badge ps-badge-impl">IMPLEMENTED</span></td>
                <td>12 deterministic consistency, coverage, and shift-alignment checks comparing energy meter readings with production logs.</td>
              </tr>
              <tr>
                <td><strong>Multi-Worker Celery / Redis Asynchronous Task Queue</strong></td>
                <td><span className="ps-badge ps-badge-deferred">DEFERRED</span></td>
                <td>Current runtime uses single-process Uvicorn (workers=1) with threadpool execution and in-memory locks. Multi-worker Redis queue planned for large file scale-out.</td>
              </tr>
              <tr>
                <td><strong>PostgreSQL Advisory Locks for Multi-Process Execution</strong></td>
                <td><span className="ps-badge ps-badge-deferred">DEFERRED</span></td>
                <td>Process-local threading.RLock and per-date execution locks protect state within single Uvicorn process; DB advisory locks deferred until multi-worker deployment.</td>
              </tr>
              <tr>
                <td><strong>Real-Time Sub-Second IoT Sensor Streaming</strong></td>
                <td><span className="ps-badge ps-badge-unsupported">NOT SUPPORTED</span></td>
                <td>Platform is architected for hourly batch telemetry and daily operations reports; sub-second streaming is not supported by current data models or plant hardware.</td>
              </tr>
              <tr>
                <td><strong>Automated Closed-Loop SCADA / Equipment Control</strong></td>
                <td><span className="ps-badge ps-badge-unsupported">NOT SUPPORTED</span></td>
                <td>Platform strictly operates in advisory and surveillance mode. Autonomous machinery shutdown is intentionally omitted for plant safety and human-in-the-loop compliance.</td>
              </tr>
              <tr>
                <td><strong>Predictive Machine Vibration / Motor Failure Forecasting</strong></td>
                <td><span className="ps-badge ps-badge-unsupported">NOT SUPPORTED</span></td>
                <td>Telemetric scope covers electrical power (kWh, PF, V, I) and output units; vibration, acoustic, and mechanical wear sensors are not present in the current database.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

