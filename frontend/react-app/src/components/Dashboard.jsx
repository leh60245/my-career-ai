import React, { useState, useEffect, useMemo } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import {
  fetchCompanies,
  fetchTopics,
  fetchReports,
  generateReport,
} from '../services/apiService';

/**
 * Dashboard 컴포넌트
 *
 * Backend API 응답 스키마:
 *   CompanyResponse:  { id, company_name, corp_code, stock_code, sector, ... }
 *   ReportSummary:    { job_id, company_name, topic, status, created_at, updated_at }
 *   ReportJobResponse: { job_id, status, company_name, topic, error_message, created_at, updated_at }
 */
const Dashboard = ({ onReportStart, onViewReport }) => {
  // ─── State ──────────────────────────────────────────────
  const [companies, setCompanies] = useState([]);
  const [topics, setTopics] = useState([]);
  const [reports, setReports] = useState([]);
  const [reportsTotal, setReportsTotal] = useState(0);
  const [filters, setFilters] = useState({ company: '', topic: '' });
  const [reportsLoading, setReportsLoading] = useState(false);
  const [metaLoading, setMetaLoading] = useState(true);
  const [error, setError] = useState(null);

  // 생성 모달
  const [createOpen, setCreateOpen] = useState(false);
  const [modalCompany, setModalCompany] = useState('');
  const [modalTopic, setModalTopic] = useState('');
  const [modalCustomTopic, setModalCustomTopic] = useState('');
  const [creating, setCreating] = useState(false);

  const isCustomTopic = modalTopic === 'custom';

  // ─── Data Loading ───────────────────────────────────────
  const loadReferenceData = async () => {
    try {
      setMetaLoading(true);
      const [companiesData, topicsData] = await Promise.all([
        fetchCompanies(),
        fetchTopics(),
      ]);
      setCompanies(companiesData || []);
      setTopics(topicsData || []);

      // 초기값: company_name 문자열
      if (companiesData?.length) {
        setModalCompany(companiesData[0].company_name);
      }
      if (topicsData?.length) {
        setModalTopic(topicsData[0].id);
      }
      setError(null);
    } catch (err) {
      console.error('Failed to load reference data:', err);
      setError('기준 데이터를 불러올 수 없습니다. 서버 상태를 확인하세요.');
    } finally {
      setMetaLoading(false);
    }
  };

  const loadReports = async () => {
    try {
      setReportsLoading(true);
      // Backend는 limit, offset만 지원 → 필터는 클라이언트에서 처리
      const data = await fetchReports({ limit: 50, offset: 0 });
      setReports(data?.reports || []);
      setReportsTotal(data?.total || 0);
      setError(null);
    } catch (err) {
      console.error('Failed to load reports:', err);
      setError('리포트 목록을 불러올 수 없습니다.');
    } finally {
      setReportsLoading(false);
    }
  };

  useEffect(() => {
    loadReferenceData();
  }, []);

  useEffect(() => {
    loadReports();
  }, []);

  // ─── Client-side Filtering ──────────────────────────────
  const filteredReports = useMemo(() => {
    return reports.filter((r) => {
      if (filters.company && r.company_name !== filters.company) return false;
      if (filters.topic && r.topic !== filters.topic) return false;
      return true;
    });
  }, [reports, filters]);

  // ─── Create Modal ───────────────────────────────────────
  const openCreateModal = () => {
    setCreateOpen(true);
    setModalCustomTopic('');
    if (topics?.length && !modalTopic) {
      setModalTopic(topics[0].id);
    }
    if (companies?.length && !modalCompany) {
      setModalCompany(companies[0].company_name);
    }
  };

  const closeCreateModal = () => {
    setCreateOpen(false);
    setCreating(false);
  };

  const handleGenerate = async () => {
    if (!modalCompany || !modalTopic) {
      setError('기업과 주제를 모두 선택해주세요.');
      return;
    }

    let finalTopic = modalTopic;
    if (isCustomTopic) {
      if (!modalCustomTopic.trim()) {
        setError('직접 입력한 분석 주제를 입력해주세요.');
        return;
      }
      finalTopic = modalCustomTopic.trim();
    } else {
      const selected = topics.find((t) => t.id === modalTopic);
      finalTopic = selected?.label || finalTopic;
    }

    try {
      setCreating(true);
      const response = await generateReport(modalCompany, finalTopic);

      // Optimistic row (ReportSummary 스키마에 맞춤)
      const optimisticRow = {
        job_id: response?.job_id,
        company_name: modalCompany,
        topic: finalTopic,
        status: response?.status || 'PENDING',
        created_at: response?.created_at || new Date().toISOString(),
        updated_at: null,
      };
      setReports((prev) => [optimisticRow, ...prev]);
      setReportsTotal((prev) => prev + 1);

      if (response?.job_id) {
        onReportStart(response.job_id);
      }

      closeCreateModal();
      setError(null);
    } catch (err) {
      console.error('Failed to generate report:', err);
      setError('리포트 생성 요청에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setCreating(false);
    }
  };

  // ─── Helpers ────────────────────────────────────────────
  const STATUS_CONFIG = {
    COMPLETED: { color: 'success', label: '완료' },
    PROCESSING: { color: 'warning', label: '처리 중' },
    PENDING: { color: 'info', label: '대기 중' },
    FAILED: { color: 'error', label: '실패' },
  };

  const renderStatusChip = (status) => {
    const upper = (status || '').toUpperCase();
    const config = STATUS_CONFIG[upper] || { color: 'default', label: status || 'unknown' };
    return <Chip size="small" color={config.color} label={config.label} />;
  };

  const truncateId = (id) => (id ? id.substring(0, 8) + '…' : '—');

  // ─── Render ─────────────────────────────────────────────
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
              📊 Enterprise STORM Dashboard
            </Typography>
            <Typography variant="body2" color="textSecondary">
              생성된 리포트를 테이블로 관리하고 새 리포트를 생성하세요.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              startIcon={<RefreshIcon />}
              variant="outlined"
              onClick={loadReports}
              disabled={reportsLoading}
            >
              새로고침
            </Button>
            <Button
              startIcon={<AddIcon />}
              variant="contained"
              onClick={openCreateModal}
              disabled={metaLoading}
            >
              새 리포트 생성
            </Button>
          </Stack>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Filters (client-side) */}
        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <FormControl sx={{ minWidth: 200 }} size="small">
            <InputLabel>기업 필터</InputLabel>
            <Select
              label="기업 필터"
              value={filters.company}
              onChange={(e) => setFilters((f) => ({ ...f, company: e.target.value }))}
            >
              <MenuItem value="">전체</MenuItem>
              {companies.map((c) => (
                <MenuItem key={c.id} value={c.company_name}>
                  {c.company_name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl sx={{ minWidth: 220 }} size="small">
            <InputLabel>주제 필터</InputLabel>
            <Select
              label="주제 필터"
              value={filters.topic}
              onChange={(e) => setFilters((f) => ({ ...f, topic: e.target.value }))}
            >
              <MenuItem value="">전체</MenuItem>
              {topics.map((t) => (
                <MenuItem key={t.id} value={t.label}>
                  {t.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        {/* Reports Table */}
        <Paper variant="outlined" sx={{ width: '100%', overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Job ID</TableCell>
                <TableCell>기업명</TableCell>
                <TableCell>분석 주제</TableCell>
                <TableCell>상태</TableCell>
                <TableCell>생성 일시</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {reportsLoading ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, py: 2 }}>
                      <CircularProgress size={20} />
                      <Typography variant="body2">리포트를 불러오는 중...</Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ) : filteredReports.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography variant="body2" sx={{ py: 2 }}>
                      표시할 리포트가 없습니다.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                filteredReports.map((row) => {
                  const jobId = row.job_id || row.id;
                  const statusUpper = (row.status || '').toUpperCase();

                  return (
                    <TableRow key={jobId || row.job_id} hover>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                        {truncateId(jobId)}
                      </TableCell>
                      <TableCell>{row.company_name}</TableCell>
                      <TableCell>{row.topic}</TableCell>
                      <TableCell>{renderStatusChip(row.status)}</TableCell>
                      <TableCell>
                        {row.created_at
                          ? new Date(row.created_at).toLocaleString('ko-KR')
                          : '—'}
                      </TableCell>
                      <TableCell align="right">
                        {statusUpper === 'COMPLETED' ? (
                          <Button
                            size="small"
                            variant="outlined"
                            color="primary"
                            onClick={() => onViewReport(jobId, row.status)}
                            disabled={!jobId}
                          >
                            보기
                          </Button>
                        ) : statusUpper === 'FAILED' ? (
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            disabled
                          >
                            실패
                          </Button>
                        ) : (
                          <Button
                            size="small"
                            variant="outlined"
                            disabled
                          >
                            {statusUpper === 'PROCESSING' ? '처리 중…' : '대기 중…'}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </Paper>

        <Typography variant="caption" sx={{ mt: 1, display: 'block' }}>
          {filters.company || filters.topic
            ? `${filteredReports.length}건 (전체 ${reportsTotal}건 중)`
            : `총 ${reportsTotal}건`}
        </Typography>
      </Paper>

      {/* 생성 모달 */}
      <Dialog open={createOpen} onClose={closeCreateModal} fullWidth maxWidth="sm">
        <DialogTitle>새 리포트 생성</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          <FormControl fullWidth disabled={metaLoading}>
            <InputLabel>기업 선택</InputLabel>
            <Select
              label="기업 선택"
              value={modalCompany}
              onChange={(e) => setModalCompany(e.target.value)}
            >
              {companies.map((c) => (
                <MenuItem key={c.id} value={c.company_name}>
                  {c.company_name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={metaLoading}>
            <InputLabel>분석 주제</InputLabel>
            <Select
              label="분석 주제"
              value={modalTopic}
              onChange={(e) => setModalTopic(e.target.value)}
            >
              {topics.map((t) => (
                <MenuItem key={t.id} value={t.id}>
                  {t.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {isCustomTopic && (
            <TextField
              label="분석 주제 직접 입력"
              value={modalCustomTopic}
              onChange={(e) => setModalCustomTopic(e.target.value)}
              fullWidth
              multiline
              rows={2}
              placeholder="예: 재무 분석, 글로벌 확장 전략"
            />
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={closeCreateModal} disabled={creating}>
            취소
          </Button>
          <Button
            variant="contained"
            onClick={handleGenerate}
            disabled={creating || !modalCompany || !modalTopic}
          >
            {creating ? <CircularProgress size={20} sx={{ color: 'white' }} /> : '생성'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Dashboard;
