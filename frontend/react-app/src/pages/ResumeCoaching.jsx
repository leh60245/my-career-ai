/**
 * ResumeCoaching - 자소서 코칭 통합 페이지 (2-Column Split View)
 *
 * Left Panel (Input Area):
 *   Step 1 - Settings: 기업명/직무명/지원형태(신입/경력) 입력
 *   Step 2 - Question: 자소서 문항 제목, 글자수 제한 입력
 *   Step 3 - Draft: Textarea (초안 작성) + 'My Data 불러오기' 버튼
 *
 * Right Panel (Assistant Area):
 *   Tab 1 - 가이드 (Guide): 초안 없어도 활성화
 *   Tab 2 - 첨삭 (Correction): 초안이 있어야 활성화
 *
 * Interaction:
 *   1. 가이드 요청: 기업/직무/문항 입력 후 버튼 클릭 -> 우측에 가이드 표시
 *   2. 초안 작성: 좌측 에디터에 글 작성
 *   3. 첨삭 요청: 초안 작성 후 버튼 클릭 -> 우측에 첨삭 결과 표시
 */
import React, { useState, useCallback, useMemo } from 'react';
import {
    Box,
    Typography,
    TextField,
    Button,
    Paper,
    Tab,
    Tabs,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Chip,
    CircularProgress,
    Alert,
    Divider,
    Stack,
    LinearProgress,
    Card,
    CardContent,
    IconButton,
    Tooltip,
    Fade,
    Stepper,
    Step,
    StepLabel,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import SaveIcon from '@mui/icons-material/Save';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import EditNoteIcon from '@mui/icons-material/EditNote';
import GradingIcon from '@mui/icons-material/Grading';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { useAuth } from '../contexts/AuthContext';
import {
    createResumeQuestion,
    createDraft,
    requestGuide,
    requestCorrection,
} from '../services/apiClient';

// ─── Constants ────────────────────────────────────────────
const APPLICANT_TYPES = [
    { value: 'NEW', label: '신입' },
    { value: 'EXPERIENCED', label: '경력' },
];
const ITEM_TYPES = [
    { value: 'MOTIVATION', label: '지원동기' },
    { value: 'COMPETENCY', label: '직무역량' },
    { value: 'CHALLENGE', label: '도전/성취' },
    { value: 'COLLABORATION', label: '협업/소통' },
    { value: 'VALUES', label: '가치관' },
    { value: 'SOCIAL_ISSUE', label: '사회이슈' },
];
const STEPS = ['기본 설정', '문항 입력', '초안 작성'];

export const ResumeCoaching = () => {
    const { user } = useAuth();

    // ─── Step 1: Settings ─────────────────────────────────
    const [companyName, setCompanyName] = useState('');
    const [jobTitle, setJobTitle] = useState('');
    const [applicantType, setApplicantType] = useState('NEW');

    // ─── Step 2: Question ─────────────────────────────────
    const [questionTitle, setQuestionTitle] = useState('');
    const [itemType, setItemType] = useState('MOTIVATION');
    const [maxLength, setMaxLength] = useState('');

    // ─── Step 3: Draft ────────────────────────────────────
    const [draftContent, setDraftContent] = useState('');

    // ─── Server State ─────────────────────────────────────
    const [savedQuestion, setSavedQuestion] = useState(null);
    const [savedItem, setSavedItem] = useState(null);
    const [savedDraft, setSavedDraft] = useState(null);

    // ─── Right Panel ──────────────────────────────────────
    const [activeTab, setActiveTab] = useState(0); // 0: Guide, 1: Correction
    const [guideResult, setGuideResult] = useState(null);
    const [correctionResult, setCorrectionResult] = useState(null);

    // ─── UI State ─────────────────────────────────────────
    const [loading, setLoading] = useState({ save: false, guide: false, correction: false });
    const [error, setError] = useState(null);
    const [activeStep, setActiveStep] = useState(0);

    // ─── Derived State ────────────────────────────────────
    const hasDraft = draftContent.trim().length > 0;
    const hasQuestion = questionTitle.trim().length > 0;
    const hasSettings = companyName.trim().length > 0;
    const charCount = draftContent.length;
    const maxLengthNum = maxLength ? parseInt(maxLength, 10) : null;
    const isOverLimit = maxLengthNum && charCount > maxLengthNum;

    /** Step 자동 진행 */
    const computedStep = useMemo(() => {
        if (hasDraft) return 2;
        if (hasQuestion) return 1;
        return 0;
    }, [hasDraft, hasQuestion]);

    // ─── Handlers ─────────────────────────────────────────

    /** 세트 + 문항 저장 후 가이드/첨삭 요청용 ID 확보 */
    const handleSaveAndPrepare = useCallback(async () => {
        if (!hasSettings || !hasQuestion) {
            setError('기업명과 문항을 모두 입력해주세요.');
            return null;
        }
        setLoading((p) => ({ ...p, save: true }));
        setError(null);

        try {
            const body = {
                title: `${companyName} - ${jobTitle || '직무미정'}`,
                job_text: jobTitle || null,
                applicant_type: applicantType,
                items: [
                    {
                        type: itemType,
                        content: questionTitle,
                        max_length: maxLengthNum,
                        order_index: 0,
                    },
                ],
            };
            const result = await createResumeQuestion(user.id, body);
            setSavedQuestion(result);
            const item = result.items?.[0] || null;
            setSavedItem(item);
            return { question: result, item };
        } catch (e) {
            setError(e.response?.data?.detail || '자소서 세트 저장에 실패했습니다.');
            return null;
        } finally {
            setLoading((p) => ({ ...p, save: false }));
        }
    }, [hasSettings, hasQuestion, companyName, jobTitle, applicantType, itemType, questionTitle, maxLengthNum, user.id]);

    /** 초안 저장 */
    const handleSaveDraft = useCallback(async (itemId) => {
        if (!hasDraft || !itemId) return null;
        try {
            const result = await createDraft(itemId, draftContent);
            setSavedDraft(result);
            return result;
        } catch (e) {
            setError(e.response?.data?.detail || '초안 저장에 실패했습니다.');
            return null;
        }
    }, [hasDraft, draftContent]);

    /** 가이드 요청 */
    const handleRequestGuide = useCallback(async () => {
        setLoading((p) => ({ ...p, guide: true }));
        setError(null);
        setGuideResult(null);

        try {
            let itemId = savedItem?.id;

            // 아직 저장하지 않았다면 먼저 저장
            if (!itemId) {
                const saved = await handleSaveAndPrepare();
                if (!saved) return;
                itemId = saved.item?.id;
            }

            const guide = await requestGuide(itemId, user.id);
            setGuideResult(guide);
            setActiveTab(0); // 가이드 탭으로 전환
        } catch (e) {
            setError(e.response?.data?.detail || 'AI 가이드 생성에 실패했습니다.');
        } finally {
            setLoading((p) => ({ ...p, guide: false }));
        }
    }, [savedItem, handleSaveAndPrepare, user.id]);

    /** 첨삭 요청 */
    const handleRequestCorrection = useCallback(async () => {
        if (!hasDraft) {
            setError('초안을 먼저 작성해주세요.');
            return;
        }
        setLoading((p) => ({ ...p, correction: true }));
        setError(null);
        setCorrectionResult(null);

        try {
            let itemId = savedItem?.id;

            // 아직 저장하지 않았다면 먼저 저장
            if (!itemId) {
                const saved = await handleSaveAndPrepare();
                if (!saved) return;
                itemId = saved.item?.id;
            }

            // 초안 저장
            const draft = await handleSaveDraft(itemId);
            if (!draft) return;

            const correction = await requestCorrection(draft.id, user.id);
            setCorrectionResult(correction);
            setActiveTab(1); // 첨삭 탭으로 전환
        } catch (e) {
            setError(e.response?.data?.detail || 'AI 첨삭에 실패했습니다.');
        } finally {
            setLoading((p) => ({ ...p, correction: false }));
        }
    }, [hasDraft, savedItem, handleSaveAndPrepare, handleSaveDraft, user.id]);

    /** My Data 불러오기 (MVP Placeholder) */
    const handleLoadMyData = useCallback(() => {
        const placeholder = '[My Data]\n- 학력: OO대학교 OO학과 졸업\n- 경력: OO 인턴 경험 (6개월)\n- 자격증: 정보처리기사\n- 활동: OO 동아리 회장\n\n위 내용을 참고하여 초안을 작성해보세요.';
        setDraftContent((prev) => prev ? prev + '\n\n' + placeholder : placeholder);
    }, []);

    // ─── Render ───────────────────────────────────────────
    return (
        <Box sx={{ display: 'flex', height: 'calc(100vh - 0px)', overflow: 'hidden' }}>
            {/* ================================================================ */}
            {/* LEFT PANEL - Input Area                                          */}
            {/* ================================================================ */}
            <Box
                sx={{
                    width: '50%',
                    borderRight: '1px solid',
                    borderColor: 'grey.200',
                    display: 'flex',
                    flexDirection: 'column',
                    bgcolor: '#fff',
                }}
            >
                {/* Header */}
                <Box sx={{ px: 3, py: 2, borderBottom: '1px solid', borderColor: 'grey.100' }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <EditNoteIcon color="primary" /> 자소서 코칭
                    </Typography>
                    <Stepper activeStep={computedStep} alternativeLabel sx={{ mt: 2 }}>
                        {STEPS.map((label) => (
                            <Step key={label}>
                                <StepLabel>{label}</StepLabel>
                            </Step>
                        ))}
                    </Stepper>
                </Box>

                {/* Scrollable Content */}
                <Box sx={{ flex: 1, overflow: 'auto', px: 3, py: 2 }}>
                    {/* Error Alert */}
                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                            {error}
                        </Alert>
                    )}

                    {/* ─── Step 1: Settings ────────────────────────── */}
                    <Paper variant="outlined" sx={{ p: 2.5, mb: 2, borderRadius: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}>
                            Step 1. 기본 설정
                        </Typography>
                        <Stack spacing={2}>
                            <TextField
                                label="기업명"
                                placeholder="e.g., 삼성전자"
                                value={companyName}
                                onChange={(e) => setCompanyName(e.target.value)}
                                size="small"
                                fullWidth
                                required
                            />
                            <Stack direction="row" spacing={2}>
                                <TextField
                                    label="직무명"
                                    placeholder="e.g., 백엔드 개발"
                                    value={jobTitle}
                                    onChange={(e) => setJobTitle(e.target.value)}
                                    size="small"
                                    fullWidth
                                />
                                <FormControl size="small" sx={{ minWidth: 120 }}>
                                    <InputLabel>지원형태</InputLabel>
                                    <Select
                                        value={applicantType}
                                        label="지원형태"
                                        onChange={(e) => setApplicantType(e.target.value)}
                                    >
                                        {APPLICANT_TYPES.map((t) => (
                                            <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                            </Stack>
                        </Stack>
                    </Paper>

                    {/* ─── Step 2: Question ────────────────────────── */}
                    <Paper variant="outlined" sx={{ p: 2.5, mb: 2, borderRadius: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}>
                            Step 2. 문항 입력
                        </Typography>
                        <Stack spacing={2}>
                            <TextField
                                label="문항 내용"
                                placeholder="e.g., 지원동기를 기술하시오."
                                value={questionTitle}
                                onChange={(e) => setQuestionTitle(e.target.value)}
                                size="small"
                                fullWidth
                                multiline
                                minRows={2}
                                required
                            />
                            <Stack direction="row" spacing={2}>
                                <FormControl size="small" fullWidth>
                                    <InputLabel>문항 유형</InputLabel>
                                    <Select
                                        value={itemType}
                                        label="문항 유형"
                                        onChange={(e) => setItemType(e.target.value)}
                                    >
                                        {ITEM_TYPES.map((t) => (
                                            <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                                <TextField
                                    label="글자수 제한"
                                    placeholder="e.g., 500"
                                    value={maxLength}
                                    onChange={(e) => setMaxLength(e.target.value.replace(/\D/g, ''))}
                                    size="small"
                                    sx={{ maxWidth: 140 }}
                                    type="number"
                                />
                            </Stack>
                        </Stack>
                    </Paper>

                    {/* ─── Step 3: Draft Editor ────────────────────── */}
                    <Paper variant="outlined" sx={{ p: 2.5, mb: 2, borderRadius: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'primary.main' }}>
                                Step 3. 초안 작성
                            </Typography>
                            <Tooltip title="My Data 불러오기 (참고용)">
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<FolderOpenIcon />}
                                    onClick={handleLoadMyData}
                                    sx={{ textTransform: 'none', fontSize: 12 }}
                                >
                                    My Data
                                </Button>
                            </Tooltip>
                        </Box>
                        <TextField
                            multiline
                            minRows={8}
                            maxRows={20}
                            fullWidth
                            placeholder="초안을 작성해주세요. 가이드를 먼저 받아본 후 작성하는 것을 추천합니다."
                            value={draftContent}
                            onChange={(e) => setDraftContent(e.target.value)}
                            sx={{
                                '& .MuiOutlinedInput-root': {
                                    fontSize: '0.95rem',
                                    lineHeight: 1.8,
                                },
                            }}
                        />
                        {/* Character Count */}
                        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1, gap: 1, alignItems: 'center' }}>
                            {maxLengthNum && (
                                <LinearProgress
                                    variant="determinate"
                                    value={Math.min((charCount / maxLengthNum) * 100, 100)}
                                    color={isOverLimit ? 'error' : 'primary'}
                                    sx={{ flex: 1, maxWidth: 200, height: 6, borderRadius: 3 }}
                                />
                            )}
                            <Typography
                                variant="caption"
                                sx={{ color: isOverLimit ? 'error.main' : 'text.secondary', fontWeight: isOverLimit ? 700 : 400 }}
                            >
                                {charCount}{maxLengthNum ? ` / ${maxLengthNum}` : ''} 자
                            </Typography>
                        </Box>
                    </Paper>
                </Box>

                {/* Bottom Action Buttons */}
                <Box sx={{ px: 3, py: 2, borderTop: '1px solid', borderColor: 'grey.100', bgcolor: '#fafafa' }}>
                    <Stack direction="row" spacing={2}>
                        <Button
                            variant="contained"
                            startIcon={loading.guide ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <LightbulbIcon />}
                            onClick={handleRequestGuide}
                            disabled={!hasQuestion || !hasSettings || loading.guide || loading.correction}
                            sx={{ flex: 1, py: 1.2, textTransform: 'none', fontWeight: 600 }}
                        >
                            가이드 받기
                        </Button>
                        <Button
                            variant="contained"
                            color="secondary"
                            startIcon={loading.correction ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <AutoFixHighIcon />}
                            onClick={handleRequestCorrection}
                            disabled={!hasDraft || !hasQuestion || !hasSettings || loading.guide || loading.correction}
                            sx={{ flex: 1, py: 1.2, textTransform: 'none', fontWeight: 600 }}
                        >
                            첨삭 받기
                        </Button>
                    </Stack>
                    {/* 초안이 없으면 첨삭 비활성화 안내 */}
                    {!hasDraft && hasQuestion && (
                        <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'text.secondary', textAlign: 'center' }}>
                            첨삭을 받으려면 초안을 먼저 작성해주세요.
                        </Typography>
                    )}
                </Box>
            </Box>

            {/* ================================================================ */}
            {/* RIGHT PANEL - Assistant Area                                     */}
            {/* ================================================================ */}
            <Box
                sx={{
                    width: '50%',
                    display: 'flex',
                    flexDirection: 'column',
                    bgcolor: '#fafbfc',
                }}
            >
                {/* Tabs */}
                <Box sx={{ borderBottom: '1px solid', borderColor: 'grey.200', bgcolor: '#fff' }}>
                    <Tabs
                        value={activeTab}
                        onChange={(_, v) => setActiveTab(v)}
                        sx={{
                            px: 2,
                            '& .MuiTab-root': { textTransform: 'none', fontWeight: 600, minHeight: 56 },
                        }}
                    >
                        <Tab
                            icon={<LightbulbIcon sx={{ fontSize: 18 }} />}
                            iconPosition="start"
                            label={
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    가이드
                                    {guideResult && <CheckCircleIcon sx={{ fontSize: 16, color: 'success.main' }} />}
                                </Box>
                            }
                        />
                        <Tab
                            icon={<GradingIcon sx={{ fontSize: 18 }} />}
                            iconPosition="start"
                            label={
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    첨삭
                                    {correctionResult && <CheckCircleIcon sx={{ fontSize: 16, color: 'success.main' }} />}
                                    {!hasDraft && (
                                        <Chip label="초안 필요" size="small" variant="outlined" color="warning" sx={{ fontSize: 10, height: 20 }} />
                                    )}
                                </Box>
                            }
                        />
                    </Tabs>
                </Box>

                {/* Tab Content */}
                <Box sx={{ flex: 1, overflow: 'auto', p: 3 }}>
                    {/* ─── Loading State ────────────────────────────── */}
                    {(loading.guide || loading.correction) && (
                        <Fade in>
                            <Box sx={{ textAlign: 'center', py: 8 }}>
                                <CircularProgress size={48} sx={{ mb: 2 }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                                    {loading.guide ? 'AI가 가이드를 생성 중입니다...' : 'AI가 첨삭 중입니다...'}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {loading.guide
                                        ? '기업 아이덴티티와 직무 역량을 분석하고 있습니다.'
                                        : '인재상과 직무 맥락에 비추어 평가하고 있습니다.'}
                                </Typography>
                                <LinearProgress sx={{ maxWidth: 300, mx: 'auto', mt: 3 }} />
                            </Box>
                        </Fade>
                    )}

                    {/* ─── Tab 0: Guide ─────────────────────────────── */}
                    {activeTab === 0 && !loading.guide && (
                        <>
                            {guideResult ? (
                                <GuideResultView data={guideResult} />
                            ) : (
                                <EmptyState
                                    icon={<LightbulbIcon sx={{ fontSize: 64, color: 'grey.300' }} />}
                                    title="작성 가이드"
                                    description="기업명과 문항을 입력한 후 '가이드 받기' 버튼을 클릭하세요. AI가 기업 아이덴티티 x 직무 역량 x 역량 심리 분석을 결합하여 맞춤 가이드를 제공합니다."
                                />
                            )}
                        </>
                    )}

                    {/* ─── Tab 1: Correction ────────────────────────── */}
                    {activeTab === 1 && !loading.correction && (
                        <>
                            {correctionResult ? (
                                <CorrectionResultView data={correctionResult} />
                            ) : (
                                <EmptyState
                                    icon={<GradingIcon sx={{ fontSize: 64, color: 'grey.300' }} />}
                                    title="첨삭 결과"
                                    description={
                                        hasDraft
                                            ? "'첨삭 받기' 버튼을 클릭하면 AI가 초안을 기업 인재상에 비추어 평가하고, 3-Point 피드백과 수정본을 제공합니다."
                                            : '초안을 먼저 작성해주세요. 첨삭은 작성된 초안을 기반으로 진행됩니다.'
                                    }
                                    warning={!hasDraft}
                                />
                            )}
                        </>
                    )}
                </Box>
            </Box>
        </Box>
    );
};

// ─── Sub Components ─────────────────────────────────────────

/** 빈 상태 표시 */
const EmptyState = ({ icon, title, description, warning = false }) => (
    <Box sx={{ textAlign: 'center', py: 8, px: 4 }}>
        {icon}
        <Typography variant="h6" sx={{ fontWeight: 600, mt: 2, mb: 1, color: warning ? 'warning.main' : 'text.primary' }}>
            {title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 400, mx: 'auto', lineHeight: 1.8 }}>
            {description}
        </Typography>
        {warning && (
            <Chip
                icon={<ErrorOutlineIcon />}
                label="초안 작성이 필요합니다"
                color="warning"
                variant="outlined"
                sx={{ mt: 2 }}
            />
        )}
    </Box>
);

/** 가이드 결과 렌더링 */
const GuideResultView = ({ data }) => {
    const sections = [
        { key: 'question_intent', title: '질문 의도 분석', icon: '1', color: '#1565c0' },
        { key: 'keywords', title: '핵심 키워드', icon: '2', color: '#2e7d32' },
        { key: 'material_guide', title: '소재 선정 가이드', icon: '3', color: '#e65100' },
        { key: 'writing_points', title: '작성 포인트 (STAR 기법)', icon: '4', color: '#6a1b9a' },
        { key: 'cautions', title: '주의사항', icon: '5', color: '#c62828' },
    ];

    return (
        <Stack spacing={2.5}>
            <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
                <LightbulbIcon color="primary" /> 작성 가이드
            </Typography>
            {sections.map((sec) => {
                const value = data[sec.key];
                if (!value) return null;
                return (
                    <Card key={sec.key} variant="outlined" sx={{ borderRadius: 2, borderLeft: `4px solid ${sec.color}` }}>
                        <CardContent>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                                <Box
                                    sx={{
                                        width: 28,
                                        height: 28,
                                        borderRadius: '50%',
                                        bgcolor: sec.color,
                                        color: '#fff',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: 13,
                                        fontWeight: 700,
                                    }}
                                >
                                    {sec.icon}
                                </Box>
                                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                    {sec.title}
                                </Typography>
                            </Box>
                            {/* keywords는 배열 */}
                            {sec.key === 'keywords' && Array.isArray(value) ? (
                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                                    {value.map((kw, i) => (
                                        <Chip key={i} label={kw} size="small" color="success" variant="outlined" />
                                    ))}
                                </Box>
                            ) : (
                                <Typography variant="body2" sx={{ lineHeight: 1.9, whiteSpace: 'pre-wrap', color: 'text.secondary' }}>
                                    {value}
                                </Typography>
                            )}
                        </CardContent>
                    </Card>
                );
            })}
        </Stack>
    );
};

/** 첨삭 결과 렌더링 */
const CorrectionResultView = ({ data }) => (
    <Stack spacing={3}>
        <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
            <GradingIcon color="secondary" /> 첨삭 결과
        </Typography>

        {/* Score Summary */}
        {data.score && (
            <Card variant="outlined" sx={{ borderRadius: 2, bgcolor: '#f8f9ff' }}>
                <CardContent>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 2 }}>
                        항목별 점수
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                        {Object.entries(data.score).map(([key, val]) => {
                            const label = { logic: '논리성', job_fit: '직무적합', expression: '표현력', structure: '구조' }[key] || key;
                            const color = val >= 80 ? 'success' : val >= 60 ? 'warning' : 'error';
                            return (
                                <Box key={key} sx={{ textAlign: 'center', minWidth: 80 }}>
                                    <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                                        <CircularProgress variant="determinate" value={val} size={56} color={color} thickness={5} />
                                        <Box
                                            sx={{
                                                position: 'absolute',
                                                top: 0,
                                                left: 0,
                                                bottom: 0,
                                                right: 0,
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                            }}
                                        >
                                            <Typography variant="caption" sx={{ fontWeight: 700 }}>
                                                {val}
                                            </Typography>
                                        </Box>
                                    </Box>
                                    <Typography variant="caption" display="block" sx={{ mt: 0.5, fontWeight: 600 }}>
                                        {label}
                                    </Typography>
                                </Box>
                            );
                        })}
                    </Box>
                </CardContent>
            </Card>
        )}

        {/* 3-Point Feedback */}
        {data.feedback_points && (
            <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
                    3-Point 피드백
                </Typography>
                <Stack spacing={1.5}>
                    {data.feedback_points.map((point, i) => (
                        <Card key={i} variant="outlined" sx={{ borderRadius: 2, borderLeft: '4px solid #f57c00' }}>
                            <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                                <Chip label={point.category || `Point ${i + 1}`} size="small" color="warning" sx={{ mb: 1 }} />
                                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                                    {point.issue}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {point.suggestion}
                                </Typography>
                            </CardContent>
                        </Card>
                    ))}
                </Stack>
            </Box>
        )}

        {/* Revised Content */}
        {data.revised_content && (
            <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
                    수정본
                </Typography>
                <Paper
                    variant="outlined"
                    sx={{
                        p: 2.5,
                        borderRadius: 2,
                        bgcolor: '#fffdf5',
                        borderColor: '#e0d8b0',
                        lineHeight: 1.9,
                        fontSize: '0.95rem',
                        whiteSpace: 'pre-wrap',
                    }}
                >
                    <Typography variant="body2" sx={{ lineHeight: 1.9, whiteSpace: 'pre-wrap' }}>
                        {data.revised_content}
                    </Typography>
                </Paper>
            </Box>
        )}
    </Stack>
);
