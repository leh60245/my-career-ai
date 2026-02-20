/**
 * API Client (axios instance)
 *
 * Base URL: http://localhost:8000 (직접 연결)
 * Request Interceptor: 현재 Mock User ID 헤더 전송
 * Response Interceptor: 에러 핸들링 (401, 403, 400 중앙 처리)
 *
 * Mock Auth 연동: AuthContext가 setCurrentUserId()를 호출하여 사용자 전환 시 동기화.
 */
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

/** 현재 활성 사용자 ID (AuthContext에 의해 동적으로 갱신됨) */
let _currentUserId = 1;

/**
 * 현재 요청에 사용할 사용자 ID를 설정한다.
 * AuthContext의 user 변경 시 호출된다.
 * @param {number|null} userId
 */
export const setCurrentUserId = (userId) => {
    _currentUserId = userId;
};

/** 현재 요청 사용자 ID 조회 (디버그/동기화용) */
export const getCurrentUserId = () => _currentUserId;

export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    timeout: 120_000,
});

// ─── Request Interceptor ──────────────────────────────────
apiClient.interceptors.request.use(
    (config) => {
        if (_currentUserId != null) {
            config.headers['X-User-Id'] = _currentUserId;
        }
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

/** GET /api/company/trending - 최근 분석된 기업 목록 (DB 조회) */
export const fetchTrendingCompanies = async () => {
    const { data } = await apiClient.get('/api/company/trending');
    return data;
};

/** GET /api/company/search?query={name} - 기업명 검색 */
export const searchCompanies = async (query) => {
    const { data } = await apiClient.get('/api/company/search', { params: { query } });
    return data;
};

/** GET /api/reports/company/{company_name} - 특정 기업의 모든 리포트 */
export const fetchReportsByCompany = async (companyName) => {
    const { data } = await apiClient.get(`/api/reports/company/${encodeURIComponent(companyName)}`);
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

/** GET /api/report/{report_id} (PK) */
export const getReport = async (reportId) => {
    const { data } = await apiClient.get(`/api/report/${reportId}`);
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

// ─── 기업 분석 요청 플로우 (구직자 ↔ 관리자) ──────────────

/**
 * 구직자: 기업 분석 요청 등록
 * POST /api/company/analyze/request?user_id={userId}
 * @param {{ companyId: number|null, companyName: string, topic: string }} params
 * @returns {CompanyAnalysisRequestResponse}
 */
export const submitAnalysisRequest = async ({ companyId, companyName, topic }) => {
    const { data } = await apiClient.post(
        `/api/company/analyze/request`,
        { company_id: companyId, company_name: companyName, topic },
        { params: { user_id: _currentUserId } },
    );
    return data;
};

/**
 * 구직자: 내 분석 요청 목록 조회
 * GET /api/company/analyze/requests?user_id={userId}
 * @returns {CompanyAnalysisRequestResponse[]}
 */
export const getUserAnalysisRequests = async () => {
    const { data } = await apiClient.get('/api/company/analyze/requests', {
        params: { user_id: _currentUserId },
    });
    return data;
};

/**
 * 관리자: PENDING 상태 분석 요청 목록 조회
 * GET /api/admin/analyze/requests?user_id={adminId}
 * @returns {{ total: number, requests: AdminAnalysisRequestResponse[] }}
 */
export const getAdminPendingRequests = async () => {
    const { data } = await apiClient.get('/api/admin/analyze/requests', {
        params: { user_id: _currentUserId },
    });
    return data;
};

/**
 * 관리자: 분석 요청 승인
 * POST /api/admin/analyze/{jobId}/approve
 * @param {string} jobId
 * @returns {void} (204 No Content)
 */
export const approveAnalysisRequest = async (jobId) => {
    await apiClient.post(`/api/admin/analyze/${jobId}/approve`, {
        approved_by_user_id: _currentUserId,
    });
};

/**
 * 관리자: 분석 요청 반려
 * POST /api/admin/analyze/{jobId}/reject
 * @param {string} jobId
 * @param {string} rejectionReason
 * @returns {void} (204 No Content)
 */
export const rejectAnalysisRequest = async (jobId, rejectionReason) => {
    await apiClient.post(`/api/admin/analyze/${jobId}/reject`, {
        approved_by_user_id: _currentUserId,
        rejection_reason: rejectionReason,
    });
};

// ─── Mock Auth Sync Helpers ───────────────────────────────

/** 이메일로 사용자 조회 (없으면 404) */
export const getUserByEmail = async (email) => {
    const { data } = await apiClient.get('/api/user/by-email', { params: { email } });
    return data;
};

/** 개발/테스트용 사용자 생성 */
export const registerUser = async (email, role) => {
    const { data } = await apiClient.post('/api/user/register', { email, role });
    return data;
};

/**
 * Mock 사용자 동기화:
 * - 이메일로 사용자 조회
 * - 없으면 등록
 * - 등록 중 race condition(중복) 발생 시 재조회
 */
export const ensureMockUser = async ({ email, role }) => {
    try {
        return await getUserByEmail(email);
    } catch (e) {
        if (e.response?.status !== 404) throw e;
    }

    try {
        return await registerUser(email, role);
    } catch (e) {
        if (e.response?.status === 400) {
            return await getUserByEmail(email);
        }
        throw e;
    }
};
