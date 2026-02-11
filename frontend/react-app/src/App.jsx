import React, { useState } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box } from '@mui/material';
import Dashboard from './components/Dashboard';
import ReportViewer from './components/ReportViewer';

// MUI 테마 설정 (1920x1080 해상도 기준)
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
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
        root: {
          textTransform: 'none',
          fontSize: '1rem',
        },
      },
    },
  },
});

/**
 * Enterprise STORM Frontend Application
 *
 * Architecture:
 *   Dashboard  → 기업 선택 및 리포트 생성/목록 관리
 *   ReportViewer → 리포트 진행 상태 확인 + 완료된 리포트 표시
 *
 * Flow:
 *   1. Dashboard에서 기업 선택 → 생성 요청 (POST /api/generate)
 *   2. jobId 획득 → ReportViewer로 전환
 *   3. ReportViewer에서 3초 간격 폴링 (GET /api/status/{jobId})
 *   4. COMPLETED → GET /api/report/by-job/{jobId} 로 리포트 조회
 *   5. react-markdown으로 렌더링
 *
 * State:
 *   view   - 'dashboard' | 'viewer'
 *   jobId  - 활성 Job의 UUID (null이면 대시보드)
 */

function App() {
  const [view, setView] = useState('dashboard');
  const [jobId, setJobId] = useState(null);
  const [initialStatus, setInitialStatus] = useState(null);

  /** 생성 직후 → Viewer로 전환 (폴링 필요) */
  const handleReportStart = (newJobId) => {
    setJobId(newJobId);
    setInitialStatus('PENDING');
    setView('viewer');
  };

  /** 테이블 "보기" 버튼 → Viewer로 전환 (상태에 따라 분기) */
  const handleViewReport = (targetJobId, status) => {
    setJobId(targetJobId);
    setInitialStatus((status || '').toUpperCase());
    setView('viewer');
  };

  /** Viewer에서 뒤로가기 → Dashboard 복귀 */
  const handleBackToDashboard = () => {
    setView('dashboard');
    setJobId(null);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        sx={{
          width: '100%',
          minHeight: '100vh',
          backgroundColor: '#f5f5f5',
        }}
      >
        {view === 'dashboard' ? (
          <Dashboard
            onReportStart={handleReportStart}
            onViewReport={handleViewReport}
          />
        ) : (
          <ReportViewer
            jobId={jobId}
            initialStatus={initialStatus}
            onBack={handleBackToDashboard}
          />
        )}
      </Box>
    </ThemeProvider>
  );
}

export default App;
