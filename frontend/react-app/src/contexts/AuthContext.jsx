/**
 * AuthContext - MVP 사용자 인증 상태 관리
 *
 * MVP 단계에서는 이메일 입력만으로 세션을 유지한다.
 * 실제 JWT 인증은 향후 구현.
 */
import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

const AuthContext = createContext(null);

/** MVP Mock User */
const DEFAULT_USER = {
    id: 1,
    email: 'demo@mycareer.ai',
    name: 'Demo User',
    role: 'JOB_SEEKER',
};

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(DEFAULT_USER);
    const [isAuthenticated, setIsAuthenticated] = useState(true);

    /** MVP: 이메일 입력만으로 로그인 */
    const login = useCallback((email, name = 'User') => {
        setUser({ ...DEFAULT_USER, email, name });
        setIsAuthenticated(true);
    }, []);

    const logout = useCallback(() => {
        setUser(null);
        setIsAuthenticated(false);
    }, []);

    const value = useMemo(
        () => ({ user, isAuthenticated, login, logout }),
        [user, isAuthenticated, login, logout],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
};
