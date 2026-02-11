/**
 * API Service Layer
 * Backend API(localhost:8000)와의 통신을 담당합니다.
 *
 * Backend Endpoints:
 *   GET  /                             → Health Check
 *   GET  /api/companies                → CompanyResponse[]
 *   GET  /api/topics                   → [{id, label}]
 *   POST /api/generate                 → ReportJobResponse
 *   GET  /api/status/{job_id}          → 메모리: {job_id, status, progress, message, report_id}
 *                                        DB 폴백: ReportJobResponse
 *   GET  /api/report/{report_id}       → GeneratedReportResponse  (PK: int)
 *   GET  /api/report/by-job/{job_id}   → GeneratedReportResponse  (Job UUID)
 *   GET  /api/reports?limit&offset     → ReportListResponse {total, reports: ReportSummary[]}
 */

import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Health ───────────────────────────────────────────────

/** GET / */
export const healthCheck = async () => {
  const { data } = await apiClient.get('/');
  return data;
};

// ─── Reference Data ───────────────────────────────────────

/**
 * 기업 목록 조회
 * GET /api/companies → CompanyResponse[]
 * 각 항목: { id, company_name, corp_code, stock_code, sector, ... }
 */
export const fetchCompanies = async () => {
  const { data } = await apiClient.get('/api/companies');
  return data;
};

/**
 * 분석 주제 목록 조회
 * GET /api/topics → [{id, label}]
 */
export const fetchTopics = async () => {
  const { data } = await apiClient.get('/api/topics');
  return data;
};

// ─── Report Generation ───────────────────────────────────

/**
 * 리포트 생성 요청
 * POST /api/generate
 * @param {string} companyName - 회사명
 * @param {string} topic       - 분석 주제
 * @returns {ReportJobResponse} { job_id, status, company_name, topic, error_message, created_at, updated_at }
 */
export const generateReport = async (companyName, topic) => {
  const { data } = await apiClient.post('/api/generate', {
    company_name: companyName,
    topic,
  });
  return data;
};

// ─── Job Status (Polling) ─────────────────────────────────

/**
 * 작업 상태 조회
 * GET /api/status/{job_id}
 *
 * 메모리 응답: { job_id, status, progress, message, report_id }
 * DB 폴백:    { job_id, status, company_name, topic, error_message, ... }
 */
export const getJobStatus = async (jobId) => {
  const { data } = await apiClient.get(`/api/status/${jobId}`);
  return data;
};

// ─── Report Retrieval ─────────────────────────────────────

/**
 * 리포트 조회 (PK)
 * GET /api/report/{report_id}
 * @param {number} reportId
 */
export const getReport = async (reportId) => {
  const { data } = await apiClient.get(`/api/report/${reportId}`);
  return data;
};

/**
 * 리포트 조회 (Job ID)
 * GET /api/report/by-job/{job_id}
 * @param {string} jobId - UUID
 */
export const getReportByJobId = async (jobId) => {
  const { data } = await apiClient.get(`/api/report/by-job/${jobId}`);
  return data;
};

// ─── Report List ──────────────────────────────────────────

/**
 * 리포트(Job) 목록 조회
 * GET /api/reports?limit&offset
 * @param {{ limit?: number, offset?: number }} params
 * @returns {{ total: number, reports: ReportSummary[] }}
 *   ReportSummary: { job_id, company_name, topic, status, created_at, updated_at }
 */
export const fetchReports = async ({ limit = 50, offset = 0 } = {}) => {
  const { data } = await apiClient.get('/api/reports', {
    params: { limit, offset },
  });
  return data;
};

export default apiClient;
