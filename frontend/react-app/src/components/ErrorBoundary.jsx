import React from 'react';
import { Box, Typography, Button, Paper, alpha } from '@mui/material';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import RefreshIcon from '@mui/icons-material/Refresh';

/**
 * ErrorBoundary - React Error Boundary
 *
 * 하위 컴포넌트에서 발생하는 렌더링 에러를 포착하여
 * 화이트 스크린(White Screen of Death)을 원천 차단합니다.
 *
 * Fallback UI:
 *   "현재 해당 기업의 데이터를 분석하는 데 어려움을 겪고 있습니다.
 *    잠시 후 다시 시도해 주세요."
 */
export class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('[ErrorBoundary] Caught error:', error, errorInfo);
    }

    handleRetry = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            return (
                <Box
                    sx={{
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                        minHeight: 400,
                        px: 3,
                        py: 6,
                    }}
                >
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 3, sm: 5 },
                            maxWidth: 520,
                            width: '100%',
                            textAlign: 'center',
                            border: '1px solid',
                            borderColor: alpha('#e53935', 0.2),
                            borderRadius: 3,
                            bgcolor: alpha('#e53935', 0.03),
                        }}
                    >
                        <ErrorOutlineIcon
                            sx={{
                                fontSize: 56,
                                color: 'error.main',
                                mb: 2,
                                opacity: 0.8,
                            }}
                        />
                        <Typography
                            variant="h6"
                            sx={{ fontWeight: 700, mb: 1.5, color: 'text.primary' }}
                        >
                            분석 데이터 로드 오류
                        </Typography>
                        <Typography
                            variant="body1"
                            sx={{ color: 'text.secondary', lineHeight: 1.8, mb: 3 }}
                        >
                            현재 해당 기업의 데이터를 분석하는 데 어려움을 겪고 있습니다.
                            <br />
                            잠시 후 다시 시도해 주세요.
                        </Typography>
                        <Button
                            variant="contained"
                            startIcon={<RefreshIcon />}
                            onClick={this.handleRetry}
                            sx={{ borderRadius: 2, px: 3, py: 1 }}
                        >
                            다시 시도
                        </Button>
                    </Paper>
                </Box>
            );
        }

        return this.props.children;
    }
}
