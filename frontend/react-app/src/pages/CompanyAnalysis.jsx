/**
 * CompanyAnalysis - 기업 분석 페이지
 *
 * UI: Google Style 검색바 (중앙) + 추천 기업 리스트 (하단 3개 섹션)
 * Logic:
 *   - 검색바 입력 시 POST /api/generate 호출 (STORM 리포트 생성)
 *   - 추천 기업 클릭 시 리포트 생성 트리거
 *   - 추천 리스트 데이터는 GET /api/company/trending
 */
import React, { useState, useEffect } from 'react';
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
    InputLabel,
    Stack,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import BusinessCenterIcon from '@mui/icons-material/BusinessCenter';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import { fetchTrendingCompanies, fetchTopics, generateReport } from '../services/apiClient';

/** 카테고리 섹션 설정 */
const CATEGORY_CONFIG = {
    unicorns: { title: 'Unicorns', subtitle: '주목받는 유니콘 기업', icon: <RocketLaunchIcon />, color: '#7c4dff' },
    public_corps: { title: 'Public Corps', subtitle: '주요 대기업/상장사', icon: <BusinessCenterIcon />, color: '#1565c0' },
    startups: { title: 'Startups', subtitle: '성장하는 스타트업', icon: <AutoAwesomeIcon />, color: '#00897b' },
};

export const CompanyAnalysis = ({ onViewReport }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [trending, setTrending] = useState(null);
    const [topics, setTopics] = useState([]);
    const [selectedTopic, setSelectedTopic] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);

    // ─── Data Load ──────────────────────────────────────────
    useEffect(() => {
        const load = async () => {
            try {
                const [trendingData, topicData] = await Promise.all([
                    fetchTrendingCompanies(),
                    fetchTopics(),
                ]);
                setTrending(trendingData);
                setTopics(topicData || []);
                if (topicData?.length) setSelectedTopic(topicData[0].id);
            } catch (e) {
                console.error('Failed to load trending data:', e);
            }
        };
        load();
    }, []);

    // ─── Handlers ───────────────────────────────────────────
    const handleSearch = async () => {
        const companyName = searchQuery.trim();
        if (!companyName) return;

        setLoading(true);
        setError(null);
        setSuccess(null);

        try {
            const topicLabel = topics.find((t) => t.id === selectedTopic)?.label || selectedTopic;
            const result = await generateReport(companyName, topicLabel);
            setSuccess(`"${companyName}" 분석이 시작되었습니다. (Job ID: ${result.job_id})`);

            // ReportViewer로 전환
            if (onViewReport) {
                setTimeout(() => onViewReport(result.job_id, 'PENDING'), 1500);
            }
        } catch (e) {
            setError(e.response?.data?.detail || '분석 요청에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    };

    const handleCompanyClick = (company) => {
        setSearchQuery(company.name);
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') handleSearch();
    };

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
                        onChange={(e) => setSearchQuery(e.target.value)}
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
                    {/* Topic Selector */}
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

                {/* Feedback Messages */}
                {error && (
                    <Fade in>
                        <Alert severity="error" sx={{ maxWidth: 600, mx: 'auto', mt: 2 }} onClose={() => setError(null)}>
                            {error}
                        </Alert>
                    </Fade>
                )}
                {success && (
                    <Fade in>
                        <Alert severity="success" sx={{ maxWidth: 600, mx: 'auto', mt: 2 }} onClose={() => setSuccess(null)}>
                            {success}
                        </Alert>
                    </Fade>
                )}
            </Box>

            {/* ─── Trending Companies ──────────────────────────── */}
            {trending && (
                <Box sx={{ mt: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                        <TrendingUpIcon sx={{ color: 'primary.main' }} />
                        <Typography variant="h5" sx={{ fontWeight: 600 }}>
                            추천 기업
                        </Typography>
                    </Box>

                    <Grid container spacing={4}>
                        {Object.entries(CATEGORY_CONFIG).map(([key, config]) => {
                            const companies = trending[key] || [];
                            return (
                                <Grid item xs={12} md={4} key={key}>
                                    <Paper
                                        elevation={0}
                                        sx={{
                                            p: 3,
                                            borderRadius: 3,
                                            bgcolor: '#fff',
                                            border: '1px solid',
                                            borderColor: 'grey.200',
                                            height: '100%',
                                        }}
                                    >
                                        {/* Category Header */}
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5 }}>
                                            <Box
                                                sx={{
                                                    width: 40,
                                                    height: 40,
                                                    borderRadius: 2,
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    bgcolor: `${config.color}14`,
                                                    color: config.color,
                                                }}
                                            >
                                                {config.icon}
                                            </Box>
                                            <Box>
                                                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                                    {config.title}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {config.subtitle}
                                                </Typography>
                                            </Box>
                                        </Box>

                                        {/* Company Cards */}
                                        <Stack spacing={1.5}>
                                            {companies.map((company) => (
                                                <Card
                                                    key={company.id}
                                                    elevation={0}
                                                    sx={{
                                                        border: '1px solid',
                                                        borderColor: 'grey.100',
                                                        borderRadius: 2,
                                                        transition: 'all 0.2s',
                                                        '&:hover': {
                                                            borderColor: config.color,
                                                            boxShadow: `0 2px 8px ${config.color}20`,
                                                            transform: 'translateY(-1px)',
                                                        },
                                                    }}
                                                >
                                                    <CardActionArea onClick={() => handleCompanyClick(company)} sx={{ p: 1.5 }}>
                                                        <CardContent sx={{ p: '0 !important' }}>
                                                            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                                                                {company.name}
                                                            </Typography>
                                                            <Chip label={company.industry} size="small" variant="outlined" sx={{ fontSize: 11, height: 22 }} />
                                                        </CardContent>
                                                    </CardActionArea>
                                                </Card>
                                            ))}
                                        </Stack>
                                    </Paper>
                                </Grid>
                            );
                        })}
                    </Grid>
                </Box>
            )}
        </Box>
    );
};
