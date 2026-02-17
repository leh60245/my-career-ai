/**
 * CompanyAnalysis - 기업 분석 페이지 (Real Data)
 *
 * UI: Google Style 검색바 (중앙) + 최근 분석된 기업 카드 (하단)
 * Logic:
 *   - 검색 시 GET /api/company/search?query={name} 호출
 *   - Case A (DB 있음): "리포트 보러가기" 버튼 -> ReportViewer
 *   - Case B (DB 없음): "AI 분석 시작하기" 버튼 -> POST /api/generate
 *   - Trending: GET /api/company/trending -> 실제 DB 최근 기업 9개
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Box,
    Typography,
    TextField,
    InputAdornment,
    IconButton,
    Paper,
    Card,
    CardActionArea,
    CardContent,
    Chip,
    Grid,
    CircularProgress,
    Alert,
    Fade,
    Select,
    MenuItem,
    FormControl,
    Stack,
    Button,
    Divider,
    alpha,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import BusinessIcon from '@mui/icons-material/Business';
import ArticleIcon from '@mui/icons-material/Article';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import {
    fetchTrendingCompanies,
    fetchTopics,
    searchCompanies,
    fetchReportsByCompany,
    generateReport,
} from '../services/apiClient';

export const CompanyAnalysis = ({ onViewReport, onViewCompanyReports }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [trendingCompanies, setTrendingCompanies] = useState([]);
    const [topics, setTopics] = useState([]);
    const [selectedTopic, setSelectedTopic] = useState('');
    const [loading, setLoading] = useState(false);
    const [trendingLoading, setTrendingLoading] = useState(true);
    const [error, setError] = useState(null);

    // Search result state
    const [searchResults, setSearchResults] = useState(null); // null = not searched
    const [companyReports, setCompanyReports] = useState([]); // reports for matched company
    const [selectedCompany, setSelectedCompany] = useState(null);

    // ─── Data Load ──────────────────────────────────────────
    useEffect(() => {
        const load = async () => {
            try {
                setTrendingLoading(true);
                const [trendingData, topicData] = await Promise.all([
                    fetchTrendingCompanies(),
                    fetchTopics(),
                ]);
                setTrendingCompanies(trendingData || []);
                setTopics((topicData || []).filter((t) => t.id !== 'custom'));
                if (topicData?.length) setSelectedTopic(topicData[0].id);
            } catch (e) {
                console.error('Failed to load data:', e);
            } finally {
                setTrendingLoading(false);
            }
        };
        load();
    }, []);

    // ─── Search Handler ─────────────────────────────────────
    const handleSearch = useCallback(async () => {
        const query = searchQuery.trim();
        if (!query) return;

        setLoading(true);
        setError(null);
        setSearchResults(null);
        setCompanyReports([]);
        setSelectedCompany(null);

        try {
            // 1. DB에서 기업 검색
            const companies = await searchCompanies(query);
            setSearchResults(companies);

            // 2. 정확히 매치되는 기업이 있으면 리포트 조회
            if (companies.length > 0) {
                const exact = companies.find(
                    (c) => c.company_name.toLowerCase() === query.toLowerCase()
                ) || companies[0];
                setSelectedCompany(exact);

                try {
                    const reports = await fetchReportsByCompany(exact.company_name);
                    setCompanyReports(reports || []);
                } catch {
                    setCompanyReports([]);
                }
            }
        } catch (e) {
            setError(e.response?.data?.detail || '검색에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [searchQuery]);

    // ─── Start Analysis ─────────────────────────────────────
    const handleStartAnalysis = useCallback(async (companyName) => {
        setLoading(true);
        setError(null);

        try {
            const topicLabel = topics.find((t) => t.id === selectedTopic)?.label || selectedTopic;
            const result = await generateReport(companyName || searchQuery.trim(), topicLabel);

            if (onViewReport) {
                onViewReport(result.job_id, 'PENDING');
            }
        } catch (e) {
            setError(e.response?.data?.detail || '분석 요청에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [topics, selectedTopic, searchQuery, onViewReport]);

    // ─── View Existing Report ───────────────────────────────
    const handleViewExistingReport = useCallback((report) => {
        if (onViewReport) {
            onViewReport(report.job_id, 'COMPLETED');
        }
    }, [onViewReport]);

    // ─── Trending Card Click ────────────────────────────────
    const handleTrendingClick = useCallback((company) => {
        setSearchQuery(company.company_name);
        setSelectedCompany(company);
        setSearchResults([company]);
        fetchReportsByCompany(company.company_name)
            .then((reports) => setCompanyReports(reports || []))
            .catch(() => setCompanyReports([]));
    }, []);

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') handleSearch();
    };

    // Determine search state
    const isNotSearched = searchResults === null;
    const hasDbMatch = searchResults && searchResults.length > 0;
    const hasReports = companyReports.length > 0;

    return (
        <Box sx={{ px: 4, py: 3, maxWidth: 1200, mx: 'auto' }}>
            {/* ─── Hero Section ────────────────────────────────── */}
            <Box sx={{ textAlign: 'center', pt: 6, pb: 4 }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#1a237e', mb: 1 }}>
                    기업 분석
                </Typography>
                <Typography variant="h6" sx={{ color: 'text.secondary', fontWeight: 400, mb: 4 }}>
                    지원하고 싶은 기업을 검색하고, AI 기반 심층 분석 리포트를 받아보세요.
                </Typography>

                {/* Search Bar */}
                <Paper
                    elevation={3}
                    sx={{
                        maxWidth: 700,
                        mx: 'auto',
                        borderRadius: 50,
                        overflow: 'hidden',
                        display: 'flex',
                        alignItems: 'center',
                        px: 1,
                    }}
                >
                    <TextField
                        fullWidth
                        placeholder="기업명을 입력하세요 (e.g., 삼성전자, NAVER)"
                        variant="standard"
                        value={searchQuery}
                        onChange={(e) => {
                            setSearchQuery(e.target.value);
                            if (searchResults !== null) {
                                setSearchResults(null);
                                setCompanyReports([]);
                                setSelectedCompany(null);
                            }
                        }}
                        onKeyDown={handleKeyDown}
                        InputProps={{
                            disableUnderline: true,
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon sx={{ color: 'text.secondary', ml: 1 }} />
                                </InputAdornment>
                            ),
                            sx: { py: 1.5, px: 1, fontSize: '1.1rem' },
                        }}
                    />
                    <FormControl variant="standard" sx={{ minWidth: 120, mr: 1 }}>
                        <Select
                            value={selectedTopic}
                            onChange={(e) => setSelectedTopic(e.target.value)}
                            disableUnderline
                            sx={{ fontSize: '0.85rem' }}
                        >
                            {topics.map((t) => (
                                <MenuItem key={t.id} value={t.id}>{t.label}</MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                    <IconButton
                        onClick={handleSearch}
                        disabled={loading || !searchQuery.trim()}
                        sx={{
                            bgcolor: 'primary.main',
                            color: '#fff',
                            mr: 0.5,
                            '&:hover': { bgcolor: 'primary.dark' },
                            '&.Mui-disabled': { bgcolor: 'grey.300' },
                        }}
                    >
                        {loading ? <CircularProgress size={24} sx={{ color: '#fff' }} /> : <SearchIcon />}
                    </IconButton>
                </Paper>

                {error && (
                    <Fade in>
                        <Alert severity="error" sx={{ maxWidth: 600, mx: 'auto', mt: 2 }} onClose={() => setError(null)}>
                            {error}
                        </Alert>
                    </Fade>
                )}
            </Box>

            {/* ─── Search Results ─────────────────────────────── */}
            {!isNotSearched && !loading && (
                <Fade in>
                    <Paper
                        elevation={0}
                        sx={{
                            maxWidth: 700,
                            mx: 'auto',
                            mb: 4,
                            p: 3,
                            borderRadius: 3,
                            border: '1px solid',
                            borderColor: 'grey.200',
                        }}
                    >
                        {/* Case A: DB에 기업 존재 */}
                        {hasDbMatch && selectedCompany && (
                            <Box>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                                    <Box
                                        sx={{
                                            width: 48,
                                            height: 48,
                                            borderRadius: 2,
                                            bgcolor: alpha('#1565c0', 0.1),
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                        }}
                                    >
                                        <BusinessIcon sx={{ color: '#1565c0', fontSize: 28 }} />
                                    </Box>
                                    <Box sx={{ flex: 1 }}>
                                        <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                            {selectedCompany.company_name}
                                        </Typography>
                                        <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                                            {selectedCompany.sector && (
                                                <Chip label={selectedCompany.sector} size="small" variant="outlined" />
                                            )}
                                            {selectedCompany.stock_code && (
                                                <Chip label={`종목: ${selectedCompany.stock_code}`} size="small" variant="outlined" color="info" />
                                            )}
                                        </Stack>
                                    </Box>
                                </Box>

                                {hasReports ? (
                                    <Box>
                                        <Button
                                            variant="outlined"
                                            color="primary"
                                            fullWidth
                                            startIcon={<ArticleIcon />}
                                            onClick={() => onViewCompanyReports && onViewCompanyReports(selectedCompany.company_name)}
                                            sx={{ mb: 2, py: 1, fontWeight: 600 }}
                                        >
                                            전체 분석 리포트 보기 ({companyReports.length}건)
                                        </Button>
                                        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, color: 'text.secondary' }}>
                                            기존 분석 리포트 ({companyReports.length}건)
                                        </Typography>
                                        <Stack spacing={1} sx={{ mb: 2 }}>
                                            {companyReports.map((report) => (
                                                <Paper
                                                    key={report.id}
                                                    variant="outlined"
                                                    sx={{
                                                        p: 1.5,
                                                        borderRadius: 2,
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'space-between',
                                                        cursor: 'pointer',
                                                        transition: 'all 0.15s',
                                                        '&:hover': {
                                                            bgcolor: alpha('#1565c0', 0.04),
                                                            borderColor: '#1565c0',
                                                        },
                                                    }}
                                                    onClick={() => handleViewExistingReport(report)}
                                                >
                                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                                        <ArticleIcon sx={{ color: '#1565c0', fontSize: 20 }} />
                                                        <Box>
                                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                                {report.topic}
                                                            </Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {report.model_name} | {new Date(report.created_at).toLocaleDateString('ko-KR')}
                                                            </Typography>
                                                        </Box>
                                                    </Box>
                                                    <Chip label="보기" size="small" color="primary" variant="outlined" />
                                                </Paper>
                                            ))}
                                        </Stack>
                                        <Divider sx={{ my: 2 }} />
                                    </Box>
                                ) : (
                                    <Alert severity="info" sx={{ mb: 2 }}>
                                        이 기업에 대한 분석 리포트가 아직 없습니다.
                                    </Alert>
                                )}

                                <Button
                                    variant="contained"
                                    startIcon={loading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <RocketLaunchIcon />}
                                    onClick={() => handleStartAnalysis(selectedCompany.company_name)}
                                    disabled={loading}
                                    fullWidth
                                    sx={{ py: 1.2, fontWeight: 600 }}
                                >
                                    {hasReports ? '새 주제로 분석 시작하기' : 'AI 분석 시작하기'}
                                </Button>

                                {searchResults.length > 1 && (
                                    <Box sx={{ mt: 2 }}>
                                        <Typography variant="caption" color="text.secondary">
                                            다른 검색 결과:
                                        </Typography>
                                        <Stack direction="row" spacing={1} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 0.5 }}>
                                            {searchResults
                                                .filter((c) => c.id !== selectedCompany.id)
                                                .map((c) => (
                                                    <Chip
                                                        key={c.id}
                                                        label={c.company_name}
                                                        size="small"
                                                        variant="outlined"
                                                        onClick={() => handleTrendingClick(c)}
                                                        sx={{ cursor: 'pointer' }}
                                                    />
                                                ))}
                                        </Stack>
                                    </Box>
                                )}
                            </Box>
                        )}

                        {/* Case B: DB에 기업 없음 */}
                        {!hasDbMatch && (
                            <Box sx={{ textAlign: 'center', py: 2 }}>
                                <Typography variant="body1" sx={{ mb: 2, color: 'text.secondary' }}>
                                    <b>"{searchQuery.trim()}"</b> 에 대한 분석 데이터가 없습니다.
                                </Typography>
                                <Button
                                    variant="contained"
                                    size="large"
                                    startIcon={loading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <PlayArrowIcon />}
                                    onClick={() => handleStartAnalysis()}
                                    disabled={loading}
                                    sx={{ py: 1.2, px: 4, fontWeight: 600 }}
                                >
                                    AI 분석 시작하기
                                </Button>
                                <Typography variant="caption" display="block" sx={{ mt: 1, color: 'text.secondary' }}>
                                    STORM 엔진이 웹에서 데이터를 수집하여 심층 분석 리포트를 생성합니다.
                                </Typography>
                            </Box>
                        )}
                    </Paper>
                </Fade>
            )}

            {/* ─── Trending Companies ──────────────────────────── */}
            <Box sx={{ mt: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                    <TrendingUpIcon sx={{ color: 'primary.main' }} />
                    <Typography variant="h5" sx={{ fontWeight: 600 }}>
                        최근 분석된 기업
                    </Typography>
                    {trendingLoading && <CircularProgress size={20} sx={{ ml: 1 }} />}
                </Box>

                {!trendingLoading && trendingCompanies.length === 0 && (
                    <Paper
                        variant="outlined"
                        sx={{ p: 4, textAlign: 'center', borderRadius: 3, borderStyle: 'dashed' }}
                    >
                        <BusinessIcon sx={{ fontSize: 48, color: 'grey.300', mb: 1 }} />
                        <Typography variant="body1" color="text.secondary">
                            아직 분석된 기업이 없습니다.
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            검색바에 기업명을 입력하여 첫 번째 분석을 시작해보세요.
                        </Typography>
                    </Paper>
                )}

                <Grid container spacing={2}>
                    {trendingCompanies.map((company) => (
                        <Grid item xs={12} sm={6} md={4} key={company.id}>
                            <Card
                                elevation={0}
                                sx={{
                                    border: '1px solid',
                                    borderColor: 'grey.200',
                                    borderRadius: 2.5,
                                    transition: 'all 0.2s',
                                    '&:hover': {
                                        borderColor: 'primary.main',
                                        boxShadow: `0 2px 12px ${alpha('#1565c0', 0.12)}`,
                                        transform: 'translateY(-2px)',
                                    },
                                }}
                            >
                                <CardActionArea
                                    onClick={() => handleTrendingClick(company)}
                                    sx={{ p: 2.5 }}
                                >
                                    <CardContent sx={{ p: '0 !important' }}>
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                                            <Box
                                                sx={{
                                                    width: 36,
                                                    height: 36,
                                                    borderRadius: 1.5,
                                                    bgcolor: alpha('#1565c0', 0.08),
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                }}
                                            >
                                                <BusinessIcon sx={{ color: '#1565c0', fontSize: 20 }} />
                                            </Box>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                                {company.company_name}
                                            </Typography>
                                        </Box>
                                        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
                                            {company.sector && (
                                                <Chip
                                                    label={company.sector}
                                                    size="small"
                                                    variant="outlined"
                                                    sx={{ fontSize: 11, height: 22 }}
                                                />
                                            )}
                                            {company.stock_code && (
                                                <Chip
                                                    label={company.stock_code}
                                                    size="small"
                                                    variant="outlined"
                                                    color="info"
                                                    sx={{ fontSize: 11, height: 22 }}
                                                />
                                            )}
                                        </Stack>
                                    </CardContent>
                                </CardActionArea>
                            </Card>
                        </Grid>
                    ))}
                </Grid>
            </Box>
        </Box>
    );
};
