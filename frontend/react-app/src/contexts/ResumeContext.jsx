/**
 * ResumeContext - 자소서 작성 상태 관리
 *
 * 현재 작성 중인 자소서 세트/문항/초안 데이터를 관리한다.
 */
import React, { createContext, useContext, useReducer, useMemo, useCallback } from 'react';

const ResumeContext = createContext(null);

// ─── Initial State ────────────────────────────────────────
const initialState = {
    /** 현재 선택/생성된 자소서 세트 */
    currentQuestion: null,
    /** 현재 선택된 문항 */
    currentItem: null,
    /** 현재 문항의 초안 내용 (에디터 텍스트) */
    draftContent: '',
    /** 현재 문항의 저장된 Draft 객체 (서버 응답) */
    savedDraft: null,
    /** 가이드 결과 */
    guideResult: null,
    /** 첨삭 결과 */
    correctionResult: null,
    /** 로딩 상태 */
    loading: {
        guide: false,
        correction: false,
        draft: false,
    },
    /** 에러 메시지 */
    error: null,
};

// ─── Reducer ──────────────────────────────────────────────
const ACTIONS = {
    SET_QUESTION: 'SET_QUESTION',
    SET_ITEM: 'SET_ITEM',
    SET_DRAFT_CONTENT: 'SET_DRAFT_CONTENT',
    SET_SAVED_DRAFT: 'SET_SAVED_DRAFT',
    SET_GUIDE: 'SET_GUIDE',
    SET_CORRECTION: 'SET_CORRECTION',
    SET_LOADING: 'SET_LOADING',
    SET_ERROR: 'SET_ERROR',
    RESET: 'RESET',
};

const reducer = (state, action) => {
    switch (action.type) {
        case ACTIONS.SET_QUESTION:
            return { ...state, currentQuestion: action.payload, currentItem: null, draftContent: '', savedDraft: null, guideResult: null, correctionResult: null };
        case ACTIONS.SET_ITEM:
            return { ...state, currentItem: action.payload, draftContent: '', savedDraft: null, guideResult: null, correctionResult: null };
        case ACTIONS.SET_DRAFT_CONTENT:
            return { ...state, draftContent: action.payload };
        case ACTIONS.SET_SAVED_DRAFT:
            return { ...state, savedDraft: action.payload };
        case ACTIONS.SET_GUIDE:
            return { ...state, guideResult: action.payload };
        case ACTIONS.SET_CORRECTION:
            return { ...state, correctionResult: action.payload };
        case ACTIONS.SET_LOADING:
            return { ...state, loading: { ...state.loading, ...action.payload } };
        case ACTIONS.SET_ERROR:
            return { ...state, error: action.payload };
        case ACTIONS.RESET:
            return initialState;
        default:
            return state;
    }
};

// ─── Provider ─────────────────────────────────────────────
export const ResumeProvider = ({ children }) => {
    const [state, dispatch] = useReducer(reducer, initialState);

    const setQuestion = useCallback((q) => dispatch({ type: ACTIONS.SET_QUESTION, payload: q }), []);
    const setItem = useCallback((item) => dispatch({ type: ACTIONS.SET_ITEM, payload: item }), []);
    const setDraftContent = useCallback((text) => dispatch({ type: ACTIONS.SET_DRAFT_CONTENT, payload: text }), []);
    const setSavedDraft = useCallback((draft) => dispatch({ type: ACTIONS.SET_SAVED_DRAFT, payload: draft }), []);
    const setGuide = useCallback((guide) => dispatch({ type: ACTIONS.SET_GUIDE, payload: guide }), []);
    const setCorrection = useCallback((corr) => dispatch({ type: ACTIONS.SET_CORRECTION, payload: corr }), []);
    const setLoading = useCallback((obj) => dispatch({ type: ACTIONS.SET_LOADING, payload: obj }), []);
    const setError = useCallback((msg) => dispatch({ type: ACTIONS.SET_ERROR, payload: msg }), []);
    const reset = useCallback(() => dispatch({ type: ACTIONS.RESET }), []);

    const value = useMemo(
        () => ({
            ...state,
            setQuestion,
            setItem,
            setDraftContent,
            setSavedDraft,
            setGuide,
            setCorrection,
            setLoading,
            setError,
            reset,
        }),
        [state, setQuestion, setItem, setDraftContent, setSavedDraft, setGuide, setCorrection, setLoading, setError, reset],
    );

    return <ResumeContext.Provider value={value}>{children}</ResumeContext.Provider>;
};

export const useResume = () => {
    const ctx = useContext(ResumeContext);
    if (!ctx) throw new Error('useResume must be used within ResumeProvider');
    return ctx;
};
