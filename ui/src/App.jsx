import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Dashboard from './components/dashboard/Dashboard';
import { checkBackendHealth } from './services/api';
import './theme.css';
import './app.css';

const BASE_PLACEHOLDER_INFO = {
  dashboard: {
    title: 'Industrial Energy & Production Overview',
    description: 'Central operations monitoring hub. Verified KPIs, meter summaries, and real-time production-energy ratios will be displayed here once connected to validated backend analytics.',
    details: [
      'Source Datasets: 4 approved factory files verified',
      'Calculations: Deterministic backend calculation services',
      'Database: Neon PostgreSQL data store foundation ready',
    ],
  },
  'energy-analytics': {
    title: 'Energy Consumption & Meter Analytics',
    description: 'Detailed analysis of factory energy meters, interval consumption, demand peaks, and power factor distributions across monitored production zones.',
    details: [
      'Temporal granularity: Hourly intervals and daily rollups',
      'Boundary verification: Submeter isolation to prevent double counting',
    ],
  },
  'production-analytics': {
    title: 'Production Performance & Product Correlation',
    description: 'Tracking manufacturing output by production line, shift, and product SKU to contextualize plant energy consumption.',
    details: [
      'Lines: SMT lines and Final Assembly lines',
      'Products: Aster 15 & Aster Pro variants',
    ],
  },
  anomalies: {
    title: 'Automated Energy Anomaly Detection',
    description: 'Deterministic identification of statistical deviations, off-hour baseline spikes, and non-production consumption events.',
    details: [
      'Detection methods: Historical rolling baselines and standard deviations',
      'Investigation guidance: Operational recommendations and severity ratings',
    ],
  },
  'daily-analysis': {
    title: 'Automated Daily Energy Analysis',
    description: 'One-click daily energy reporting workflow generating verified executive summaries, anomaly audits, and evidence-backed energy savings actions.',
    details: [
      'Action: Run Today\'s Energy Analysis trigger ready for integration',
      'Persistence: Neon report storage and historical audit log',
    ],
  },
  'ai-assistant': {
    title: 'Conversational Energy Intelligence Assistant',
    description: 'Interactive analytical assistant powered by LangChain and Domo AI Services with deterministic tools and read-only database query execution.',
    details: [
      'Safety: Read-only analytics connection with strict single-statement validation',
      'Traceability: Direct inspection of tool inputs, outputs, and execution steps',
    ],
  },
};

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('iei_theme') || 'light';
  });

  const [activeNav, setActiveNav] = useState('dashboard');
  const [backendStatus, setBackendStatus] = useState({
    loading: true,
    connected: false,
    version: null,
    error: null,
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('iei_theme', theme);
  }, [theme]);

  useEffect(() => {
    let isMounted = true;
    async function verifyBackend() {
      setBackendStatus({ loading: true, connected: false, version: null, error: null });
      const result = await checkBackendHealth();
      if (!isMounted) return;
      if (result.success && result.data?.status === 'ok') {
        setBackendStatus({
          loading: false,
          connected: true,
          version: result.data.version,
          error: null,
        });
      } else {
        setBackendStatus({
          loading: false,
          connected: false,
          version: null,
          error: result.error || 'Backend unavailable',
        });
      }
    }

    verifyBackend();
    return () => {
      isMounted = false;
    };
  }, []);

  const toggleTheme = () => {
    setTheme((prevTheme) => (prevTheme === 'light' ? 'dark' : 'light'));
  };

  const currentInfo = BASE_PLACEHOLDER_INFO[activeNav] || BASE_PLACEHOLDER_INFO.dashboard;

  const dynamicDetails = [...currentInfo.details];
  if (activeNav === 'dashboard') {
    if (backendStatus.loading) {
      dynamicDetails.push('API Integration: Connecting to FastAPI backend via Vite proxy...');
    } else if (backendStatus.connected) {
      dynamicDetails.push(`API Integration: FastAPI backend connected (v${backendStatus.version}) via /api proxy`);
    } else {
      dynamicDetails.push(`API Integration: Offline (${backendStatus.error})`);
    }
  }

  return (
    <div className="app-container">
      <Sidebar activeNav={activeNav} onNavigate={setActiveNav} />
      <div className="main-wrapper">
        <Header
          activeNav={activeNav}
          theme={theme}
          onToggleTheme={toggleTheme}
          backendStatus={backendStatus}
        />
        <main className="content-area">
          {activeNav === 'dashboard' ? (
            <Dashboard />
          ) : (
            <div className="placeholder-card">
              <div className="placeholder-header">
                <h2 className="placeholder-heading">{currentInfo.title}</h2>
                <p className="placeholder-desc">{currentInfo.description}</p>
              </div>
              <div className="placeholder-details">
                {dynamicDetails.map((detail, idx) => (
                  <div key={idx} className="placeholder-item">
                    <span className="item-bullet">›</span>
                    <span>{detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
