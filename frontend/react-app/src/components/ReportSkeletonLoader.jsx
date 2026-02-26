import React from 'react';
import { Box, Paper, Skeleton, Stack, Tabs, Tab, alpha } from '@mui/material';

/**
 * ReportSkeletonLoader - 리포트 로딩 시 스켈레톤 UI
 *
 * 단순 스피너 대신, 실제 리포트 레이아웃과 유사한 뼈대를 표시하여
 * 사용자에게 진행 상태를 시각적으로 암시합니다.
 *
 * Wishlist 요구: "단순 스피너 사용을 금지함. 스켈레톤 UI 또는 프로그레스 바 필수"
 */

/** 헤더 스켈레톤 (기업명 + 메타 정보) */
const HeaderSkeleton = () => (
    <Paper
        elevation={0}
        sx={{
            p: 3,
            mb: 3,
            border: '1px solid',
            borderColor: 'grey.200',
            borderRadius: 2,
        }}
    >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Skeleton variant="rounded" width={56} height={56} />
            <Box sx={{ flex: 1 }}>
                <Skeleton variant="text" width="40%" height={40} />
                <Skeleton variant="text" width="25%" height={20} sx={{ mt: 0.5 }} />
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Skeleton variant="rounded" width={80} height={24} />
                    <Skeleton variant="rounded" width={100} height={24} />
                    <Skeleton variant="rounded" width={90} height={24} />
                </Stack>
            </Box>
            <Skeleton variant="rounded" width={100} height={36} />
        </Box>
    </Paper>
);

/** 탭 바 스켈레톤 */
const TabsSkeleton = () => (
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
        <Tabs value={0} sx={{ pointerEvents: 'none' }}>
            <Tab label={<Skeleton width={60} />} />
            <Tab label={<Skeleton width={50} />} />
            <Tab label={<Skeleton width={70} />} />
            <Tab label={<Skeleton width={50} />} />
        </Tabs>
    </Paper>
);

/** 본문 콘텐츠 스켈레톤 */
const ContentSkeleton = () => (
    <Paper
        elevation={0}
        sx={{
            p: { xs: 2, sm: 4 },
            border: '1px solid',
            borderColor: 'grey.200',
            borderRadius: 2,
        }}
    >
        {/* 섹션 제목 */}
        <Skeleton variant="text" width="30%" height={32} sx={{ mb: 2 }} />

        {/* 카드 그리드 (기업 개요 형태) */}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
            {[1, 2, 3].map((i) => (
                <Paper
                    key={i}
                    elevation={0}
                    sx={{
                        flex: 1,
                        p: 2,
                        border: '1px solid',
                        borderColor: 'grey.100',
                        borderRadius: 2,
                    }}
                >
                    <Skeleton variant="text" width="50%" height={20} sx={{ mb: 1 }} />
                    <Skeleton variant="text" width="80%" height={24} />
                </Paper>
            ))}
        </Stack>

        {/* 텍스트 블록 */}
        <Skeleton variant="text" width="20%" height={28} sx={{ mb: 1.5 }} />
        <Skeleton variant="text" width="100%" />
        <Skeleton variant="text" width="95%" />
        <Skeleton variant="text" width="88%" />
        <Skeleton variant="text" width="92%" sx={{ mb: 2.5 }} />

        {/* 불릿 리스트 형태 */}
        <Skeleton variant="text" width="25%" height={28} sx={{ mb: 1.5 }} />
        {[1, 2, 3, 4].map((i) => (
            <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                <Skeleton variant="circular" width={8} height={8} />
                <Skeleton variant="text" width={`${70 + Math.random() * 25}%`} height={22} />
            </Box>
        ))}
    </Paper>
);

/**
 * 아코디언 모드 스켈레톤 (기업 전체 리포트 조회 시)
 */
const AccordionSkeleton = () => (
    <Box>
        {/* 헤더 */}
        <Paper
            elevation={0}
            sx={{
                p: 3,
                mb: 3,
                border: '1px solid',
                borderColor: 'grey.200',
                borderRadius: 2,
            }}
        >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Skeleton variant="rounded" width={56} height={56} />
                <Box sx={{ flex: 1 }}>
                    <Skeleton variant="text" width="35%" height={36} />
                    <Skeleton variant="text" width="20%" height={18} />
                </Box>
                <Skeleton variant="rounded" width={90} height={36} />
            </Box>
        </Paper>

        {/* 아코디언 아이템들 */}
        <Stack spacing={1.5}>
            {[1, 2, 3, 4].map((i) => (
                <Paper
                    key={i}
                    elevation={0}
                    sx={{
                        p: 2,
                        border: '1px solid',
                        borderColor: 'grey.200',
                        borderRadius: 2,
                    }}
                >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Skeleton variant="rounded" width={40} height={24} />
                        <Box sx={{ flex: 1 }}>
                            <Skeleton variant="text" width={`${40 + i * 10}%`} height={24} />
                            <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                                <Skeleton variant="text" width={60} height={16} />
                                <Skeleton variant="text" width={80} height={16} />
                            </Stack>
                        </Box>
                        <Skeleton variant="circular" width={24} height={24} />
                    </Box>
                </Paper>
            ))}
        </Stack>
    </Box>
);

/**
 * 폴링 상태 스켈레톤 (리포트 생성 대기 중)
 */
export const PollingSkeleton = ({ progress = 0, message = '' }) => (
    <Paper
        elevation={0}
        sx={{
            p: { xs: 3, sm: 5 },
            textAlign: 'center',
            border: '1px solid',
            borderColor: 'grey.200',
            borderRadius: 2,
        }}
    >
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 2,
            }}
        >
            {/* 파동 애니메이션 대신 스켈레톤 블록 */}
            <Box
                sx={{
                    width: 80,
                    height: 80,
                    borderRadius: '50%',
                    bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    animation: 'pulse 2s ease-in-out infinite',
                    '@keyframes pulse': {
                        '0%, 100%': { transform: 'scale(1)', opacity: 1 },
                        '50%': { transform: 'scale(1.1)', opacity: 0.7 },
                    },
                }}
            >
                <Skeleton
                    variant="circular"
                    width={48}
                    height={48}
                    animation="wave"
                />
            </Box>

            <Skeleton variant="text" width={200} height={32} animation="wave" />
            <Skeleton variant="text" width={280} height={20} animation="wave" />

            {/* 프로그레스 바 스켈레톤 */}
            <Box sx={{ width: '80%', mt: 1 }}>
                <Skeleton
                    variant="rounded"
                    width="100%"
                    height={10}
                    animation="wave"
                    sx={{ borderRadius: 5 }}
                />
            </Box>

            <Stack direction="row" spacing={1}>
                <Skeleton variant="rounded" width={100} height={24} />
            </Stack>
        </Box>
    </Paper>
);

/**
 * ReportSkeletonLoader - 메인 스켈레톤 컴포넌트
 *
 * @param {'single' | 'accordion' | 'polling'} variant - 스켈레톤 종류
 * @param {number} progress - 폴링 진행률 (0-100)
 * @param {string} message - 폴링 메시지
 */
export const ReportSkeletonLoader = ({ variant = 'single', progress, message }) => {
    if (variant === 'polling') {
        return <PollingSkeleton progress={progress} message={message} />;
    }

    if (variant === 'accordion') {
        return <AccordionSkeleton />;
    }

    // single mode
    return (
        <Box>
            <HeaderSkeleton />
            <TabsSkeleton />
            <ContentSkeleton />
        </Box>
    );
};
