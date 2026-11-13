import React, { useState, useEffect } from 'react';
import ReportUploadSection from './daily-reports/ReportUploadSection';
import ValidationReviewSection from './daily-reports/ValidationReviewSection';
import IngestionActionSection from './daily-reports/IngestionActionSection';
import UploadHistorySection from './daily-reports/UploadHistorySection';
import { dailyReportsApi } from '../services/dailyReportsApi';

export default function DailyReports() {
  const [activeMainTab, setActiveMainTab] = useState('upload'); // 'upload' | 'history'

  // Upload & File State
  const [selectedFile, setSelectedFile] = useState(null);
  const [reportType, setReportType] = useState('AUTO'); // 'ENERGY' | 'PRODUCTION' | 'AUTO'
  const [sheetName, setSheetName] = useState('');
  const [sheetNames, setSheetNames] = useState([]);
  const [inspecting, setInspecting] = useState(false);

  // Validation State
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [confirmedDate, setConfirmedDate] = useState('');
  const [uploadError, setUploadError] = useState(null);

  // Ingestion State
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  // Inspect file on file selection
  useEffect(() => {
    if (!selectedFile) {
      setSheetNames([]);
      setSheetName('');
      setValidationResult(null);
      setConfirmedDate('');
      setIngestResult(null);
      setUploadError(null);
      return;
    }

    let isMounted = true;
    async function inspect() {
      setInspecting(true);
      setUploadError(null);
      setValidationResult(null);
      setIngestResult(null);

      try {
        const meta = await dailyReportsApi.inspectFile(selectedFile);
        if (!isMounted) return;

        setSheetNames(meta.sheet_names || []);
        if (meta.sheet_names && meta.sheet_names.length > 0) {
          setSheetName(meta.sheet_names[0]);
        }
        if (meta.detected_report_type && reportType === 'AUTO') {
          if (meta.detected_report_type === 'ENERGY' || meta.detected_report_type === 'PRODUCTION') {
            setReportType(meta.detected_report_type);
          }
        }
      } catch (err) {
        if (!isMounted) return;
        setUploadError(err.message || 'Unable to inspect uploaded file.');
      } finally {
        if (isMounted) setInspecting(false);
      }
    }

    inspect();
    return () => {
      isMounted = false;
    };
  }, [selectedFile]);

  // Handle Validation
  const handleValidate = async (targetDate = null, targetMode = 'INCREMENTAL') => {
    if (!selectedFile) return;

    setValidating(true);
    setUploadError(null);
    setIngestResult(null);

    const effectiveDate = targetDate || confirmedDate || undefined;
    const effectiveType = reportType === 'AUTO' ? undefined : reportType;

    try {
      const res = await dailyReportsApi.validateReport(selectedFile, {
        reportType: effectiveType,
        sheetName: sheetName || undefined,
        confirmedDate: effectiveDate,
        mode: targetMode,
      });

      setValidationResult(res);
      if (res.confirmed_date) {
        setConfirmedDate(res.confirmed_date);
      } else if (res.detected_dates && res.detected_dates.length > 0) {
        setConfirmedDate(res.detected_dates[0]);
      }
      if (res.summary?.report_type && reportType === 'AUTO') {
        setReportType(res.summary.report_type);
      }
    } catch (err) {
      console.error('Validation error:', err);
      setUploadError(err.message || 'Validation request failed.');
      setValidationResult(null);
    } finally {
      setValidating(false);
    }
  };

  const handleRevalidateWithDate = () => {
    handleValidate(confirmedDate);
  };

  // Handle Ingestion
  const handleIngest = async (mode = 'INCREMENTAL') => {
    if (!selectedFile || !confirmedDate) return;

    setIngesting(true);
    setUploadError(null);

    const effectiveType =
      validationResult?.summary?.report_type || (reportType === 'AUTO' ? 'ENERGY' : reportType);

    try {
      const res = await dailyReportsApi.ingestReport(selectedFile, {
        reportType: effectiveType,
        reportingDate: confirmedDate,
        mode,
        sheetName: sheetName || undefined,
      });

      setIngestResult(res);
      setHistoryRefreshKey((k) => k + 1);
    } catch (err) {
      console.error('Ingestion error:', err);
      setUploadError(err.message || 'Failed to ingest records into database.');
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="dashboard-container daily-reports-page">
      {/* Top Header Card */}
      <div className="dashboard-header-card reports-page-header">
        <div className="analytics-header-top">
          <div className="dashboard-title-group">
            <span className="dashboard-title-badge">Data Ingestion Engine</span>
            <h1 className="dashboard-title">Daily Reports Ingestion</h1>
            <p className="dashboard-subtitle">
              Validate, reconcile, and transactionally store daily energy submeter readings and production telemetry into Neon PostgreSQL.
            </p>
          </div>

          <div className="reports-main-tab-nav">
            <button
              type="button"
              className={`reports-main-tab-btn ${activeMainTab === 'upload' ? 'active' : ''}`}
              onClick={() => setActiveMainTab('upload')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              Upload & Ingest
            </button>
            <button
              type="button"
              className={`reports-main-tab-btn ${activeMainTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveMainTab('history')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              Upload History & Audit
            </button>
          </div>
        </div>
      </div>

      {activeMainTab === 'upload' ? (
        <div className="reports-layout">
          {/* Step 1: Upload & File Selection */}
          <ReportUploadSection
            selectedFile={selectedFile}
            setSelectedFile={setSelectedFile}
            reportType={reportType}
            setReportType={setReportType}
            sheetName={sheetName}
            setSheetName={setSheetName}
            sheetNames={sheetNames}
            onValidate={() => handleValidate()}
            validating={validating}
            inspecting={inspecting}
            error={uploadError}
          />

          {/* Step 2: Validation Summary & Date Confirmation */}
          <ValidationReviewSection
            validationResult={validationResult}
            confirmedDate={confirmedDate}
            setConfirmedDate={setConfirmedDate}
            onRevalidateWithDate={handleRevalidateWithDate}
            validating={validating}
          />

          {/* Step 3: Ingestion Configuration & Database Commit */}
          <IngestionActionSection
            validationResult={validationResult}
            confirmedDate={confirmedDate}
            onIngest={handleIngest}
            ingesting={ingesting}
            ingestResult={ingestResult}
          />
        </div>
      ) : (
        <UploadHistorySection refreshTrigger={historyRefreshKey} />
      )}
    </div>
  );
}

