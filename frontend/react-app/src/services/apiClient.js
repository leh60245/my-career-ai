/**
 * API Client (axios instance)
 *
 * Base URL: /api (Vite proxy) 또는 http://localhost:8000 (직접 연결)
 * Request Interceptor: Mock User ID 헤더 전송 (MVP)
 * Response Interceptor: 에러 핸들링
 */
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

/** MVP Mock User ID */
const MOCK_USER_ID = 1;

export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    timeout: 120_000,
});

// ─── Request Interceptor ──────────────────────────────────
apiClient.interceptors.request.use(
    (config) => {
        config.headers['X-User-Id'] = MOCK_USER_ID;
        return config;
    },
    (error) => Promise.reject(error),
);

// ─── Response Interceptor ─────────────────────────────────
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        const message =
            error.response?.data?.detail ||
            error.response?.data?.message ||
            error.message ||
            'Unknown error occurred';

        console.error(`[API Error] ${error.config?.method?.toUpperCase()} ${error.config?.url}: ${message}`);

        return Promise.reject(error);
    },
);

// ─── Company Domain ───────────────────────────────────────

/** GET /api/companies */
export const fetchCompanies = async () => {
    const { data } = await apiClient.get('/api/companies');
    return data;
};

/** GET /api/topics */
export const fetchTopics = async () => {
    const { data } = await apiClient.get('/api/topics');
    return data;
};

/** GET /api/company/trending */
export const fetchTrendingCompanies = async () => {
    const { data } = await apiClient.get('/api/company/trending');
    return data;
};

/** POST /api/generate */
export const generateReport = async (companyName, topic) => {
    const { data } = await apiClient.post('/api/generate', {
        company_name: companyName,
        topic,
    });
    return data;
};

/** GET /api/status/{job_id} */
export const getJobStatus = async (jobId) => {
    const { data } = await apiClient.get(`/api/status/${jobId}`);
    return data;
};

/** GET /api/report/by-job/{job_id} */
export const getReportByJobId = async (jobId) => {
    const { data } = await apiClient.get(`/api/report/by-job/${jobId}`);
    return data;
};

/** GET /api/reports */
export const fetchReports = async ({ limit = 50, offset = 0 } = {}) => {
    const { data } = await apiClient.get('/api/reports', { params: { limit, offset } });
    return data;
};

// ─── Resume Domain ────────────────────────────────────────

/** GET /api/resume/questions (세트 목록) */
export const fetchResumeQuestions = async (userId) => {
    const { data } = await apiClient.get('/api/resume/questions', { params: { user_id: userId } });
    return data;
};

/** GET /api/resume/questions/{id} (세트 상세 + 문항) */
export const fetchResumeQuestion = async (questionId) => {
    const { data } = await apiClient.get(`/api/resume/questions/${questionId}`);
    return data;
};

/** POST /api/resume/questions (세트 생성) */
export const createResumeQuestion = async (userId, body) => {
    const { data } = await apiClient.post(`/api/resume/questions?user_id=${userId}`, body);
    return data;
};

/** POST /api/resume/items/{item_id}/drafts (초안 생성) */
export const createDraft = async (itemId, content) => {
    const { data } = await apiClient.post(`/api/resume/items/${itemId}/drafts`, { content });
    return data;
};

/** GET /api/resume/items/{item_id}/drafts (초안 히스토리) */
export const fetchDraftHistory = async (itemId) => {
    const { data } = await apiClient.get(`/api/resume/items/${itemId}/drafts`);
    return data;
};

/** POST /api/resume/guide (작성 가이드) */
export const requestGuide = async (itemId, userId) => {
    const { data } = await apiClient.post('/api/resume/guide', { item_id: itemId, user_id: userId });
    return data;
};

/** POST /api/resume/correction (첨삭) */
export const requestCorrection = async (draftId, userId) => {
    const { data } = await apiClient.post('/api/resume/correction', { draft_id: draftId, user_id: userId });
    return data;
};
