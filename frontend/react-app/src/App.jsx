import React, { useState, useCallback } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box, Alert } from '@mui/material';
import { AuthProvider } from './contexts/AuthContext';
import { ResumeProvider } from './contexts/ResumeContext';
import { MainLayout } from './layouts/MainLayout';
import { Home } from './pages/Home';
import { CompanyAnalysis } from './pages/CompanyAnalysis';
import { ResumeCoaching } from './pages/ResumeCoaching';
import { AdminDashboard } from './pages/AdminDashboard';
import ReportViewer from './components/ReportViewer';
import { useAuth } from './contexts/AuthContext';

// MUI theme (1920x1080 기준)
const theme = createTheme({
  palette: {
    primary: { main: '#1565c0' },
    secondary: { main: '#e91e63' },
    background: { default: '#f5f7fa', paper: '#ffffff' },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontSize: '0.9rem', borderRadius: 8 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 8 },
      },
    },
  },
});

/**
 * My Career AI - Main Application
 *
 * Pages:
 *   home     - 홈
 *   company  - 기업 분석 (검색 + 추천 + STORM 리포트 생성)
 *   resume   - 자소서 코칭 (2-Column Split View)
 *   viewer   - 리포트 뷰어 (폴링 + 마크다운 렌더링)
 *   admin    - 관리자 대시보드 (ADMIN 전용, 라우터 레벨 권한 검사)
 *
 * Navigation: MainLayout 사이드바를 통한 state 기반 전환
 */

/**
 * AppRouter - AuthContext에 접근하여 페이지 렌더링 및 권한 가드를 담당.
 * AuthProvider 내부에 위치해야 useAuth()를 사용할 수 있음.
 */
const AppRouter = () => {
  const { isAdmin } = useAuth();

  const [currentPage, setCurrentPage] = useState('home');
  const [jobId, setJobId] = useState(null);
  const [initialStatus, setInitialStatus] = useState(null);
  const [viewerCompanyName, setViewerCompanyName] = useState(null);

  /** 기업 분석 -> ReportViewer 전환 (단일 리포트 - 폴링 모드) */
  const handleViewReport = useCallback((targetJobId, status) => {
    setJobId(targetJobId);
    setViewerCompanyName(null);
    setInitialStatus((status || '').toUpperCase());
    setCurrentPage('viewer');
  }, []);

  /** 기업 분석 -> ReportViewer 전환 (아코디언 모드 - 기업 전체 리포트) */
  const handleViewCompanyReports = useCallback((companyName) => {
    setViewerCompanyName(companyName);
    setJobId(null);
    setInitialStatus(null);
    setCurrentPage('viewer');
  }, []);

  /** ReportViewer 뒤로가기 -> 기업 분석 복귀 */
  const handleBackFromViewer = useCallback(() => {
    setCurrentPage('company');
    setJobId(null);
    setViewerCompanyName(null);
  }, []);

  /** 사이드바 네비게이션 — admin 페이지는 권한 검사 후 진입 */
  const handleNavigate = useCallback((page) => {
    if (page === 'admin' && !isAdmin) {
      // 비인가 접근 차단: 권한 없으면 home으로 fallback
      setCurrentPage('home');
      return;
    }
    setCurrentPage(page);
  }, [isAdmin]);

  /** 페이지 렌더링 */
  const renderPage = () => {
    // admin 라우트 권한 가드 (비인가 직접 접근 방어)
    if (currentPage === 'admin' && !isAdmin) {
      return (
        <Box sx={{ p: 4 }}>
          <Alert severity="error">관리자 권한이 없습니다. (403 Forbidden)</Alert>
        </Box>
      );
    }

    switch (currentPage) {
      case 'home':
        return <Home onNavigate={handleNavigate} />;
      case 'company':
        return (
          <CompanyAnalysis
            onViewReport={handleViewReport}
            onViewCompanyReports={handleViewCompanyReports}
          />
        );
      case 'resume':
        return <ResumeCoaching />;
      case 'viewer':
        return (
          <ReportViewer
            jobId={jobId}
            companyName={viewerCompanyName}
            initialStatus={initialStatus}
            onBack={handleBackFromViewer}
          />
        );
      case 'admin':
        return <AdminDashboard />;
      default:
        return <Home onNavigate={handleNavigate} />;
    }
  };

  return (
    <MainLayout currentPage={currentPage} onNavigate={handleNavigate}>
      {renderPage()}
    </MainLayout>
  );
};

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <ResumeProvider>
          <AppRouter />
        </ResumeProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
