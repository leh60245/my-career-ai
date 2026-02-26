import React, { useState, useMemo } from 'react';
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Box,
    Card,
    CardContent,
    Chip,
    Divider,
    Grid,
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
    Paper,
    Stack,
    Tab,
    Tabs,
    Typography,
    alpha,
    useMediaQuery,
    useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import BusinessIcon from '@mui/icons-material/Business';
import GroupsIcon from '@mui/icons-material/Groups';
import AnalyticsIcon from '@mui/icons-material/Analytics';
import QuizIcon from '@mui/icons-material/Quiz';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import PeopleIcon from '@mui/icons-material/People';
import CategoryIcon from '@mui/icons-material/Category';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import StarIcon from '@mui/icons-material/Star';
import EmojiObjectsIcon from '@mui/icons-material/EmojiObjects';
import ShieldIcon from '@mui/icons-material/Shield';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import GppBadIcon from '@mui/icons-material/GppBad';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

/**
 * StructuredReportViewer - JSON 스키마 기반 구조화된 리포트 뷰어
 *
 * CareerAnalysisReport의 4가지 섹션을 탭(Tab) UI로 렌더링합니다.
 * - company_overview: 기업 개요
 * - corporate_culture: 조직문화
 * - swot_analysis: SWOT 분석
 * - interview_preparation: 면접 대비
 *
 * 빈 데이터 대응: null, 빈 배열, 기본값("정보 부족 - 추가 조사 필요")인 경우
 * Placeholder 텍스트를 노출하여 레이아웃 무너짐을 방지합니다.
 */

// ────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────

const EMPTY_PLACEHOLDER = '해당 항목의 데이터가 부족합니다';
const DEFAULT_EMPTY_VALUE = '정보 부족 - 추가 조사 필요';

/** 탭 정의 (순서/라벨/아이콘/색상) */
const SECTION_TABS = [
    { key: 'company_overview', label: '기업 개요', icon: BusinessIcon, color: '#1565c0' },
    { key: 'corporate_culture', label: '조직문화', icon: GroupsIcon, color: '#2e7d32' },
    { key: 'swot_analysis', label: 'SWOT 분석', icon: AnalyticsIcon, color: '#e65100' },
    { key: 'interview_preparation', label: '면접 대비', icon: QuizIcon, color: '#7b1fa2' },
];

// ────────────────────────────────────────────────────────────
// Utility Functions
// ────────────────────────────────────────────────────────────

/**
 * 값이 비어있거나 의미 없는 기본값인지 판별합니다.
 * @param {*} value - 검사할 값
 * @returns {boolean}
 */
const isEmpty = (value) => {
    if (value === null || value === undefined) return true;
    if (typeof value === 'string') {
        const trimmed = value.trim();
        return trimmed === '' || trimmed === DEFAULT_EMPTY_VALUE || trimmed === '-' || trimmed === 'N/A';
    }
    if (Array.isArray(value)) {
        if (value.length === 0) return true;
        // 모든 요소가 비어있는 경우
        return value.every((item) => isEmpty(item));
    }
    return false;
};

/**
 * report_content 문자열을 JSON 파싱하여 구조화된 데이터를 반환합니다.
 * @param {string} reportContent - JSON 문자열
 * @returns {{ data: object|null, isStructured: boolean }}
 */
export const parseReportContent = (reportContent) => {
    if (!reportContent || typeof reportContent !== 'string') {
        return { data: null, isStructured: false };
    }

    try {
        const parsed = JSON.parse(reportContent);
        // CareerAnalysisReport 구조 확인 (4개 섹션 중 최소 1개 존재)
        const hasStructuredKeys = ['company_overview', 'corporate_culture', 'swot_analysis', 'interview_preparation']
            .some((key) => key in parsed);

        if (hasStructuredKeys) {
            return { data: parsed, isStructured: true };
        }
        return { data: null, isStructured: false };
    } catch {
        // JSON이 아닌 경우 (기존 Markdown 형식)
        return { data: null, isStructured: false };
    }
};

// ────────────────────────────────────────────────────────────
// Sub-Components: Shared
// ────────────────────────────────────────────────────────────

/** 빈 데이터 Placeholder */
const EmptyPlaceholder = ({ message = EMPTY_PLACEHOLDER }) => (
    <Box
        sx={{
            py: 2,
            px: 2.5,
            bgcolor: 'grey.50',
            borderRadius: 2,
            border: '1px dashed',
            borderColor: 'grey.300',
        }}
    >
        <Stack direction="row" spacing={1} alignItems="center">
            <InfoOutlinedIcon sx={{ fontSize: 18, color: 'grey.400' }} />
            <Typography variant="body2" sx={{ color: 'text.disabled', fontStyle: 'italic' }}>
                {message}
            </Typography>
        </Stack>
    </Box>
);

/** 불릿 포인트 리스트 렌더러 */
const BulletList = ({ items, icon: IconComponent = FiberManualRecordIcon, iconColor = 'primary.main', iconSize = 8 }) => {
    if (isEmpty(items)) return <EmptyPlaceholder />;

    return (
        <List disablePadding>
            {items.filter((item) => !isEmpty(item)).map((item, idx) => (
                <ListItem
                    key={idx}
                    disableGutters
                    sx={{ py: 0.5, alignItems: 'flex-start' }}
                >
                    <ListItemIcon sx={{ minWidth: 28, mt: 1 }}>
                        <IconComponent sx={{ fontSize: iconSize, color: iconColor }} />
                    </ListItemIcon>
                    <ListItemText
                        primary={item}
                        primaryTypographyProps={{
                            variant: 'body2',
                            sx: { lineHeight: 1.8, wordBreak: 'keep-all' },
                        }}
                    />
                </ListItem>
            ))}
        </List>
    );
};

/** 정보 카드 (key-value 형태) */
const InfoCard = ({ icon: Icon, label, value, color = 'primary.main' }) => (
    <Card
        elevation={0}
        sx={{
            height: '100%',
            border: '1px solid',
            borderColor: 'grey.200',
            borderRadius: 2,
            transition: 'border-color 0.2s',
            '&:hover': { borderColor: color },
        }}
    >
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
                <Box
                    sx={{
                        width: 36,
                        height: 36,
                        borderRadius: 1.5,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        bgcolor: alpha(color, 0.08),
                        flexShrink: 0,
                    }}
                >
                    <Icon sx={{ fontSize: 20, color }} />
                </Box>
                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="caption"
                        sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}
                    >
                        {label}
                    </Typography>
                    <Typography
                        variant="body2"
                        sx={{
                            fontWeight: 500,
                            mt: 0.5,
                            lineHeight: 1.6,
                            wordBreak: 'keep-all',
                            color: isEmpty(value) ? 'text.disabled' : 'text.primary',
                        }}
                    >
                        {isEmpty(value) ? EMPTY_PLACEHOLDER : value}
                    </Typography>
                </Box>
            </Stack>
        </CardContent>
    </Card>
);

/** 섹션 헤더 */
const SectionHeader = ({ title, subtitle, icon: Icon, color }) => (
    <Box sx={{ mb: 3 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
            <Box
                sx={{
                    width: 40,
                    height: 40,
                    borderRadius: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    bgcolor: alpha(color, 0.1),
                }}
            >
                <Icon sx={{ fontSize: 24, color }} />
            </Box>
            <Box>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {title}
                </Typography>
                {subtitle && (
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        {subtitle}
                    </Typography>
                )}
            </Box>
        </Stack>
    </Box>
);

/** 서브 섹션 (라벨 + 콘텐츠) */
const SubSection = ({ label, children, sx = {} }) => (
    <Box sx={{ mb: 3, ...sx }}>
        <Typography
            variant="subtitle2"
            sx={{
                fontWeight: 700,
                mb: 1.5,
                color: 'text.primary',
                fontSize: '0.9rem',
            }}
        >
            {label}
        </Typography>
        {children}
    </Box>
);

// ────────────────────────────────────────────────────────────
// Section Renderers
// ────────────────────────────────────────────────────────────

/** 1. 기업 개요 섹션 */
const CompanyOverviewSection = ({ data }) => {
    if (!data) return <EmptyPlaceholder />;

    const { introduction, industry, employee_count, location, financials } = data;

    return (
        <Box>
            <SectionHeader
                title="기업 개요"
                subtitle="산업 애널리스트 데이터 기반 분석"
                icon={BusinessIcon}
                color="#1565c0"
            />

            {/* 기업 소개 */}
            <SubSection label="기업 소개">
                {isEmpty(introduction) ? (
                    <EmptyPlaceholder />
                ) : (
                    <Paper
                        elevation={0}
                        sx={{
                            p: 2.5,
                            bgcolor: alpha('#1565c0', 0.03),
                            borderRadius: 2,
                            borderLeft: '4px solid',
                            borderLeftColor: '#1565c0',
                        }}
                    >
                        <Typography variant="body2" sx={{ lineHeight: 1.9, wordBreak: 'keep-all' }}>
                            {introduction}
                        </Typography>
                    </Paper>
                )}
            </SubSection>

            {/* 기본 정보 카드 그리드 */}
            <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={6} md={3}>
                    <InfoCard icon={CategoryIcon} label="업종" value={industry} color="#1565c0" />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                    <InfoCard icon={PeopleIcon} label="직원 수" value={employee_count} color="#0277bd" />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                    <InfoCard icon={LocationOnIcon} label="본사 위치" value={location} color="#00838f" />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                    <InfoCard
                        icon={AccountBalanceIcon}
                        label="매출액"
                        value={financials?.revenue}
                        color="#2e7d32"
                    />
                </Grid>
            </Grid>

            {/* 영업이익 */}
            {financials && (
                <SubSection label="영업이익">
                    {isEmpty(financials.operating_profit) ? (
                        <EmptyPlaceholder />
                    ) : (
                        <Paper
                            elevation={0}
                            sx={{
                                p: 2,
                                bgcolor: 'grey.50',
                                borderRadius: 2,
                                display: 'inline-block',
                            }}
                        >
                            <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                {financials.operating_profit}
                            </Typography>
                        </Paper>
                    )}
                </SubSection>
            )}
        </Box>
    );
};

/** 2. 조직문화 섹션 */
const CorporateCultureSection = ({ data }) => {
    if (!data) return <EmptyPlaceholder />;

    const { core_values, ideal_candidate, work_environment } = data;

    return (
        <Box>
            <SectionHeader
                title="조직문화"
                subtitle="수석 취업 지원관 데이터 기반 분석"
                icon={GroupsIcon}
                color="#2e7d32"
            />

            <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                    <SubSection label="핵심가치">
                        <BulletList
                            items={core_values}
                            icon={StarIcon}
                            iconColor="#ffa000"
                            iconSize={16}
                        />
                    </SubSection>
                </Grid>
                <Grid item xs={12} md={4}>
                    <SubSection label="인재상">
                        <BulletList
                            items={ideal_candidate}
                            icon={EmojiObjectsIcon}
                            iconColor="#2e7d32"
                            iconSize={16}
                        />
                    </SubSection>
                </Grid>
                <Grid item xs={12} md={4}>
                    <SubSection label="조직문화 및 복리후생">
                        <BulletList
                            items={work_environment}
                            icon={FiberManualRecordIcon}
                            iconColor="#0277bd"
                            iconSize={8}
                        />
                    </SubSection>
                </Grid>
            </Grid>
        </Box>
    );
};

/** 3. SWOT 분석 섹션 */
const SwotAnalysisSection = ({ data }) => {
    if (!data) return <EmptyPlaceholder />;

    const { strength, weakness, opportunity, threat, so_strategy, wt_strategy } = data;

    const swotQuadrants = [
        { key: 'S', label: '강점 (Strengths)', items: strength, icon: ShieldIcon, color: '#2e7d32', bgColor: '#e8f5e9' },
        { key: 'W', label: '약점 (Weaknesses)', items: weakness, icon: WarningAmberIcon, color: '#e65100', bgColor: '#fff3e0' },
        { key: 'O', label: '기회 (Opportunities)', items: opportunity, icon: LightbulbIcon, color: '#1565c0', bgColor: '#e3f2fd' },
        { key: 'T', label: '위협 (Threats)', items: threat, icon: GppBadIcon, color: '#c62828', bgColor: '#ffebee' },
    ];

    return (
        <Box>
            <SectionHeader
                title="SWOT 분석"
                subtitle="산업 애널리스트 데이터 기반 전략 분석"
                icon={AnalyticsIcon}
                color="#e65100"
            />

            {/* SWOT 2x2 Grid */}
            <Grid container spacing={2} sx={{ mb: 4 }}>
                {swotQuadrants.map(({ key, label, items, icon: QIcon, color, bgColor }) => (
                    <Grid item xs={12} sm={6} key={key}>
                        <Paper
                            elevation={0}
                            sx={{
                                p: 2.5,
                                borderRadius: 2,
                                border: '1px solid',
                                borderColor: alpha(color, 0.2),
                                bgcolor: alpha(bgColor, 0.5),
                                height: '100%',
                            }}
                        >
                            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                                <Chip
                                    label={key}
                                    size="small"
                                    sx={{
                                        bgcolor: color,
                                        color: '#fff',
                                        fontWeight: 700,
                                        fontSize: '0.8rem',
                                        minWidth: 28,
                                    }}
                                />
                                <Typography variant="subtitle2" sx={{ fontWeight: 700, color }}>
                                    {label}
                                </Typography>
                            </Stack>
                            <BulletList
                                items={items}
                                icon={FiberManualRecordIcon}
                                iconColor={color}
                                iconSize={7}
                            />
                        </Paper>
                    </Grid>
                ))}
            </Grid>

            {/* 전략 섹션 */}
            <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                    <SubSection label="SO 전략 (강점 x 기회)">
                        {isEmpty(so_strategy) ? (
                            <EmptyPlaceholder />
                        ) : (
                            <Paper
                                elevation={0}
                                sx={{
                                    p: 2.5,
                                    bgcolor: alpha('#2e7d32', 0.04),
                                    borderRadius: 2,
                                    borderLeft: '4px solid #2e7d32',
                                }}
                            >
                                <Typography variant="body2" sx={{ lineHeight: 1.9, wordBreak: 'keep-all' }}>
                                    {so_strategy}
                                </Typography>
                            </Paper>
                        )}
                    </SubSection>
                </Grid>
                <Grid item xs={12} md={6}>
                    <SubSection label="WT 전략 (약점 x 위협)">
                        {isEmpty(wt_strategy) ? (
                            <EmptyPlaceholder />
                        ) : (
                            <Paper
                                elevation={0}
                                sx={{
                                    p: 2.5,
                                    bgcolor: alpha('#c62828', 0.04),
                                    borderRadius: 2,
                                    borderLeft: '4px solid #c62828',
                                }}
                            >
                                <Typography variant="body2" sx={{ lineHeight: 1.9, wordBreak: 'keep-all' }}>
                                    {wt_strategy}
                                </Typography>
                            </Paper>
                        )}
                    </SubSection>
                </Grid>
            </Grid>
        </Box>
    );
};

/** 4. 면접 대비 섹션 */
const InterviewPreparationSection = ({ data }) => {
    if (!data) return <EmptyPlaceholder />;

    const { recent_issues, pressure_questions, expected_answers } = data;

    return (
        <Box>
            <SectionHeader
                title="면접 대비"
                subtitle="실무 면접관 데이터 기반 분석"
                icon={QuizIcon}
                color="#7b1fa2"
            />

            {/* 최근 이슈 */}
            <SubSection label="최근 이슈 및 리스크">
                <BulletList
                    items={recent_issues}
                    icon={ReportProblemIcon}
                    iconColor="#e65100"
                    iconSize={16}
                />
            </SubSection>

            {/* 압박 면접 Q&A */}
            <SubSection label="압박 면접 질문 & 전략적 답변">
                {isEmpty(pressure_questions) && isEmpty(expected_answers) ? (
                    <EmptyPlaceholder />
                ) : (
                    <Stack spacing={2}>
                        {(pressure_questions || []).map((question, idx) => {
                            const answer = expected_answers?.[idx];
                            return (
                                <Accordion
                                    key={idx}
                                    elevation={0}
                                    sx={{
                                        border: '1px solid',
                                        borderColor: 'grey.200',
                                        borderRadius: '8px !important',
                                        '&:before': { display: 'none' },
                                        overflow: 'hidden',
                                    }}
                                >
                                    <AccordionSummary
                                        expandIcon={<ExpandMoreIcon />}
                                        sx={{
                                            bgcolor: alpha('#7b1fa2', 0.04),
                                            '& .MuiAccordionSummary-content': {
                                                alignItems: 'center',
                                                gap: 1.5,
                                            },
                                        }}
                                    >
                                        <Chip
                                            label={`Q${idx + 1}`}
                                            size="small"
                                            sx={{
                                                bgcolor: '#7b1fa2',
                                                color: '#fff',
                                                fontWeight: 700,
                                                fontSize: '0.75rem',
                                                minWidth: 32,
                                            }}
                                        />
                                        <Typography
                                            variant="body2"
                                            sx={{ fontWeight: 600, lineHeight: 1.6, wordBreak: 'keep-all' }}
                                        >
                                            {isEmpty(question) ? EMPTY_PLACEHOLDER : question}
                                        </Typography>
                                    </AccordionSummary>
                                    <AccordionDetails sx={{ pt: 2, pb: 2.5 }}>
                                        {isEmpty(answer) ? (
                                            <EmptyPlaceholder message="전략적 답변 데이터가 부족합니다" />
                                        ) : (
                                            <Stack direction="row" spacing={1.5} alignItems="flex-start">
                                                <CheckCircleOutlineIcon
                                                    sx={{ fontSize: 18, color: '#2e7d32', mt: 0.3, flexShrink: 0 }}
                                                />
                                                <Typography
                                                    variant="body2"
                                                    sx={{ lineHeight: 1.9, wordBreak: 'keep-all', color: 'text.secondary' }}
                                                >
                                                    {answer}
                                                </Typography>
                                            </Stack>
                                        )}
                                    </AccordionDetails>
                                </Accordion>
                            );
                        })}
                    </Stack>
                )}
            </SubSection>
        </Box>
    );
};

// ────────────────────────────────────────────────────────────
// Section Router
// ────────────────────────────────────────────────────────────

const SECTION_RENDERERS = {
    company_overview: CompanyOverviewSection,
    corporate_culture: CorporateCultureSection,
    swot_analysis: SwotAnalysisSection,
    interview_preparation: InterviewPreparationSection,
};

// ────────────────────────────────────────────────────────────
// Main Component
// ────────────────────────────────────────────────────────────

/**
 * StructuredReportViewer - 구조화 JSON 리포트 탭 뷰어
 *
 * @param {object} reportData - 파싱된 CareerAnalysisReport JSON
 * @param {string} companyName - 기업명 (헤더 표시용)
 */
export const StructuredReportViewer = ({ reportData, companyName }) => {
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const [activeTab, setActiveTab] = useState(0);

    const activeSection = SECTION_TABS[activeTab];
    const SectionRenderer = SECTION_RENDERERS[activeSection.key];
    const sectionData = reportData?.[activeSection.key] || null;

    return (
        <Box>
            {/* Tab Navigation */}
            <Paper
                elevation={0}
                sx={{
                    mb: 3,
                    border: '1px solid',
                    borderColor: 'grey.200',
                    borderRadius: 2,
                    overflow: 'hidden',
                }}
            >
                <Tabs
                    value={activeTab}
                    onChange={(_, v) => setActiveTab(v)}
                    variant={isMobile ? 'scrollable' : 'fullWidth'}
                    scrollButtons={isMobile ? 'auto' : false}
                    sx={{
                        '& .MuiTab-root': {
                            minHeight: 56,
                            fontWeight: 600,
                            fontSize: '0.875rem',
                        },
                    }}
                >
                    {SECTION_TABS.map((tab, idx) => {
                        const Icon = tab.icon;
                        return (
                            <Tab
                                key={tab.key}
                                icon={<Icon sx={{ fontSize: 20 }} />}
                                iconPosition="start"
                                label={tab.label}
                                sx={{
                                    gap: 1,
                                    '&.Mui-selected': { color: tab.color },
                                }}
                            />
                        );
                    })}
                </Tabs>
            </Paper>

            {/* Tab Content */}
            <Paper
                elevation={0}
                sx={{
                    p: { xs: 2, sm: 3, md: 4 },
                    border: '1px solid',
                    borderColor: 'grey.200',
                    borderRadius: 2,
                    minHeight: 300,
                }}
            >
                <SectionRenderer data={sectionData} />
            </Paper>
        </Box>
    );
};

// ────────────────────────────────────────────────────────────
// Accordion Mode Renderer (for company-wide view)
// ────────────────────────────────────────────────────────────

/**
 * StructuredAccordionViewer - 아코디언 모드에서 개별 리포트의 JSON 데이터 렌더링
 *
 * @param {object} reportData - 파싱된 CareerAnalysisReport JSON
 */
export const StructuredAccordionViewer = ({ reportData }) => {
    if (!reportData) return <EmptyPlaceholder />;

    return (
        <Stack spacing={3}>
            {SECTION_TABS.map((tab) => {
                const SectionRenderer = SECTION_RENDERERS[tab.key];
                const sectionData = reportData[tab.key] || null;

                return (
                    <Box key={tab.key}>
                        <SectionRenderer data={sectionData} />
                        <Divider sx={{ mt: 3 }} />
                    </Box>
                );
            })}
        </Stack>
    );
};
