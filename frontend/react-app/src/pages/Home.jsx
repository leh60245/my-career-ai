/**
 * Home - 메인 랜딩 페이지
 *
 * 서비스의 대문(Entry Point)으로 4개 핵심 서비스로의 내비게이션 허브 역할.
 * Hero Section (서비스 소개) + 4 Service Cards (Grid Layout)
 */
import React from 'react';
import {
    Box,
    Typography,
    Card,
    CardActionArea,
    CardContent,
    Grid,
    Chip,
    alpha,
} from '@mui/material';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import BusinessIcon from '@mui/icons-material/Business';
import DescriptionIcon from '@mui/icons-material/Description';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';

const SERVICE_CARDS = [
    {
        key: 'verification',
        title: '지원 검증',
        subtitle: '합격 가능성 진단',
        description: '지원하려는 기업과 직무에 대한 합격 가능성을 AI가 진단합니다.',
        icon: VerifiedUserIcon,
        color: '#7c4dff',
        disabled: true,
    },
    {
        key: 'company',
        title: '기업 분석',
        subtitle: 'AI 심층 리포트',
        description: 'Stanford STORM 기반 RAG로 기업의 재무, 경쟁력, ESG 등을 심층 분석합니다.',
        icon: BusinessIcon,
        color: '#1565c0',
        disabled: false,
    },
    {
        key: 'resume',
        title: '자소서 코칭',
        subtitle: '논리적 첨삭 & 가이드',
        description: '기업 인재상에 맞춘 Context-Aware 작성 가이드와 논리적 첨삭을 제공합니다.',
        icon: DescriptionIcon,
        color: '#2e7d32',
        disabled: false,
    },
    {
        key: 'interview',
        title: '면접 코칭',
        subtitle: '실전 모의 면접',
        description: 'AI 면접관과 실전 모의 면접을 통해 답변 역량을 강화합니다.',
        icon: RecordVoiceOverIcon,
        color: '#e65100',
        disabled: true,
    },
];

export const Home = ({ onNavigate }) => {
    return (
        <Box sx={{ px: 4, py: 3, maxWidth: 1100, mx: 'auto' }}>
            {/* ─── Hero Section ────────────────────────────────── */}
            <Box sx={{ textAlign: 'center', pt: 8, pb: 6 }}>
                <Typography
                    variant="h3"
                    sx={{
                        fontWeight: 800,
                        background: 'linear-gradient(135deg, #1565c0 0%, #0d47a1 50%, #1a237e 100%)',
                        backgroundClip: 'text',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                        mb: 2,
                    }}
                >
                    My Career AI
                </Typography>
                <Typography variant="h5" sx={{ color: 'text.secondary', fontWeight: 400, mb: 1 }}>
                    Human-Centric Career Agent
                </Typography>
                <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 600, mx: 'auto', lineHeight: 1.8, mt: 2 }}>
                    AI 기반 기업 심층 분석과 자소서 코칭으로
                    <br />
                    취업 준비의 모든 과정을 체계적으로 지원합니다.
                </Typography>
            </Box>

            {/* ─── Service Cards ───────────────────────────────── */}
            <Grid container spacing={3}>
                {SERVICE_CARDS.map((card) => {
                    const Icon = card.icon;
                    return (
                        <Grid item xs={12} sm={6} key={card.key}>
                            <Card
                                elevation={0}
                                sx={{
                                    border: '1px solid',
                                    borderColor: card.disabled ? 'grey.200' : 'grey.200',
                                    borderRadius: 3,
                                    opacity: card.disabled ? 0.55 : 1,
                                    transition: 'all 0.25s ease',
                                    ...(!card.disabled && {
                                        '&:hover': {
                                            borderColor: card.color,
                                            boxShadow: `0 4px 20px ${alpha(card.color, 0.15)}`,
                                            transform: 'translateY(-4px)',
                                        },
                                    }),
                                }}
                            >
                                <CardActionArea
                                    disabled={card.disabled}
                                    onClick={() => onNavigate(card.key)}
                                    sx={{ p: 3, minHeight: 180 }}
                                >
                                    <CardContent sx={{ p: '0 !important' }}>
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                                            <Box
                                                sx={{
                                                    width: 52,
                                                    height: 52,
                                                    borderRadius: 2.5,
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    bgcolor: alpha(card.color, 0.1),
                                                    color: card.color,
                                                }}
                                            >
                                                <Icon sx={{ fontSize: 28 }} />
                                            </Box>
                                            <Box>
                                                <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                                                    {card.title}
                                                </Typography>
                                                <Typography variant="caption" sx={{ color: card.color, fontWeight: 600 }}>
                                                    {card.subtitle}
                                                </Typography>
                                            </Box>
                                            {card.disabled && (
                                                <Chip label="Coming Soon" size="small" variant="outlined" sx={{ ml: 'auto', fontSize: 11 }} />
                                            )}
                                        </Box>
                                        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
                                            {card.description}
                                        </Typography>
                                    </CardContent>
                                </CardActionArea>
                            </Card>
                        </Grid>
                    );
                })}
            </Grid>
        </Box>
    );
};
