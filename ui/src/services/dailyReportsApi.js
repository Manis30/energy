/**
 * API service for Daily Reports upload, validation, ingestion, and audit history.
 */

import { apiRequest } from './apiClient';

const pendingCoverageRequests = new Map();

export const dailyReportsApi = {
  /**
   * Inspect an uploaded file (metadata, sheet names, detected format).
   * @param {File} file
   * @returns {Promise<any>}
   */
  async inspectFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    return apiRequest('/daily-reports/inspect', {
      init: {
        method: 'POST',
        body: formData,
      },
    });
  },

  /**
   * Validate report rows, constraints, dates, and schema.
   * @param {File} file
   * @param {object} options
   * @param {string} [options.reportType] - 'ENERGY' | 'PRODUCTION'
   * @param {string} [options.sheetName] - Optional worksheet name
   * @param {string} [options.confirmedDate] - Optional confirmed date (YYYY-MM-DD)
   * @param {string} [options.mode] - 'INCREMENTAL' | 'OVERWRITE_CORRECTION'
   * @returns {Promise<any>}
   */
  async validateReport(file, { reportType, sheetName, confirmedDate, mode } = {}) {
    const formData = new FormData();
    formData.append('file', file);
    if (reportType) formData.append('report_type', reportType);
    if (sheetName) formData.append('sheet_name', sheetName);
    if (confirmedDate) formData.append('confirmed_date', confirmedDate);
    if (mode) formData.append('mode', mode);

    return apiRequest('/daily-reports/validate', {
      init: {
        method: 'POST',
        body: formData,
      },
    });
  },

  /**
   * Ingest validated report records into PostgreSQL fact tables.
   * @param {File|null} file
   * @param {object} options
   * @param {string} options.reportType - 'ENERGY' | 'PRODUCTION'
   * @param {string} options.reportingDate - YYYY-MM-DD
   * @param {string} [options.plantId] - Plant identifier (e.g. IN-TN-01)
   * @param {string} [options.uploadId] - Staged or explicit upload batch ID
   * @param {string} [options.mode] - 'INCREMENTAL' | 'OVERWRITE_CORRECTION'
   * @param {string} [options.sheetName] - Optional worksheet name
   * @returns {Promise<any>}
   */
  async ingestReport(file, { reportType, reportingDate, plantId, uploadId, mode = 'INCREMENTAL', sheetName } = {}) {
    const formData = new FormData();
    if (file) formData.append('file', file);
    formData.append('report_type', reportType);
    formData.append('reporting_date', reportingDate);
    if (plantId) formData.append('plant_id', plantId);
    if (uploadId) formData.append('upload_id', uploadId);
    formData.append('mode', mode);
    if (sheetName) formData.append('sheet_name', sheetName);

    return apiRequest('/daily-reports/ingest', {
      init: {
        method: 'POST',
        body: formData,
      },
    });
  },

  /**
   * Fetch upload history audit log.
   * @param {object} [params]
   * @param {number} [params.limit=50]
   * @param {string} [params.reportType]
   * @param {string} [params.reportingDate]
   * @returns {Promise<Array<any>>}
   */
  async getUploadHistory({ limit = 50, reportType, reportingDate } = {}) {
    const params = { limit };
    if (reportType) params.report_type = reportType;
    if (reportingDate) params.reporting_date = reportingDate;

    return apiRequest('/daily-reports/history', { params });
  },

  /**
   * Get persisted energy and production coverage for an inclusive date range.
   * @param {object} params
   * @param {string} params.start_date - YYYY-MM-DD
   * @param {string} params.end_date - YYYY-MM-DD
   * @returns {Promise<any>}
   */
  async getCoverage(params) {
    const requestKey = `${params?.start_date || ''}|${params?.end_date || ''}`;
    const pendingRequest = pendingCoverageRequests.get(requestKey);
    if (pendingRequest) return pendingRequest;

    const request = apiRequest('/daily-reports/coverage', { params });
    pendingCoverageRequests.set(requestKey, request);
    try {
      return await request;
    } finally {
      if (pendingCoverageRequests.get(requestKey) === request) {
        pendingCoverageRequests.delete(requestKey);
      }
    }
  },

  /**
   * Download a standard CSV template for energy or production.
   * @param {string} reportType - 'energy' | 'production'
   */
  downloadTemplate(reportType) {
    const norm = reportType.toLowerCase();
    const url = `/api/daily-reports/template/${norm}`;
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${norm}_daily_report_template.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  },

  /**
   * Retrieve authoritative 8-stage Daily Operations pipeline status.
   * @param {string} reportingDate - YYYY-MM-DD
   * @param {string} [plantId='IN-TN-01']
   * @returns {Promise<any>}
   */
  async getPipelineStatus(reportingDate, plantId = 'IN-TN-01') {
    return apiRequest('/daily-reports/pipeline-status', {
      params: { reporting_date: reportingDate, plant_id: plantId },
    });
  },

  /**
   * Execute downstream processing stages (Reconciliation, Analytics, Report, Anomalies, Handoff).
   * @param {string} reportingDate - YYYY-MM-DD
   * @param {string} [plantId='IN-TN-01']
   * @returns {Promise<any>}
   */
  async runDownstreamPipeline(reportingDate, plantId = 'IN-TN-01') {
    return apiRequest('/daily-reports/pipeline/run-downstream', {
      params: { reporting_date: reportingDate, plant_id: plantId },
      init: { method: 'POST' },
    });
  },

  /**
   * Update or record an individual pipeline stage status.
   * @param {string} reportingDate - YYYY-MM-DD
   * @param {string} stageId - Stage key
   * @param {string} status - 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'COMPLETED_WITH_WARNINGS' | 'FAILED' | 'BLOCKED'
   * @param {string} summary - Human-readable summary
   * @param {object|null} [details] - Structured stage metrics and metadata
   * @returns {Promise<any>}
   */
  async updatePipelineStatus(reportingDate, stageId, status, summary, details = null) {
    const formData = new FormData();
    formData.append('reporting_date', reportingDate);
    formData.append('stage_id', stageId);
    formData.append('status', status);
    formData.append('summary', summary);
    if (details) {
      formData.append('details', typeof details === 'string' ? details : JSON.stringify(details));
    }

    return apiRequest('/daily-reports/pipeline-status', {
      init: {
        method: 'POST',
        body: formData,
      },
    });
  },

  /**
   * Verify actual fact records and upload ID linkage in PostgreSQL.
   * @param {object} options
   * @param {string} options.reportingDate - YYYY-MM-DD
   * @param {string} [options.plantId] - Optional plant filter
   * @param {string} [options.uploadId] - Specific upload batch ID
   * @returns {Promise<any>}
   */
  async verifyIngestion({ reportingDate, plantId, uploadId } = {}) {
    const params = { reporting_date: reportingDate };
    if (plantId) params.plant_id = plantId;
    if (uploadId) params.upload_id = uploadId;

    return apiRequest('/daily-reports/verify-ingestion', { params });
  },
};

