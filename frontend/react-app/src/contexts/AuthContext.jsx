/**
 * AuthContext - MVP 사용자 인증 상태 관리
 *
 * Mock Auth: MOCK_USERS 상수로 구직자/관리자 전환 지원.
 * 실제 JWT 인증으로 전환 시 Provider 내부 로직만 교체하면 됨.
 */
import React, { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';
import { MOCK_USERS, ROLES } from '../constants';
import { ensureMockUser, setCurrentUserId } from '../services/apiClient';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(MOCK_USERS.JOB_SEEKER);
    const [isAuthenticated, setIsAuthenticated] = useState(true);

    // user 변경 시 DB 사용자와 동기화 후 apiClient 요청 헤더 반영
    useEffect(() => {
        let isCancelled = false;

        const syncMockUser = async () => {
            if (!user) {
                setCurrentUserId(null);
                return;
            }

            try {
                const dbUser = await ensureMockUser({ email: user.email, role: user.role });
                if (isCancelled) return;

                setCurrentUserId(dbUser.id);

                if (dbUser.id !== user.id || dbUser.role !== user.role) {
                    setUser((prev) => {
                        if (!prev) return prev;
                        return {
                            ...prev,
                            id: dbUser.id,
                            role: dbUser.role,
                            email: dbUser.email,
                        };
                    });
                }
            } catch {
                // 동기화 실패 시 기존 값으로 동작 유지
                setCurrentUserId(user.id ?? null);
            }
        };

        syncMockUser();

        return () => {
            isCancelled = true;
        };
    }, [user]);

    /** MVP: 이메일 입력만으로 로그인 */
    const login = useCallback((email, name = 'User') => {
        setUser({ ...MOCK_USERS.JOB_SEEKER, email, name });
        setIsAuthenticated(true);
    }, []);

    const logout = useCallback(() => {
        setUser(null);
        setIsAuthenticated(false);
        setCurrentUserId(null);
    }, []);

    /** 구직자 ↔ 관리자 역할 전환 (Mock Auth 전용) */
    const switchRole = useCallback(() => {
        setUser((prev) =>
            prev?.role === ROLES.JOB_SEEKER ? MOCK_USERS.ADMIN : MOCK_USERS.JOB_SEEKER
        );
    }, []);

    /** 관리자 여부 */
    const isAdmin = user?.role === ROLES.MANAGER || user?.role === ROLES.SYSTEM_ADMIN;

    const value = useMemo(
        () => ({ user, isAuthenticated, isAdmin, login, logout, switchRole }),
        [user, isAuthenticated, isAdmin, login, logout, switchRole],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
};
