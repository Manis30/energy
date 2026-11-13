import React, { useRef, useState } from 'react';
import { dailyReportsApi } from '../../services/dailyReportsApi';

export default function ReportUploadSection({
  selectedFile,
  setSelectedFile,
  reportType,
  setReportType,
  sheetName,
  setSheetName,
  sheetNames,
  onValidate,
  validating,
  inspecting,
  error,
}) {
  const fileInputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleTriggerBrowse = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleClearFile = (e) => {
    e.stopPropagation();
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes && bytes !== 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="reports-section-card">
      <div className="reports-card-header">
        <div>
          <h2 className="reports-card-title">1. Report Type & Source File</h2>
          <p className="reports-card-subtitle">
            Upload daily manufacturing operational files (.csv, .xlsx, .xls) for energy or production facts.
          </p>
        </div>
        <div className="reports-template-actions">
          <span className="template-label">Templates:</span>
          <button
            type="button"
            className="reports-secondary-btn"
            onClick={() => dailyReportsApi.downloadTemplate('energy')}
            title="Download approved CSV template for Energy Submeter Readings"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Energy Template
          </button>
          <button
            type="button"
            className="reports-secondary-btn"
            onClick={() => dailyReportsApi.downloadTemplate('production')}
            title="Download approved CSV template for Hourly Production & Downtime"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Production Template
          </button>
        </div>
      </div>

      {/* Report Type Selector */}
      <div className="reports-type-selector">
        <label className="filter-label">Report Category:</label>
        <div className="reports-pill-group">
          <button
            type="button"
            className={`reports-pill-btn ${reportType === 'ENERGY' ? 'active' : ''}`}
            onClick={() => setReportType('ENERGY')}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Energy Telemetry (fact_energy_meter_hourly)
          </button>
          <button
            type="button"
            className={`reports-pill-btn ${reportType === 'PRODUCTION' ? 'active' : ''}`}
            onClick={() => setReportType('PRODUCTION')}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
            </svg>
            Production Output (fact_hourly_production)
          </button>
          <button
            type="button"
            className={`reports-pill-btn ${reportType === 'AUTO' ? 'active' : ''}`}
            onClick={() => setReportType('AUTO')}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 16v-4"/>
              <path d="M12 8h.01"/>
            </svg>
            Auto-Detect from Columns
          </button>
        </div>
      </div>

      {/* Drag & Drop Upload Zone */}
      <div
        className={`reports-dropzone ${isDragOver ? 'drag-over' : ''} ${selectedFile ? 'has-file' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleTriggerBrowse}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={handleFileChange}
          style={{ display: 'none' }}
        />

        {!selectedFile ? (
          <div className="dropzone-content">
            <div className="dropzone-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <div className="dropzone-title">
              {inspecting ? 'Inspecting Uploaded File...' : 'Drag & drop your daily report file here, or click to browse'}
            </div>
            <div className="dropzone-hint">
              Supports CSV, XLSX, and XLS up to 25 MB. Column order and sheet names may differ.
            </div>
          </div>
        ) : (
          <div className="selected-file-card">
            <div className="file-info-group">
              <div className="file-icon-badge">
                {selectedFile.name.endsWith('.csv') ? 'CSV' : 'XLS'}
              </div>
              <div className="file-details">
                <div className="file-name">{selectedFile.name}</div>
                <div className="file-meta">
                  Size: {formatFileSize(selectedFile.size)} • Type: {selectedFile.type || 'Operational Data'}
                </div>
              </div>
            </div>
            <button
              type="button"
              className="file-remove-btn"
              onClick={handleClearFile}
              title="Remove file and select another"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Multi-Sheet Selector for Excel */}
      {sheetNames && sheetNames.length > 1 && (
        <div className="reports-sheet-selector">
          <label htmlFor="sheet-select" className="filter-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '6px' }}>
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="9" y1="21" x2="9" y2="9"/>
            </svg>
            Workbook Worksheets Detected ({sheetNames.length} sheets):
          </label>
          <div className="custom-select-wrapper" style={{ maxWidth: '300px' }}>
            <select
              id="sheet-select"
              className="factory-scope-select"
              value={sheetName || sheetNames[0]}
              onChange={(e) => setSheetName(e.target.value)}
            >
              {sheetNames.map((s) => (
                <option key={s} value={s}>
                  Sheet: {s}
                </option>
              ))}
            </select>
            <span className="select-arrow" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </span>
          </div>
        </div>
      )}

      {/* Validation Trigger Button */}
      {selectedFile && (
        <div className="reports-action-row">
          <button
            type="button"
            className="reports-primary-btn"
            onClick={onValidate}
            disabled={validating || inspecting}
          >
            {validating ? (
              <>
                <span className="btn-spinner"></span>
                Validating Records & Schemas...
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 11l3 3L22 4"/>
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
                Validate & Inspect Records
              </>
            )}
          </button>
        </div>
      )}

      {error && (
        <div className="reports-error-banner">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

