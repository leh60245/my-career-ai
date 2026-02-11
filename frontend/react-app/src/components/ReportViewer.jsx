import React, { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Box,
  CircularProgress,
  Typography,
  Alert,
  Button,
  Chip,
  Divider,
  LinearProgress,
} from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { getJobStatus, getReport, getReportByJobId } from '../services/apiService';
import '../styles/ReportViewer.css';

/**
 * ReportViewer 컴포넌트
 *
 * Props:
 *   jobId  - Job UUID (필수)
 *   onBack - 대시보드 복귀 콜백
 *
 * 흐름:
 *   1. GET /api/status/{jobId} 로 상태 폴링 (3초 간격)
 *   2. COMPLETED → GET /api/report/by-job/{jobId} 로 리포트 조회
 *   3. FAILED → 에러 메시지 표시
 *
 * Backend 응답 스키마:
 *   메모리 상태: { job_id, status, progress, message, report_id }
 *   DB 폴백:    { job_id, status, company_name, topic, error_message, ... }
 *   리포트:     { id, job_id, company_name, topic, report_content, toc_text,
 *                 references_data, conversation_log, meta_info, model_name, created_at }
 */

const POLL_INTERVAL = 3000;

const ReportViewer = ({ jobId, initialStatus, onBack }) => {
  // phase: 'polling' | 'loading' | 'done' | 'error'
  // COMPLETED → 폴링 없이 바로 리포트 로드
  const deriveInitialPhase = () => {
    const s = (initialStatus || '').toUpperCase();
    if (s === 'COMPLETED') return 'loading';
    if (s === 'FAILED') return 'error';
    return 'polling';
  };
  const [phase, setPhase] = useState(deriveInitialPhase);
  const [statusInfo, setStatusInfo] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(
    deriveInitialPhase() === 'error' ? '작업이 실패했습니다.' : null
  );
  const [pollingCount, setPollingCount] = useState(0);

  useEffect(() => {
    if (jobId) return;
    setError('유효한 작업 ID가 없습니다.');
    setPhase('error');
  }, [jobId]);

  // ─── Phase 1: Status Polling ────────────────────────────
  useEffect(() => {
    if (!jobId || phase !== 'polling') return;

    let cancelled = false;

    const checkStatus = async () => {
      try {
        const data = await getJobStatus(jobId);
        if (cancelled) return;

        setStatusInfo(data);
        const s = (data.status || '').toUpperCase();

        if (s === 'COMPLETED') {
          setPhase('loading');
        } else if (s === 'FAILED') {
          setError(data.error_message || data.message || '작업이 실패했습니다.');
          setPhase('error');
        }
        // PENDING, PROCESSING → 계속 polling
      } catch (err) {
        if (cancelled) return;
        console.error('Status check failed:', err);
        setError('상태 확인에 실패했습니다. 서버 연결을 확인하세요.');
        setPhase('error');
      }
    };

    checkStatus();
    const interval = setInterval(() => {
      checkStatus();
      setPollingCount((c) => c + 1);
    }, POLL_INTERVAL);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId, phase]);

  // ─── Phase 2: Load Report ──────────────────────────────
  useEffect(() => {
    if (phase !== 'loading' || !jobId) return;

    let cancelled = false;

    const loadReport = async () => {
      try {
        let reportData;
        // 메모리에 report_id(PK)가 있으면 직접 조회, 없으면 job_id로 조회
        if (statusInfo?.report_id) {
          reportData = await getReport(statusInfo.report_id);
        } else {
          reportData = await getReportByJobId(jobId);
        }
        if (cancelled) return;
        setReport(reportData);
        setPhase('done');
      } catch (err) {
        if (cancelled) return;
        console.error('Report fetch failed:', err);
        setError('리포트를 불러올 수 없습니다.');
        setPhase('error');
      }
    };

    loadReport();
    return () => { cancelled = true; };
  }, [phase, statusInfo, jobId]);

  // ─── Helpers ────────────────────────────────────────────
  const currentStatus = (statusInfo?.status || '').toUpperCase();
  const progress = statusInfo?.progress ?? 0;
  const message = statusInfo?.message || '';

  const statusLabel = {
    PENDING: '대기 중',
    PROCESSING: '처리 중',
    COMPLETED: '완료',
    FAILED: '실패',
  };

  // ─── Render: Polling (PENDING / PROCESSING) ─────────────
  if (phase === 'polling') {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={60} />
            <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
              {currentStatus === 'PENDING' ? '⏳ 작업 대기 중...' : '📋 리포트 생성 중...'}
            </Typography>
            <Typography variant="body1" color="textSecondary">
              {message || 'AI가 데이터를 분석하고 있습니다. 잠시만 기다려주세요.'}
            </Typography>

            {/* Progress Bar */}
            {progress > 0 && (
              <Box sx={{ width: '80%', mt: 1 }}>
                <LinearProgress
                  variant="determinate"
                  value={progress}
                  sx={{ height: 10, borderRadius: 5 }}
                />
                <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
                  {progress}%
                </Typography>
              </Box>
            )}

            <Chip
              label={`상태: ${statusLabel[currentStatus] || currentStatus}`}
              color={currentStatus === 'PENDING' ? 'info' : 'warning'}
              variant="outlined"
              size="small"
            />
            <Typography variant="caption" color="textSecondary">
              (폴링: {pollingCount}회)
            </Typography>

            <Button variant="outlined" onClick={onBack} sx={{ mt: 2 }}>
              ← 대시보드로 돌아가기
            </Button>
          </Box>
        </Paper>
      </Container>
    );
  }

  // ─── Render: Error ──────────────────────────────────────
  if (phase === 'error') {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4 }}>
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
          {statusInfo?.error_message && statusInfo.error_message !== error && (
            <Typography
              variant="body2"
              component="pre"
              sx={{
                backgroundColor: '#f5f5f5',
                p: 2,
                borderRadius: 1,
                overflow: 'auto',
                mb: 2,
                fontSize: '0.85rem',
                whiteSpace: 'pre-wrap',
              }}
            >
              {statusInfo.error_message}
            </Typography>
          )}
          <Button variant="contained" onClick={onBack}>
            ← 대시보드로 돌아가기
          </Button>
        </Paper>
      </Container>
    );
  }

  // ─── Render: Loading Report ─────────────────────────────
  if (phase === 'loading') {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={50} />
            <Typography variant="body1">리포트를 불러오는 중...</Typography>
          </Box>
        </Paper>
      </Container>
    );
  }

  // ─── Render: Report ─────────────────────────────────────
  if (phase === 'done' && report) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        {/* 헤더 */}
        <Paper elevation={3} sx={{ p: 3, mb: 3, backgroundColor: '#f5f5f5' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 1 }}>
                {report.company_name}
              </Typography>
              <Typography variant="body1" color="textSecondary">
                주제: {report.topic}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap' }}>
                <Chip label={`모델: ${report.model_name}`} variant="outlined" />
                {report.created_at && (
                  <Chip
                    label={`생성: ${new Date(report.created_at).toLocaleDateString('ko-KR')}`}
                    variant="outlined"
                  />
                )}
              </Box>
            </Box>
            <Button variant="outlined" onClick={onBack}>
              ← 돌아가기
            </Button>
          </Box>
        </Paper>

        {/* 리포트 콘텐츠 */}
        <Paper elevation={2} sx={{ p: 4 }}>
          <div className="markdown-container">
            <ReactMarkdown
              components={{
                h1: ({ node, ...props }) => (
                  <Typography variant="h3" component="h1" sx={{ mt: 3, mb: 2, fontWeight: 'bold' }} {...props} />
                ),
                h2: ({ node, ...props }) => (
                  <Typography variant="h5" component="h2" sx={{ mt: 2.5, mb: 1.5, fontWeight: 'bold' }} {...props} />
                ),
                h3: ({ node, ...props }) => (
                  <Typography variant="h6" component="h3" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }} {...props} />
                ),
                p: ({ node, ...props }) => (
                  <Typography variant="body1" sx={{ mb: 1.5, lineHeight: 1.7 }} {...props} />
                ),
                ul: ({ node, ...props }) => (
                  <Box component="ul" sx={{ ml: 2, mb: 1.5 }} {...props} />
                ),
                ol: ({ node, ...props }) => (
                  <Box component="ol" sx={{ ml: 2, mb: 1.5 }} {...props} />
                ),
                li: ({ node, ...props }) => (
                  <Box component="li" sx={{ mb: 0.5, lineHeight: 1.6 }} {...props} />
                ),
                table: ({ node, ...props }) => (
                  <Box sx={{
                    overflowX: 'auto',
                    mb: 2,
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                  }}>
                    <table style={{
                      width: '100%',
                      borderCollapse: 'collapse',
                      fontSize: '0.95rem',
                    }} {...props} />
                  </Box>
                ),
                thead: ({ node, ...props }) => (
                  <thead style={{ backgroundColor: '#f0f0f0' }} {...props} />
                ),
                th: ({ node, ...props }) => (
                  <th style={{
                    padding: '12px',
                    textAlign: 'left',
                    borderBottom: '2px solid #ddd',
                    fontWeight: 'bold',
                  }} {...props} />
                ),
                td: ({ node, ...props }) => (
                  <td style={{
                    padding: '10px 12px',
                    borderBottom: '1px solid #eee',
                  }} {...props} />
                ),
                code: ({ node, inline, ...props }) => (
                  inline ? (
                    <code style={{
                      backgroundColor: '#f5f5f5',
                      padding: '2px 6px',
                      borderRadius: '3px',
                      fontFamily: 'monospace',
                    }} {...props} />
                  ) : (
                    <pre style={{
                      backgroundColor: '#f5f5f5',
                      padding: '12px',
                      borderRadius: '4px',
                      overflowX: 'auto',
                      marginBottom: '1.5rem',
                    }}>
                      <code {...props} />
                    </pre>
                  )
                ),
                blockquote: ({ node, ...props }) => (
                  <Box
                    component="blockquote"
                    sx={{
                      borderLeft: '4px solid #1976d2',
                      paddingLeft: 2,
                      marginLeft: 0,
                      marginY: 2,
                      fontStyle: 'italic',
                      color: 'textSecondary',
                    }}
                    {...props}
                  />
                ),
                a: ({ node, ...props }) => (
                  <Typography
                    component="a"
                    sx={{
                      color: '#1976d2',
                      textDecoration: 'none',
                      '&:hover': { textDecoration: 'underline' },
                    }}
                    target="_blank"
                    rel="noopener noreferrer"
                    {...props}
                  />
                ),
              }}
            >
              {report.report_content}
            </ReactMarkdown>
          </div>

          {/* 목차 */}
          {report.toc_text && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
                📑 목차
              </Typography>
              <Typography variant="body2" component="pre" sx={{
                backgroundColor: '#f5f5f5',
                p: 2,
                borderRadius: '4px',
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
              }}>
                {report.toc_text}
              </Typography>
            </>
          )}

          {/* 참고 문헌 (references_data.url_to_info 형식) */}
          {report.references_data &&
            typeof report.references_data === 'object' &&
            report.references_data.url_to_info && (
              <>
                <Divider sx={{ my: 3 }} />
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
                  📚 참고 문헌
                </Typography>
                <Box component="ul" sx={{ pl: 2, m: 0 }}>
                  {Object.entries(report.references_data.url_to_info).map(
                    ([url, info], idx) => (
                      <Box key={`${url}-${idx}`} component="li" sx={{ mb: 1.5 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                          {info.title || url}
                        </Typography>
                        {info.snippet && (
                          <Typography
                            variant="body2"
                            sx={{ mt: 0.5, color: 'text.secondary' }}
                          >
                            {info.snippet}
                          </Typography>
                        )}
                        {url && (
                          <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{ display: 'block', mt: 0.5 }}
                          >
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: '#1976d2' }}
                            >
                              {url}
                            </a>
                          </Typography>
                        )}
                      </Box>
                    )
                  )}
                </Box>
              </>
            )}
        </Paper>

        {/* 하단 액션 */}
        <Box sx={{ mt: 4, display: 'flex', gap: 2, justifyContent: 'center' }}>
          <Button variant="contained" onClick={onBack}>
            ← 새로운 리포트 생성
          </Button>
          <Button variant="outlined">📥 다운로드</Button>
        </Box>
      </Container>
    );
  }

  return null;
};

export default ReportViewer;
