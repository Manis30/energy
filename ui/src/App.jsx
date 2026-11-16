import React, { useState, useEffect, Suspense, lazy } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
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
const InvestigationActionsCentre = lazy(() => import('./pages/InvestigationActionsCentre'));
const DailyReports = lazy(() => import('./pages/DailyReports'));
const DataConnectors = lazy(() => import('./pages/DataConnectors'));
const AIAssistant = lazy(() => import('./pages/AIAssistant'));
const PlatformStory = lazy(() => import('./pages/PlatformStory'));

// Deep-link redirect preserving query parameters (e.g. ?finding_id=... or ?tab=...)
function RedirectToInvestigation({ defaultTab }) {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  if (defaultTab && !params.has('tab')) {
    params.set('tab', defaultTab);
  }
  const searchStr = params.toString() ? `?${params.toString()}` : '';
  return <Navigate to={`/investigation-actions${searchStr}`} replace />;
}

function RedirectPreserveQuery({ to }) {
  const location = useLocation();
  return <Navigate to={`${to}${location.search}`} replace />;
}

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

  const location = useLocation();
  const isChatPage = location.pathname === '/ai-assistant';

  return (
    <div className="app-container">
      <Sidebar />
      <div className={`main-wrapper ${isChatPage ? 'main-wrapper-chat' : ''}`}>
        <Header
          theme={theme}
          onToggleTheme={toggleTheme}
          backendStatus={backendStatus}
        />
        <main className={`content-area ${isChatPage ? 'content-area-chat' : ''}`}>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              {/* 1. Dashboard */}
              <Route path="/" element={<Dashboard />} />

              {/* 2. Daily Operations */}
              <Route path="/daily-operations" element={<DailyReports />} />
              <Route path="/daily-reports" element={<RedirectPreserveQuery to="/daily-operations" />} />
              <Route path="/daily-analysis" element={<RedirectPreserveQuery to="/daily-operations" />} />

              {/* 3. Energy Analytics */}
              <Route path="/energy-analytics" element={<EnergyAnalytics />} />

              {/* 4. Production Analytics */}
              <Route path="/production-analytics" element={<ProductionAnalytics />} />

              {/* 5. Investigation & Actions Centre (Unified Page) */}
              <Route path="/investigation-actions" element={<InvestigationActionsCentre />} />
              <Route path="/findings" element={<RedirectToInvestigation />} />
              <Route path="/anomalies" element={<RedirectToInvestigation defaultTab="surveillance" />} />
              <Route path="/recommendations-actions" element={<RedirectToInvestigation defaultTab="recommendations" />} />
              <Route path="/investigation-queue" element={<RedirectToInvestigation />} />

              {/* 6. Data Connectors */}
              <Route path="/data-connectors" element={<DataConnectors />} />
              <Route path="/connectors" element={<RedirectPreserveQuery to="/data-connectors" />} />

              {/* 7. AI Assistant */}
              <Route
                path="/ai-assistant"
                element={<AIAssistant theme={theme} onToggleTheme={toggleTheme} />}
              />

              {/* 8. Platform Story & Architecture */}
              <Route path="/platform-story" element={<PlatformStory />} />

              {/* Catch-all fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
