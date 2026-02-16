/**
 * MainLayout - 좌측 사이드바 + 우측 메인 컨텐츠 레이아웃
 *
 * UI: 좌측 파란색 사이드바 (Navigation) + 우측 상단 유저 로그 + 메인 화이트 보드
 * Menu: 지원 검증, 기업 분석, 자소서 코칭, 면접 코칭 (상단) / Settings, My Page (하단)
 */
import React from 'react';
import {
    Box,
    Drawer,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Typography,
    Divider,
    Avatar,
    IconButton,
    Tooltip,
} from '@mui/material';
import BusinessIcon from '@mui/icons-material/Business';
import DescriptionIcon from '@mui/icons-material/Description';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import SettingsIcon from '@mui/icons-material/Settings';
import PersonIcon from '@mui/icons-material/Person';
import LogoutIcon from '@mui/icons-material/Logout';
import { useAuth } from '../contexts/AuthContext';

const DRAWER_WIDTH = 260;

/** 상단 메뉴 항목 */
const TOP_MENU = [
    { key: 'verification', label: '지원 검증', icon: <VerifiedUserIcon />, disabled: true },
    { key: 'company', label: '기업 분석', icon: <BusinessIcon /> },
    { key: 'resume', label: '자소서 코칭', icon: <DescriptionIcon /> },
    { key: 'interview', label: '면접 코칭', icon: <RecordVoiceOverIcon />, disabled: true },
];

/** 하단 메뉴 항목 */
const BOTTOM_MENU = [
    { key: 'settings', label: 'Settings', icon: <SettingsIcon />, disabled: true },
    { key: 'mypage', label: 'My Page', icon: <PersonIcon />, disabled: true },
];

export const MainLayout = ({ currentPage, onNavigate, children }) => {
    const { user, logout } = useAuth();

    return (
        <Box sx={{ display: 'flex', minHeight: '100vh' }}>
            {/* ─── Sidebar ────────────────────────────────────── */}
            <Drawer
                variant="permanent"
                sx={{
                    width: DRAWER_WIDTH,
                    flexShrink: 0,
                    '& .MuiDrawer-paper': {
                        width: DRAWER_WIDTH,
                        boxSizing: 'border-box',
                        background: 'linear-gradient(180deg, #1565c0 0%, #0d47a1 100%)',
                        color: '#fff',
                        borderRight: 'none',
                    },
                }}
            >
                {/* Logo / Brand */}
                <Box sx={{ px: 3, py: 3, textAlign: 'center' }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, letterSpacing: 1 }}>
                        My Career AI
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>
                        Human-Centric Career Agent
                    </Typography>
                </Box>

                <Divider sx={{ borderColor: 'rgba(255,255,255,0.15)', mx: 2 }} />

                {/* Top Navigation */}
                <List sx={{ px: 1, pt: 2, flex: 1 }}>
                    {TOP_MENU.map((item) => (
                        <ListItemButton
                            key={item.key}
                            selected={currentPage === item.key}
                            disabled={item.disabled}
                            onClick={() => onNavigate(item.key)}
                            sx={{
                                borderRadius: 2,
                                mb: 0.5,
                                mx: 1,
                                '&.Mui-selected': {
                                    bgcolor: 'rgba(255,255,255,0.18)',
                                    '&:hover': { bgcolor: 'rgba(255,255,255,0.22)' },
                                },
                                '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' },
                                '&.Mui-disabled': { opacity: 0.4 },
                            }}
                        >
                            <ListItemIcon sx={{ color: 'inherit', minWidth: 40 }}>{item.icon}</ListItemIcon>
                            <ListItemText
                                primary={item.label}
                                primaryTypographyProps={{ fontSize: 14, fontWeight: currentPage === item.key ? 600 : 400 }}
                            />
                            {item.disabled && (
                                <Typography variant="caption" sx={{ opacity: 0.5, fontSize: 10 }}>
                                    Soon
                                </Typography>
                            )}
                        </ListItemButton>
                    ))}
                </List>

                {/* Bottom Navigation */}
                <Divider sx={{ borderColor: 'rgba(255,255,255,0.15)', mx: 2 }} />
                <List sx={{ px: 1, pb: 1 }}>
                    {BOTTOM_MENU.map((item) => (
                        <ListItemButton
                            key={item.key}
                            disabled={item.disabled}
                            onClick={() => onNavigate(item.key)}
                            sx={{
                                borderRadius: 2,
                                mx: 1,
                                mb: 0.5,
                                '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' },
                                '&.Mui-disabled': { opacity: 0.4 },
                            }}
                        >
                            <ListItemIcon sx={{ color: 'inherit', minWidth: 40 }}>{item.icon}</ListItemIcon>
                            <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: 13 }} />
                        </ListItemButton>
                    ))}
                </List>

                {/* User Info */}
                <Divider sx={{ borderColor: 'rgba(255,255,255,0.15)', mx: 2 }} />
                <Box sx={{ px: 2, py: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Avatar sx={{ width: 36, height: 36, bgcolor: 'rgba(255,255,255,0.2)', fontSize: 14 }}>
                        {user?.name?.[0] || 'U'}
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }} noWrap>
                            {user?.name || 'Guest'}
                        </Typography>
                        <Typography variant="caption" sx={{ opacity: 0.6, fontSize: 11 }} noWrap>
                            {user?.email || ''}
                        </Typography>
                    </Box>
                    <Tooltip title="Logout">
                        <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.6)' }} onClick={logout}>
                            <LogoutIcon fontSize="small" />
                        </IconButton>
                    </Tooltip>
                </Box>
            </Drawer>

            {/* ─── Main Content ───────────────────────────────── */}
            <Box
                component="main"
                sx={{
                    flexGrow: 1,
                    bgcolor: '#f5f7fa',
                    minHeight: '100vh',
                    overflow: 'auto',
                }}
            >
                {children}
            </Box>
        </Box>
    );
};
