import React, { useState, useEffect, Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import PageLoader from './components/PageLoader';
import { checkBackendHealth } from './services/api';
import './theme.css';
import './app.css';

// Route-based lazy loading with React.lazy
const Dashboard = lazy(() => import('./pages/Dashboard'));
const EnergyAnalytics = lazy(() => import('./pages/EnergyAnalytics'));
const ProductionAnalytics = lazy(() => import('./pages/ProductionAnalytics'));
const AnomalyMonitoring = lazy(() => import('./pages/AnomalyMonitoring'));
const DailyAnalysis = lazy(() => import('./pages/DailyAnalysis'));
const AIAssistant = lazy(() => import('./pages/AIAssistant'));

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('iei_theme') || 'light';
  });

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

  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-wrapper">
        <Header
          theme={theme}
          onToggleTheme={toggleTheme}
          backendStatus={backendStatus}
        />
        <main className="content-area">
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/energy-analytics" element={<EnergyAnalytics />} />
              <Route path="/production-analytics" element={<ProductionAnalytics />} />
              <Route path="/anomalies" element={<AnomalyMonitoring />} />
              <Route path="/daily-analysis" element={<DailyAnalysis />} />
              <Route path="/ai-assistant" element={<AIAssistant />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
