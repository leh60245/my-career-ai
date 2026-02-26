/**
 * AdminDashboard - 관리자 전용 기업 분석 요청 대시보드
 *
 * 기능:
 *   - PENDING 상태의 분석 요청 목록 조회
 *   - 각 요청에 대한 승인 / 반려 처리
 *
 * 접근 제어: App.jsx 라우터 레벨에서 isAdmin 검증 후 렌더링.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Box,
    Typography,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Button,
    CircularProgress,
    Alert,
    Chip,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    Stack,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import RefreshIcon from '@mui/icons-material/Refresh';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import { getAdminPendingRequests, approveAnalysisRequest, rejectAnalysisRequest } from '../services/apiClient';
import { REQUEST_STATUS } from '../constants';

/** 요청 상태에 따른 Chip 색상 매핑 */
const STATUS_CHIP_COLOR = {
    [REQUEST_STATUS.PENDING]: 'warning',
    [REQUEST_STATUS.PROCESSING]: 'info',
    [REQUEST_STATUS.COMPLETED]: 'success',
    [REQUEST_STATUS.REJECTED]: 'error',
    [REQUEST_STATUS.FAILED]: 'error',
};

export const AdminDashboard = () => {
    const [requests, setRequests] = useState([]);
    const [total, setTotal] = useState(0);
    const [loadingList, setLoadingList] = useState(false);
    const [listError, setListError] = useState(null);

    // 승인/반려 로딩 상태: { [jobId]: 'approve' | 'reject' | null }
    const [actionLoading, setActionLoading] = useState({});
    const [actionError, setActionError] = useState(null);
    const [actionSuccess, setActionSuccess] = useState(null);

    // 반려 다이얼로그
    const [rejectDialog, setRejectDialog] = useState({ open: false, jobId: null, reason: '' });

    // ─── 목록 조회 ────────────────────────────────────────────
    const loadRequests = useCallback(async () => {
        setLoadingList(true);
        setListError(null);
        setActionSuccess(null);
        setActionError(null);

        try {
            const result = await getAdminPendingRequests();
            setRequests(result.requests || []);
            setTotal(result.total || 0);
        } catch (e) {
            const status = e.response?.status;
            if (status === 403) {
                setListError('관리자 권한이 없습니다. (403 Forbidden)');
            } else {
                setListError(e.response?.data?.detail || '목록 조회에 실패했습니다.');
            }
        } finally {
            setLoadingList(false);
        }
    }, []);

    useEffect(() => {
        loadRequests();
    }, [loadRequests]);

    // ─── 승인 처리 ────────────────────────────────────────────
    const handleApprove = useCallback(async (jobId) => {
        setActionLoading((prev) => ({ ...prev, [jobId]: 'approve' }));
        setActionError(null);
        setActionSuccess(null);

        try {
            await approveAnalysisRequest(jobId);
            setActionSuccess(`요청 ${jobId.slice(0, 8)}...이 승인되었습니다. 분석이 시작됩니다.`);
            // 목록 갱신
            setRequests((prev) => prev.filter((r) => r.job_id !== jobId));
            setTotal((prev) => Math.max(0, prev - 1));
        } catch (e) {
            const status = e.response?.status;
            if (status === 403) {
                setActionError('관리자 권한이 없습니다.');
            } else if (status === 404) {
                setActionError('요청을 찾을 수 없거나 이미 처리된 요청입니다.');
            } else {
                setActionError(e.response?.data?.detail || '승인 처리에 실패했습니다.');
            }
        } finally {
            setActionLoading((prev) => ({ ...prev, [jobId]: null }));
        }
    }, []);

    // ─── 반려 다이얼로그 열기 ─────────────────────────────────
    const openRejectDialog = useCallback((jobId) => {
        setRejectDialog({ open: true, jobId, reason: '' });
    }, []);

    const closeRejectDialog = useCallback(() => {
        setRejectDialog({ open: false, jobId: null, reason: '' });
    }, []);

    // ─── 반려 처리 ────────────────────────────────────────────
    const handleReject = useCallback(async () => {
        const { jobId, reason } = rejectDialog;
        if (!reason.trim()) return;

        setActionLoading((prev) => ({ ...prev, [jobId]: 'reject' }));
        setActionError(null);
        setActionSuccess(null);
        closeRejectDialog();

        try {
            await rejectAnalysisRequest(jobId, reason.trim());
            setActionSuccess(`요청 ${jobId.slice(0, 8)}...이 반려되었습니다.`);
            setRequests((prev) => prev.filter((r) => r.job_id !== jobId));
            setTotal((prev) => Math.max(0, prev - 1));
        } catch (e) {
            const status = e.response?.status;
            if (status === 403) {
                setActionError('관리자 권한이 없습니다.');
            } else if (status === 404) {
                setActionError('요청을 찾을 수 없거나 이미 처리된 요청입니다.');
            } else {
                setActionError(e.response?.data?.detail || '반려 처리에 실패했습니다.');
            }
        } finally {
            setActionLoading((prev) => ({ ...prev, [jobId]: null }));
        }
    }, [rejectDialog, closeRejectDialog]);

    return (
        <Box sx={{ px: 4, py: 3, maxWidth: 1200, mx: 'auto' }}>
            {/* ─── Header ─────────────────────────────────────── */}
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 3 }}>
                <AdminPanelSettingsIcon sx={{ color: 'primary.main', fontSize: 32 }} />
                <Box>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                        관리자 대시보드
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        PENDING 상태의 기업 분석 요청을 승인하거나 반려합니다.
                    </Typography>
                </Box>
                <Box sx={{ flex: 1 }} />
                <Button
                    variant="outlined"
                    startIcon={loadingList ? <CircularProgress size={16} /> : <RefreshIcon />}
                    onClick={loadRequests}
                    disabled={loadingList}
                >
                    새로고침
                </Button>
            </Stack>

            {/* ─── Feedback ───────────────────────────────────── */}
            {listError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setListError(null)}>
                    {listError}
                </Alert>
            )}
            {actionError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
                    {actionError}
                </Alert>
            )}
            {actionSuccess && (
                <Alert severity="success" sx={{ mb: 2 }} onClose={() => setActionSuccess(null)}>
                    {actionSuccess}
                </Alert>
            )}

            {/* ─── Stats ──────────────────────────────────────── */}
            <Paper elevation={0} sx={{ p: 2, mb: 3, border: '1px solid', borderColor: 'grey.200', borderRadius: 2 }}>
                <Typography variant="subtitle2" color="text.secondary">
                    대기 중인 요청
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: 700, color: 'warning.main' }}>
                    {total}건
                </Typography>
            </Paper>

            {/* ─── Request Table ──────────────────────────────── */}
            {loadingList ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                    <CircularProgress />
                </Box>
            ) : requests.length === 0 ? (
                <Paper
                    variant="outlined"
                    sx={{ p: 5, textAlign: 'center', borderRadius: 2, borderStyle: 'dashed' }}
                >
                    <Typography color="text.secondary">승인 대기 중인 요청이 없습니다.</Typography>
                </Paper>
            ) : (
                <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', borderRadius: 2 }}>
                    <Table>
                        <TableHead>
                            <TableRow sx={{ bgcolor: 'grey.50' }}>
                                <TableCell sx={{ fontWeight: 600 }}>요청 ID</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>기업명</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>분석 주제</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>요청자</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>상태</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>요청일</TableCell>
                                <TableCell sx={{ fontWeight: 600, textAlign: 'center' }}>액션</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {requests.map((req) => {
                                const isActing = !!actionLoading[req.job_id];
                                return (
                                    <TableRow key={req.job_id} hover>
                                        <TableCell>
                                            <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                                                {req.job_id?.slice(0, 8)}...
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                {req.company_name}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="body2">{req.topic}</Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="body2">
                                                {req.user_id ? `User #${req.user_id}` : '-'}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Chip
                                                label={req.status}
                                                size="small"
                                                color={STATUS_CHIP_COLOR[req.status] || 'default'}
                                                variant="outlined"
                                            />
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="body2" color="text.secondary">
                                                {req.requested_at
                                                    ? new Date(req.requested_at).toLocaleDateString('ko-KR')
                                                    : '-'}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Stack direction="row" spacing={1} justifyContent="center">
                                                <Button
                                                    size="small"
                                                    variant="contained"
                                                    color="success"
                                                    startIcon={
                                                        actionLoading[req.job_id] === 'approve' ? (
                                                            <CircularProgress size={14} sx={{ color: '#fff' }} />
                                                        ) : (
                                                            <CheckCircleIcon />
                                                        )
                                                    }
                                                    disabled={isActing}
                                                    onClick={() => handleApprove(req.job_id)}
                                                >
                                                    승인
                                                </Button>
                                                <Button
                                                    size="small"
                                                    variant="outlined"
                                                    color="error"
                                                    startIcon={
                                                        actionLoading[req.job_id] === 'reject' ? (
                                                            <CircularProgress size={14} />
                                                        ) : (
                                                            <CancelIcon />
                                                        )
                                                    }
                                                    disabled={isActing}
                                                    onClick={() => openRejectDialog(req.job_id)}
                                                >
                                                    반려
                                                </Button>
                                            </Stack>
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}

            {/* ─── Reject Dialog ──────────────────────────────── */}
            <Dialog open={rejectDialog.open} onClose={closeRejectDialog} maxWidth="sm" fullWidth>
                <DialogTitle>반려 사유 입력</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        fullWidth
                        multiline
                        rows={3}
                        label="반려 사유"
                        placeholder="반려 사유를 입력하세요 (필수)"
                        value={rejectDialog.reason}
                        onChange={(e) =>
                            setRejectDialog((prev) => ({ ...prev, reason: e.target.value }))
                        }
                        sx={{ mt: 1 }}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={closeRejectDialog}>취소</Button>
                    <Button
                        variant="contained"
                        color="error"
                        disabled={!rejectDialog.reason.trim()}
                        onClick={handleReject}
                    >
                        반려 확정
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
