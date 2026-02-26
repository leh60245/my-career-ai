/**
 * Application Constants
 *
 * 백엔드 Enum 값과 동기화된 전역 상수. 컴포넌트에서 직접 문자열 하드코딩 금지.
 */

// ─── User Roles (mirrors backend UserRole enum) ───────────
export const ROLES = Object.freeze({
    JOB_SEEKER: 'JOB_SEEKER',
    MANAGER: 'MANAGER',
    SYSTEM_ADMIN: 'SYSTEM_ADMIN',
});

// ─── Analysis Request / Report Job Status ─────────────────
export const REQUEST_STATUS = Object.freeze({
    PENDING: 'PENDING',
    PROCESSING: 'PROCESSING',
    COMPLETED: 'COMPLETED',
    FAILED: 'FAILED',
    REJECTED: 'REJECTED',
});

// ─── Mock Users (Development Only) ───────────────────────
// 각 user.id는 DB에 시드된 사용자 ID와 일치해야 합니다.
// scripts/seed_mock_users.py 를 실행하여 DB에 시드하세요.
export const MOCK_USERS = Object.freeze({
    JOB_SEEKER: {
        id: 1,
        email: 'jobseeker@mycareer.ai',
        name: '구직자 (테스트)',
        role: ROLES.JOB_SEEKER,
    },
    ADMIN: {
        id: 2,
        email: 'admin@mycareer.ai',
        name: '관리자 (테스트)',
        role: ROLES.MANAGER,
    },
});
