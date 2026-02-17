import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Tab,
  Tabs,
  Tooltip,
  Typography,
  alpha,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import MenuIcon from '@mui/icons-material/Menu';
import DownloadIcon from '@mui/icons-material/Download';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import BusinessIcon from '@mui/icons-material/Business';
import ArticleIcon from '@mui/icons-material/Article';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getJobStatus, getReport, getReportByJobId, fetchReportsByCompany } from '../services/apiClient';
import '../styles/ReportViewer.css';

/**
 * ORDERED_TOPICS - config.py TOPICS 순서와 일치하는 토픽 표시 순서
 * '직접 입력(custom)'은 제외
 */
const ORDERED_TOPICS = [
  '기업 개요 및 주요 사업 내용',
  '최근 3개년 재무제표 및 재무 상태 분석',
  '산업 내 경쟁 우위 및 경쟁사 비교 (SWOT)',
  '주요 제품 및 서비스 시장 점유율 분석',
  'R&D 투자 현황 및 기술 경쟁력',
  'ESG (환경, 사회, 지배구조) 평가',
];

/**
 * ReportViewer v2 — demo_light 기능 포팅
 *
 * 추가 기능:
 *   1. 인라인 인용 링크: [1] → [[1]](url) 클릭 가능
 *   2. 참고문헌 상세 패널: 번호별 title + URL + highlight snippets
 *   3. 대화 로그 뷰어: 페르소나별 탭 + 채팅 형태 UI
 *   4. TOC 사이드바: 마크다운 헤딩 → 클릭 이동
 *   5. HTML 다운로드: 리포트를 HTML 파일로 내보내기
 */

const POLL_INTERVAL = 3000;
const TOC_DRAWER_WIDTH = 280;

// ════════════════════════════════════════════════════════════
// Helper Functions
// ════════════════════════════════════════════════════════════

/**
 * 리포트 텍스트에서 [1], [2] 같은 인용 번호를 실제 URL 링크로 변환
 */
function addInlineCitationLinks(text, referencesData) {
  if (!text || !referencesData) return text;
  const urlToIndex = referencesData.url_to_unified_index || {};
  const indexToUrl = {};
  for (const [url, idx] of Object.entries(urlToIndex)) {
    indexToUrl[idx] = url;
  }
  return text.replace(/\[(\d+)\]/g, (match, num) => {
    const url = indexToUrl[parseInt(num, 10)];
    return url ? `[[${num}]](${url})` : match;
  });
}

/**
 * references_data → 번호 → {url, title, snippets} 매핑
 */
function buildCitationDict(referencesData) {
  if (!referencesData) return {};
  const urlToIndex = referencesData.url_to_unified_index || {};
  const urlToInfo = referencesData.url_to_info || {};
  const dict = {};
  for (const [url, idx] of Object.entries(urlToIndex)) {
    const info = urlToInfo[url] || {};
    dict[idx] = {
      url,
      title: info.title || url,
      snippets: info.snippets || [],
    };
  }
  return dict;
}

/**
 * 마크다운 텍스트에서 헤딩을 추출하여 TOC 배열 생성
 */
function extractTocFromMarkdown(markdownText) {
  if (!markdownText) return [];
  const toc = [];
  for (const line of markdownText.split('\n')) {
    const match = line.match(/^(#{1,4})\s+(.+)/);
    if (match) {
      const level = match[1].length;
      const title = match[2].trim();
      const anchor = title
        .toLowerCase()
        .replace(/[^\w\s가-힣-]/g, '')
        .replace(/\s+/g, '-');
      toc.push({ level, title, anchor });
    }
  }
  return toc;
}

/**
 * conversation_log → 페르소나별 대화 파싱
 * 반환: [{ name, description, messages: [{role, content}] }]
 */
function parseConversationLog(conversationLog) {
  if (!conversationLog) return [];
  let conversations;
  if (Array.isArray(conversationLog)) {
    conversations = conversationLog;
  } else if (Array.isArray(conversationLog.conversations)) {
    conversations = conversationLog.conversations;
  } else {
    return [];
  }

  return conversations.map((entry) => {
    const perspective = entry.perspective || '';
    let name, description;
    if (perspective.includes(': ')) {
      [name, description] = perspective.split(': ', 2);
    } else if (perspective.includes(' - ')) {
      [name, description] = perspective.split(' - ', 2);
    } else {
      name = '';
      description = perspective;
    }
    const messages = [];
    for (const turn of entry.dlg_turns || []) {
      if (turn.user_utterance) messages.push({ role: 'user', content: turn.user_utterance });
      if (turn.agent_utterance) {
        const cleaned = turn.agent_utterance.replace(/\[\d+\]/g, '').replace(/\s{2,}/g, ' ').trim();
        messages.push({ role: 'assistant', content: cleaned });
      }
    }
    return { name: name || '연구원', description: description || '', messages };
  });
}

/**
 * 리포트를 HTML 파일로 내보내기
 */
function exportAsHtml(report, citationDict) {
  const tocHtml = extractTocFromMarkdown(report.report_content)
    .map((item) => {
      const indent = (item.level - 1) * 20;
      return `<li style="margin-left:${indent}px"><a href="#${item.anchor}">${item.title}</a></li>`;
    })
    .join('\n');

  let bodyContent = addInlineCitationLinks(report.report_content, report.references_data) || '';
  // 간단한 마크다운 → HTML 변환 (헤딩)
  bodyContent = bodyContent.replace(/^#### (.+)$/gm, '<h4 id="$1">$1</h4>');
  bodyContent = bodyContent.replace(/^### (.+)$/gm, '<h3 id="$1">$1</h3>');
  bodyContent = bodyContent.replace(/^## (.+)$/gm, '<h2 id="$1">$1</h2>');
  bodyContent = bodyContent.replace(/^# (.+)$/gm, '<h1 id="$1">$1</h1>');
  bodyContent = bodyContent.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  bodyContent = bodyContent.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  bodyContent = bodyContent.replace(/\n\n/g, '</p><p>');
  bodyContent = `<p>${bodyContent}</p>`;

  const refsHtml = Object.entries(citationDict)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([idx, ref]) => `<div class="ref-item"><span class="ref-title">[${idx}] ${ref.title}</span><br/><a class="ref-url" href="${ref.url}" target="_blank">${ref.url}</a></div>`)
    .join('\n');

  const html = `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <title>${report.company_name} - ${report.topic}</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:900px;margin:0 auto;padding:20px;line-height:1.8;color:#333}
    h1{text-align:center;border-bottom:3px solid #1976d2;padding-bottom:10px}
    h2{border-bottom:1px solid #ddd;padding-bottom:8px;margin-top:30px}
    a{color:#1976d2}
    .toc{background:#f5f5f5;padding:16px;border-radius:8px;margin:20px 0}
    .toc ul{list-style:none;padding:0}
    .toc li{margin:4px 0}
    .references{margin-top:40px;border-top:2px solid #1976d2;padding-top:20px}
    .ref-item{margin-bottom:12px}
    .ref-title{font-weight:bold}
    .ref-url{color:#1976d2;font-size:.9em}
    .meta{text-align:center;color:#666;font-size:.9em;margin-bottom:30px}
  </style>
</head>
<body>
  <h1>${report.company_name} - ${report.topic}</h1>
  <div class="meta">모델: ${report.model_name} | 생성: ${report.created_at ? new Date(report.created_at).toLocaleDateString('ko-KR') : ''}</div>
  <div class="toc"><h2>목차</h2><ul>${tocHtml}</ul></div>
  <div class="content">${bodyContent}</div>
  <div class="references"><h2>참고 문헌</h2>${refsHtml}</div>
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${report.company_name}_${report.topic}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

// ════════════════════════════════════════════════════════════
// Sub-Components
// ════════════════════════════════════════════════════════════

/** TOC 사이드바 */
const TocSidebar = ({ toc, open, onClose }) => (
  <Drawer
    variant="persistent"
    anchor="left"
    open={open}
    sx={{
      width: open ? TOC_DRAWER_WIDTH : 0,
      flexShrink: 0,
      '& .MuiDrawer-paper': {
        width: TOC_DRAWER_WIDTH,
        boxSizing: 'border-box',
        position: 'relative',
        height: '100%',
        borderRight: '1px solid #e0e0e0',
      },
    }}
  >
    <Box sx={{ p: 2, borderBottom: '1px solid #e0e0e0' }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>📑 목차</Typography>
    </Box>
    <List dense sx={{ overflow: 'auto', flex: 1 }}>
      {toc.map((item, idx) => (
        <ListItemButton
          key={idx}
          sx={{ pl: 1 + (item.level - 1) * 2 }}
          onClick={() => {
            const el = document.getElementById(item.anchor);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            if (window.innerWidth < 960) onClose();
          }}
        >
          <ListItemText
            primary={item.title}
            primaryTypographyProps={{
              fontSize: item.level === 1 ? '0.95rem' : '0.85rem',
              fontWeight: item.level <= 2 ? 'bold' : 'normal',
              color: item.level === 1 ? 'primary.main' : 'text.primary',
              noWrap: true,
            }}
          />
        </ListItemButton>
      ))}
    </List>
  </Drawer>
);

/** 참고문헌 상세 패널 */
const ReferencesPanel = ({ citationDict }) => {
  const [selectedRef, setSelectedRef] = useState(null);
  const sortedEntries = useMemo(
    () => Object.entries(citationDict).sort(([a], [b]) => Number(a) - Number(b)),
    [citationDict]
  );

  if (sortedEntries.length === 0) {
    return <Typography color="text.secondary">참고 문헌 정보가 없습니다.</Typography>;
  }

  const activeRef = selectedRef !== null ? citationDict[selectedRef] : null;

  return (
    <Box>
      {/* 번호 버튼 그리드 */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 2 }}>
        {sortedEntries.map(([idx]) => (
          <Chip
            key={idx}
            label={`[${idx}]`}
            size="small"
            variant={selectedRef === idx ? 'filled' : 'outlined'}
            color={selectedRef === idx ? 'primary' : 'default'}
            onClick={() => setSelectedRef(selectedRef === idx ? null : idx)}
            sx={{ cursor: 'pointer', fontFamily: 'monospace' }}
          />
        ))}
      </Box>

      {/* 선택된 참고문헌 상세 */}
      {activeRef ? (
        <Paper variant="outlined" sx={{ p: 2, backgroundColor: '#fafafa' }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
            [{selectedRef}] {activeRef.title}
          </Typography>
          <Typography
            variant="caption"
            component="a"
            href={activeRef.url}
            target="_blank"
            rel="noopener noreferrer"
            sx={{ color: '#1976d2', display: 'block', mb: 1.5, wordBreak: 'break-all' }}
          >
            {activeRef.url}
          </Typography>
          {activeRef.snippets?.length > 0 && (
            <>
              <Typography variant="caption" sx={{ fontWeight: 'bold', color: 'text.secondary' }}>
                하이라이트:
              </Typography>
              {activeRef.snippets.map((snippet, i) => (
                <Typography
                  key={i}
                  variant="body2"
                  sx={{
                    mt: 0.5, p: 1,
                    backgroundColor: '#fff9c4',
                    borderRadius: 1,
                    fontSize: '0.85rem',
                    lineHeight: 1.5,
                    borderLeft: '3px solid #ffc107',
                  }}
                >
                  {snippet}
                </Typography>
              ))}
            </>
          )}
        </Paper>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          참고문헌 번호를 클릭하여 상세 정보를 확인하세요.
        </Typography>
      )}

      {/* 전체 목록 */}
      <Divider sx={{ my: 2 }} />
      <Box component="ul" sx={{ pl: 2, m: 0 }}>
        {sortedEntries.map(([idx, ref]) => (
          <Box key={idx} component="li" sx={{ mb: 1.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
              [{idx}] {ref.title}
            </Typography>
            <Typography
              variant="caption"
              component="a"
              href={ref.url}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ color: '#1976d2', wordBreak: 'break-all' }}
            >
              {ref.url}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

/** 대화 로그 뷰어 — 페르소나별 탭 + 채팅 UI */
const ConversationLogViewer = ({ conversationLog }) => {
  const personas = useMemo(() => parseConversationLog(conversationLog), [conversationLog]);
  const [tabIndex, setTabIndex] = useState(0);

  if (personas.length === 0) {
    return <Typography color="text.secondary">대화 로그가 없습니다.</Typography>;
  }

  const current = personas[tabIndex] || personas[0];

  return (
    <Box>
      <Tabs
        value={tabIndex}
        onChange={(_, v) => setTabIndex(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
      >
        {personas.map((p, i) => (
          <Tab key={i} label={p.name || `연구원 ${i + 1}`} />
        ))}
      </Tabs>

      {current.description && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <Typography variant="body2">{current.description}</Typography>
        </Alert>
      )}

      <Box sx={{ maxHeight: 500, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 1.5, p: 1 }}>
        {current.messages.map((msg, i) => (
          <Box key={i} sx={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <Paper
              elevation={0}
              sx={{
                p: 1.5,
                maxWidth: '75%',
                backgroundColor: msg.role === 'user' ? '#e3f2fd' : '#f5f5f5',
                borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                border: '1px solid',
                borderColor: msg.role === 'user' ? '#bbdefb' : '#e0e0e0',
              }}
            >
              <Typography
                variant="caption"
                sx={{ fontWeight: 'bold', color: msg.role === 'user' ? '#1565c0' : '#555', display: 'block', mb: 0.5 }}
              >
                {msg.role === 'user' ? '🔍 질문' : '💡 답변'}
              </Typography>
              <Typography variant="body2" sx={{ lineHeight: 1.6, fontWeight: msg.role === 'user' ? 'bold' : 'normal' }}>
                {msg.content}
              </Typography>
            </Paper>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

// ── Utility: extract text from React children ──
function extractTextFromChildren(children) {
  if (typeof children === 'string') return children;
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join('');
  if (children?.props?.children) return extractTextFromChildren(children.props.children);
  return String(children || '');
}

function toAnchor(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\s가-힣-]/g, '')
    .replace(/\s+/g, '-');
}

/** 공유 Markdown 렌더링 컴포넌트 설정 */
const markdownComponents = {
  h1: ({ children, ...props }) => {
    const text = extractTextFromChildren(children);
    const id = toAnchor(text);
    return <Typography id={id} variant="h3" component="h1" sx={{ mt: 3, mb: 2, fontWeight: 'bold' }} {...props}>{children}</Typography>;
  },
  h2: ({ children, ...props }) => {
    const text = extractTextFromChildren(children);
    const id = toAnchor(text);
    return <Typography id={id} variant="h5" component="h2" sx={{ mt: 2.5, mb: 1.5, fontWeight: 'bold' }} {...props}>{children}</Typography>;
  },
  h3: ({ children, ...props }) => {
    const text = extractTextFromChildren(children);
    const id = toAnchor(text);
    return <Typography id={id} variant="h6" component="h3" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }} {...props}>{children}</Typography>;
  },
  p: ({ ...props }) => <Typography variant="body1" sx={{ mb: 1.5, lineHeight: 1.7 }} {...props} />,
  ul: ({ ...props }) => <Box component="ul" sx={{ ml: 2, mb: 1.5 }} {...props} />,
  ol: ({ ...props }) => <Box component="ol" sx={{ ml: 2, mb: 1.5 }} {...props} />,
  li: ({ ...props }) => <Box component="li" sx={{ mb: 0.5, lineHeight: 1.6 }} {...props} />,
  table: ({ ...props }) => (
    <Box sx={{ overflowX: 'auto', mb: 2, border: '1px solid #ddd', borderRadius: '4px' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.95rem' }} {...props} />
    </Box>
  ),
  thead: ({ ...props }) => <thead style={{ backgroundColor: '#f0f0f0' }} {...props} />,
  th: ({ ...props }) => <th style={{ padding: '12px', textAlign: 'left', borderBottom: '2px solid #ddd', fontWeight: 'bold' }} {...props} />,
  td: ({ ...props }) => <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }} {...props} />,
  code: ({ inline, ...props }) =>
    inline
      ? <code style={{ backgroundColor: '#f5f5f5', padding: '2px 6px', borderRadius: '3px', fontFamily: 'monospace' }} {...props} />
      : <pre style={{ backgroundColor: '#f5f5f5', padding: '12px', borderRadius: '4px', overflowX: 'auto', marginBottom: '1.5rem' }}><code {...props} /></pre>,
  blockquote: ({ ...props }) => (
    <Box component="blockquote" sx={{ borderLeft: '4px solid #1976d2', pl: 2, ml: 0, my: 2, fontStyle: 'italic', color: 'text.secondary' }} {...props} />
  ),
  a: ({ href, children, ...props }) => {
    const childText = extractTextFromChildren(children);
    const isCitation = /^\[\d+\]$/.test(childText);
    if (isCitation) {
      return (
        <Tooltip title={href || ''} arrow>
          <Typography
            component="a" href={href} target="_blank" rel="noopener noreferrer"
            sx={{ color: '#1976d2', fontWeight: 'bold', fontSize: '0.8em', verticalAlign: 'super', textDecoration: 'none', cursor: 'pointer', '&:hover': { textDecoration: 'underline', color: '#1565c0' } }}
            {...props}
          >
            {children}
          </Typography>
        </Tooltip>
      );
    }
    return (
      <Typography
        component="a" href={href} target="_blank" rel="noopener noreferrer"
        sx={{ color: '#1976d2', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
        {...props}
      >
        {children}
      </Typography>
    );
  },
};

// ════════════════════════════════════════════════════════════
// Main Component
// ════════════════════════════════════════════════════════════

const ReportViewer = ({ jobId, companyName, initialStatus, onBack }) => {
  // ─── Determine mode ──────────────────────────────
  // accordion mode: companyName is provided (no jobId)
  // single mode: jobId is provided
  const isAccordionMode = Boolean(companyName) && !jobId;

  // ─── Accordion Mode State ─────────────────────────
  const [accordionReports, setAccordionReports] = useState([]);
  const [accordionLoading, setAccordionLoading] = useState(false);
  const [accordionError, setAccordionError] = useState(null);
  const [expandedTopic, setExpandedTopic] = useState(null);

  // ─── Single Mode State ────────────────────────────
  const deriveInitialPhase = () => {
    const s = (initialStatus || '').toUpperCase();
    if (s === 'COMPLETED') return 'loading';
    if (s === 'FAILED') return 'error';
    return 'polling';
  };

  const [phase, setPhase] = useState(deriveInitialPhase);
  const [statusInfo, setStatusInfo] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(deriveInitialPhase() === 'error' ? '작업이 실패했습니다.' : null);
  const [pollingCount, setPollingCount] = useState(0);
  const [tocOpen, setTocOpen] = useState(true);
  const [activeSection, setActiveSection] = useState('report');

  // ─── Guard: missing jobId ───────────────────────
  useEffect(() => {
    if (jobId) return;
    setError('유효한 작업 ID가 없습니다.');
    setPhase('error');
  }, [jobId]);

  // ─── Phase 1: Status Polling ────────────────────
  useEffect(() => {
    if (!jobId || phase !== 'polling') return;
    let cancelled = false;

    const checkStatus = async () => {
      try {
        const data = await getJobStatus(jobId);
        if (cancelled) return;
        setStatusInfo(data);
        const s = (data.status || '').toUpperCase();
        if (s === 'COMPLETED') setPhase('loading');
        else if (s === 'FAILED') {
          setError(data.error_message || data.message || '작업이 실패했습니다.');
          setPhase('error');
        }
      } catch (err) {
        if (cancelled) return;
        setError('상태 확인에 실패했습니다. 서버 연결을 확인하세요.');
        setPhase('error');
      }
    };

    checkStatus();
    const interval = setInterval(() => {
      checkStatus();
      setPollingCount((c) => c + 1);
    }, POLL_INTERVAL);

    return () => { cancelled = true; clearInterval(interval); };
  }, [jobId, phase]);

  // ─── Phase 2: Load Report ──────────────────────
  useEffect(() => {
    if (phase !== 'loading' || !jobId) return;
    let cancelled = false;

    const loadReport = async () => {
      try {
        let reportData;
        if (statusInfo?.report_id) reportData = await getReport(statusInfo.report_id);
        else reportData = await getReportByJobId(jobId);
        if (cancelled) return;
        setReport(reportData);
        setPhase('done');
      } catch (err) {
        if (cancelled) return;
        setError('리포트를 불러올 수 없습니다.');
        setPhase('error');
      }
    };

    loadReport();
    return () => { cancelled = true; };
  }, [phase, statusInfo, jobId]);

  // ─── Accordion Mode: Fetch all reports ──────────
  useEffect(() => {
    if (!isAccordionMode || !companyName) return;
    let cancelled = false;

    const loadCompanyReports = async () => {
      setAccordionLoading(true);
      setAccordionError(null);
      try {
        const reports = await fetchReportsByCompany(companyName);
        if (cancelled) return;
        // Sort by ORDERED_TOPICS
        const sorted = sortByTopicOrder(reports || []);
        setAccordionReports(sorted);
        // Default expand first topic
        if (sorted.length > 0) {
          setExpandedTopic(sorted[0].topic);
        }
      } catch (err) {
        if (cancelled) return;
        setAccordionError('리포트를 불러올 수 없습니다.');
      } finally {
        if (!cancelled) setAccordionLoading(false);
      }
    };

    loadCompanyReports();
    return () => { cancelled = true; };
  }, [isAccordionMode, companyName]);

  /** ORDERED_TOPICS 순서에 따라 리포트 정렬 */
  const sortByTopicOrder = useCallback((reports) => {
    return [...reports].sort((a, b) => {
      const idxA = ORDERED_TOPICS.findIndex((t) => a.topic?.includes(t) || t.includes(a.topic));
      const idxB = ORDERED_TOPICS.findIndex((t) => b.topic?.includes(t) || t.includes(b.topic));
      const orderA = idxA >= 0 ? idxA : ORDERED_TOPICS.length;
      const orderB = idxB >= 0 ? idxB : ORDERED_TOPICS.length;
      return orderA - orderB;
    });
  }, []);

  // ─── Derived data ─────────────────────────────
  const citationDict = useMemo(() => (report ? buildCitationDict(report.references_data) : {}), [report]);
  const processedContent = useMemo(() => (report ? addInlineCitationLinks(report.report_content, report.references_data) : ''), [report]);
  const toc = useMemo(() => extractTocFromMarkdown(report?.report_content), [report]);

  const hasConversationLog = Boolean(
    report?.conversation_log &&
    (Array.isArray(report.conversation_log)
      ? report.conversation_log.length > 0
      : report.conversation_log.conversations?.length > 0)
  );
  const hasReferences = Object.keys(citationDict).length > 0;

  const currentStatus = (statusInfo?.status || '').toUpperCase();
  const progress = statusInfo?.progress ?? 0;
  const message = statusInfo?.message || '';
  const statusLabel = { PENDING: '대기 중', PROCESSING: '처리 중', COMPLETED: '완료', FAILED: '실패' };

  // ════════════════════════════════════════════════
  // Render: Accordion Mode (Company Overview)
  // ════════════════════════════════════════════════
  if (isAccordionMode) {
    if (accordionLoading) {
      return (
        <Container maxWidth="lg" sx={{ py: 4 }}>
          <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
            <CircularProgress size={50} />
            <Typography variant="body1" sx={{ mt: 2 }}>
              {companyName}의 분석 리포트를 불러오는 중...
            </Typography>
          </Paper>
        </Container>
      );
    }

    if (accordionError) {
      return (
        <Container maxWidth="lg" sx={{ py: 4 }}>
          <Paper elevation={3} sx={{ p: 4 }}>
            <Alert severity="error" sx={{ mb: 3 }}>{accordionError}</Alert>
            <Button variant="contained" startIcon={<ArrowBackIcon />} onClick={onBack}>
              돌아가기
            </Button>
          </Paper>
        </Container>
      );
    }

    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        {/* Header */}
        <Paper elevation={3} sx={{ p: 3, mb: 3, bgcolor: '#f5f5f5' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box
                sx={{
                  width: 56,
                  height: 56,
                  borderRadius: 2,
                  bgcolor: alpha('#1565c0', 0.1),
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <BusinessIcon sx={{ color: '#1565c0', fontSize: 32 }} />
              </Box>
              <Box>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {companyName}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  AI 심층 분석 리포트 ({accordionReports.length}개 주제)
                </Typography>
              </Box>
            </Box>
            <Button variant="outlined" startIcon={<ArrowBackIcon />} onClick={onBack}>
              돌아가기
            </Button>
          </Box>
        </Paper>

        {/* Accordion List */}
        {accordionReports.length === 0 ? (
          <Paper variant="outlined" sx={{ p: 4, textAlign: 'center', borderStyle: 'dashed', borderRadius: 3 }}>
            <ArticleIcon sx={{ fontSize: 48, color: 'grey.300', mb: 1 }} />
            <Typography variant="body1" color="text.secondary">
              이 기업에 대한 분석 리포트가 아직 없습니다.
            </Typography>
          </Paper>
        ) : (
          <Stack spacing={1}>
            {accordionReports.map((rpt) => {
              const rptCitationDict = buildCitationDict(rpt.references_data);
              const rptContent = addInlineCitationLinks(rpt.report_content, rpt.references_data);
              const topicIdx = ORDERED_TOPICS.findIndex((t) => rpt.topic?.includes(t) || t.includes(rpt.topic));
              const topicLabel = topicIdx >= 0 ? `T0${topicIdx + 1}` : '';

              return (
                <Accordion
                  key={rpt.id || rpt.job_id}
                  expanded={expandedTopic === rpt.topic}
                  onChange={(_, isExpanded) => setExpandedTopic(isExpanded ? rpt.topic : null)}
                  sx={{
                    borderRadius: '8px !important',
                    '&:before': { display: 'none' },
                    boxShadow: expandedTopic === rpt.topic ? 3 : 1,
                    transition: 'box-shadow 0.2s',
                  }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMoreIcon />}
                    sx={{
                      minHeight: 64,
                      '& .MuiAccordionSummary-content': { alignItems: 'center', gap: 2 },
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flex: 1 }}>
                      {topicLabel && (
                        <Chip
                          label={topicLabel}
                          size="small"
                          color="primary"
                          variant="outlined"
                          sx={{ fontWeight: 700, minWidth: 40 }}
                        />
                      )}
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                          {rpt.topic}
                        </Typography>
                        <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                          <Typography variant="caption" color="text.secondary">
                            {rpt.model_name}
                          </Typography>
                          {rpt.created_at && (
                            <Typography variant="caption" color="text.secondary">
                              | {new Date(rpt.created_at).toLocaleDateString('ko-KR')}
                            </Typography>
                          )}
                          {Object.keys(rptCitationDict).length > 0 && (
                            <Chip
                              label={`참고문헌 ${Object.keys(rptCitationDict).length}`}
                              size="small"
                              variant="outlined"
                              color="success"
                              sx={{ height: 20, fontSize: '0.7rem' }}
                            />
                          )}
                        </Stack>
                      </Box>
                      <Tooltip title="HTML 다운로드">
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            exportAsHtml(rpt, rptCitationDict);
                          }}
                        >
                          <DownloadIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails sx={{ pt: 0, pb: 3, px: 3 }}>
                    <Divider sx={{ mb: 2 }} />
                    <div className="markdown-container">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={markdownComponents}
                      >
                        {rptContent}
                      </ReactMarkdown>
                    </div>
                    {/* References (inline) */}
                    {Object.keys(rptCitationDict).length > 0 && (
                      <Box sx={{ mt: 3 }}>
                        <Divider sx={{ mb: 2 }} />
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                          참고 문헌
                        </Typography>
                        <ReferencesPanel citationDict={rptCitationDict} />
                      </Box>
                    )}
                  </AccordionDetails>
                </Accordion>
              );
            })}
          </Stack>
        )}

        {/* Footer */}
        <Box sx={{ mt: 4, display: 'flex', justifyContent: 'center' }}>
          <Button variant="contained" startIcon={<ArrowBackIcon />} onClick={onBack}>
            기업 분석으로 돌아가기
          </Button>
        </Box>
      </Container>
    );
  }

  // ════════════════════════════════════════════════
  // Render: Polling
  // ════════════════════════════════════════════════
  if (phase === 'polling') {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={60} />
            <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
              {currentStatus === 'PENDING' ? '⏳ 작업 대기 중...' : '📋 리포트 생성 중...'}
            </Typography>
            <Typography variant="body1" color="textSecondary">
              {message || 'AI가 데이터를 분석하고 있습니다. 잠시만 기다려주세요.'}
            </Typography>
            {progress > 0 && (
              <Box sx={{ width: '80%', mt: 1 }}>
                <LinearProgress variant="determinate" value={progress} sx={{ height: 10, borderRadius: 5 }} />
                <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>{progress}%</Typography>
              </Box>
            )}
            <Chip label={`상태: ${statusLabel[currentStatus] || currentStatus}`} color={currentStatus === 'PENDING' ? 'info' : 'warning'} variant="outlined" size="small" />
            <Typography variant="caption" color="textSecondary">(폴링: {pollingCount}회)</Typography>
            <Button variant="outlined" startIcon={<ArrowBackIcon />} onClick={onBack} sx={{ mt: 2 }}>
              대시보드로 돌아가기
            </Button>
          </Box>
        </Paper>
      </Container>
    );
  }

  // ════════════════════════════════════════════════
  // Render: Error
  // ════════════════════════════════════════════════
  if (phase === 'error') {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4 }}>
          <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>
          {statusInfo?.error_message && statusInfo.error_message !== error && (
            <Typography variant="body2" component="pre" sx={{ backgroundColor: '#f5f5f5', p: 2, borderRadius: 1, overflow: 'auto', mb: 2, fontSize: '0.85rem', whiteSpace: 'pre-wrap' }}>
              {statusInfo.error_message}
            </Typography>
          )}
          <Button variant="contained" startIcon={<ArrowBackIcon />} onClick={onBack}>
            대시보드로 돌아가기
          </Button>
        </Paper>
      </Container>
    );
  }

  // ════════════════════════════════════════════════
  // Render: Loading
  // ════════════════════════════════════════════════
  if (phase === 'loading') {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={50} />
            <Typography variant="body1">리포트를 불러오는 중...</Typography>
          </Box>
        </Paper>
      </Container>
    );
  }

  // ════════════════════════════════════════════════
  // Render: Report Done
  // ════════════════════════════════════════════════
  if (phase === 'done' && report) {
    return (
      <Box sx={{ display: 'flex', minHeight: '100vh' }}>
        {/* TOC 사이드바 */}
        {toc.length > 0 && (
          <TocSidebar toc={toc} open={tocOpen} onClose={() => setTocOpen(false)} />
        )}

        {/* 메인 콘텐츠 */}
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          <Container maxWidth="lg" sx={{ py: 3 }}>
            {/* 헤더 */}
            <Paper elevation={3} sx={{ p: 3, mb: 3, backgroundColor: '#f5f5f5' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {toc.length > 0 && (
                    <Tooltip title={tocOpen ? '목차 닫기' : '목차 열기'}>
                      <IconButton onClick={() => setTocOpen(!tocOpen)} size="small">
                        <MenuIcon />
                      </IconButton>
                    </Tooltip>
                  )}
                  <Box>
                    <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                      {report.company_name}
                    </Typography>
                    <Typography variant="body1" color="textSecondary">
                      주제: {report.topic}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap' }}>
                      <Chip label={`모델: ${report.model_name}`} variant="outlined" size="small" />
                      {report.created_at && (
                        <Chip label={`생성: ${new Date(report.created_at).toLocaleDateString('ko-KR')}`} variant="outlined" size="small" />
                      )}
                      {hasConversationLog && (
                        <Chip label="대화 로그 포함" color="info" variant="outlined" size="small" />
                      )}
                      {hasReferences && (
                        <Chip label={`참고문헌 ${Object.keys(citationDict).length}개`} color="success" variant="outlined" size="small" />
                      )}
                    </Box>
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                  <Tooltip title="HTML로 다운로드">
                    <IconButton onClick={() => exportAsHtml(report, citationDict)} color="primary">
                      <DownloadIcon />
                    </IconButton>
                  </Tooltip>
                  <Button variant="outlined" startIcon={<ArrowBackIcon />} onClick={onBack}>
                    돌아가기
                  </Button>
                </Box>
              </Box>
            </Paper>

            {/* 탭 네비게이션 */}
            <Paper elevation={2} sx={{ mb: 3 }}>
              <Tabs value={activeSection} onChange={(_, v) => setActiveSection(v)} variant="fullWidth">
                <Tab value="report" label="📄 리포트" />
                {hasReferences && <Tab value="references" label={`📚 참고문헌 (${Object.keys(citationDict).length})`} />}
                {hasConversationLog && <Tab value="conversation" label="💬 연구 대화 로그" />}
              </Tabs>
            </Paper>

            {/* ── 탭 콘텐츠: 리포트 ── */}
            {activeSection === 'report' && (
              <Paper elevation={2} sx={{ p: 4 }}>
                <div className="markdown-container">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents}
                  >
                    {processedContent}
                  </ReactMarkdown>
                </div>
              </Paper>
            )}

            {/* ── 탭 콘텐츠: 참고문헌 ── */}
            {activeSection === 'references' && hasReferences && (
              <Paper elevation={2} sx={{ p: 4 }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold', mb: 3 }}>
                  📚 참고 문헌
                </Typography>
                <ReferencesPanel citationDict={citationDict} />
              </Paper>
            )}

            {/* ── 탭 콘텐츠: 대화 로그 ── */}
            {activeSection === 'conversation' && hasConversationLog && (
              <Paper elevation={2} sx={{ p: 4 }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold', mb: 1 }}>
                  💬 연구 대화 로그
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                  STORM은 다양한 관점의 전문 페르소나가 주제를 깊이 있게 탐구한 대화를 기반으로 리포트를 생성합니다.
                </Typography>
                <ConversationLogViewer conversationLog={report.conversation_log} />
              </Paper>
            )}

            {/* 하단 액션 */}
            <Box sx={{ mt: 4, display: 'flex', gap: 2, justifyContent: 'center' }}>
              <Button variant="contained" startIcon={<ArrowBackIcon />} onClick={onBack}>
                새로운 리포트 생성
              </Button>
              <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportAsHtml(report, citationDict)}>
                HTML 다운로드
              </Button>
            </Box>
          </Container>
        </Box>
      </Box>
    );
  }

  return null;
};

export default ReportViewer;
