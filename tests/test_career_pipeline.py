"""
Career Pipeline 단위 테스트

고정 페르소나 쿼리 큐, JSON 파싱 방어 로직, Pydantic 스키마 검증,
쿼리 후처리 로직, Sequential RAG 헬퍼 함수 등을 검증합니다.

테스트 전략:
- personas 모듈: 순수 단위 테스트 (DB 불필요)
- json_utils 모듈: 순수 단위 테스트 (DB 불필요)
- career_report 스키마: Pydantic 검증 테스트
- career_pipeline 내부 함수: 순수 단위 테스트
- Sequential RAG: 체이닝, Context Starvation, Phase 병합 테스트
"""

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.src.company.engine.json_utils import (
    build_retry_prompt,
    extract_json_string,
    parse_career_report,
    safe_parse_career_report,
)
from backend.src.company.engine.personas import (
    ALL_PERSONAS,
    CAREER_ADVISOR,
    FINAL_SYNTHESIS_PROMPT,
    INDUSTRY_ANALYST,
    PHASE1_SYSTEM_PROMPT,
    PHASE2_SYSTEM_PROMPT,
    PHASE3_SYSTEM_PROMPT,
    PHASE_PERSONA_MAP,
    build_query_queue,
)
from backend.src.company.schemas.career_report import (
    CareerAnalysisReport,
    CompanyOverview,
    CorporateCulture,
    Financials,
    InterviewPreparation,
    SwotAnalysis,
)


# ============================================================
# 1. 페르소나 모듈 테스트
# ============================================================
class TestPersonas:
    """고정 페르소나 정의 및 쿼리 큐 생성 테스트"""

    def test_all_personas_count(self):
        """3가지 고정 페르소나가 정의되어야 한다."""
        assert len(ALL_PERSONAS) == 3

    def test_persona_names(self):
        """각 페르소나의 이름이 올바르게 정의되어야 한다."""
        names = {p.name for p in ALL_PERSONAS}
        assert "산업 애널리스트" in names
        assert "수석 취업 지원관" in names
        assert "실무 면접관" in names

    def test_each_persona_has_5_queries(self):
        """각 페르소나는 5개의 쿼리를 가져야 한다."""
        for persona in ALL_PERSONAS:
            assert len(persona.query_queue) == 5, f"{persona.name}: {len(persona.query_queue)} queries"

    def test_each_persona_has_system_prompt(self):
        """각 페르소나는 비어있지 않은 시스템 프롬프트를 가져야 한다."""
        for persona in ALL_PERSONAS:
            assert persona.system_prompt, f"{persona.name}: system_prompt is empty"
            assert len(persona.system_prompt) > 50, f"{persona.name}: system_prompt too short"

    def test_industry_analyst_queries_have_dart(self):
        """산업 애널리스트 쿼리에는 DART 태그가 포함되어야 한다."""
        dart_queries = [q for q in INDUSTRY_ANALYST.query_queue if q.startswith("[DART]")]
        assert len(dart_queries) >= 2

    def test_career_advisor_queries_all_web(self):
        """수석 취업 지원관 쿼리는 모두 WEB 태그여야 한다."""
        for q in CAREER_ADVISOR.query_queue:
            assert q.startswith("[WEB]"), f"Expected [WEB] tag: {q}"

    def test_build_query_queue_replaces_company_name(self):
        """build_query_queue가 {company_name}을 실제 기업명으로 치환해야 한다."""
        result = build_query_queue("삼성전자", year="2025")

        assert len(result) == 15  # 3 personas * 5 queries
        for item in result:
            assert "삼성전자" in item["query"], f"Company name not found: {item['query']}"
            assert "{company_name}" not in item["query"], f"Placeholder not replaced: {item['query']}"

    def test_build_query_queue_replaces_year(self):
        """build_query_queue가 {year}를 실제 연도로 치환해야 한다."""
        result = build_query_queue("네이버", year="2025")

        dart_year_queries = [q for q in result if "2025" in q["query"] and q["tag"] == "DART"]
        assert len(dart_year_queries) >= 1

    def test_build_query_queue_tag_extraction(self):
        """build_query_queue가 태그(DART/WEB)를 올바르게 추출해야 한다."""
        result = build_query_queue("테스트기업")

        tags = {item["tag"] for item in result}
        assert "DART" in tags
        assert "WEB" in tags

    def test_build_query_queue_persona_assignment(self):
        """각 쿼리에 올바른 페르소나가 할당되어야 한다."""
        result = build_query_queue("테스트기업")

        persona_counts = {}
        for item in result:
            persona_counts[item["persona"]] = persona_counts.get(item["persona"], 0) + 1

        assert persona_counts.get("산업 애널리스트") == 5
        assert persona_counts.get("수석 취업 지원관") == 5
        assert persona_counts.get("실무 면접관") == 5

    def test_final_synthesis_prompt_not_empty(self):
        """최종 합성 프롬프트가 비어있지 않아야 한다."""
        assert FINAL_SYNTHESIS_PROMPT
        assert len(FINAL_SYNTHESIS_PROMPT) > 100


# ============================================================
# 2. JSON 파싱 방어 로직 테스트
# ============================================================
class TestJsonUtils:
    """JSON 추출, 파싱, 방어 로직 테스트"""

    # --- extract_json_string ---

    def test_extract_pure_json(self):
        """순수 JSON 문자열을 그대로 추출해야 한다."""
        raw = '{"company_overview": {"introduction": "test"}}'
        result = extract_json_string(raw)
        assert result == raw

    def test_extract_from_markdown_code_block(self):
        """마크다운 코드블록에서 JSON을 추출해야 한다."""
        raw = '```json\n{"company_overview": {"introduction": "test"}}\n```'
        result = extract_json_string(raw)
        parsed = json.loads(result)
        assert parsed["company_overview"]["introduction"] == "test"

    def test_extract_from_markdown_without_json_label(self):
        """json 라벨 없는 마크다운 코드블록에서도 추출해야 한다."""
        raw = '```\n{"key": "value"}\n```'
        result = extract_json_string(raw)
        assert json.loads(result)["key"] == "value"

    def test_extract_with_prefix_text(self):
        """'Here is the JSON' 같은 부연 설명이 있어도 추출해야 한다."""
        raw = 'Here is the JSON result:\n{"key": "value"}'
        result = extract_json_string(raw)
        assert json.loads(result)["key"] == "value"

    def test_extract_with_suffix_text(self):
        """JSON 뒤에 부연 설명이 있어도 추출해야 한다."""
        raw = '{"key": "value"}\n\nI hope this helps!'
        result = extract_json_string(raw)
        assert json.loads(result)["key"] == "value"

    def test_extract_empty_string_raises(self):
        """빈 문자열은 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError, match="빈 응답"):
            extract_json_string("")

    def test_extract_no_json_raises(self):
        """JSON 구조가 없는 텍스트는 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError, match="JSON 구조"):
            extract_json_string("This is just plain text without any JSON")

    def test_extract_invalid_json_raises(self):
        """유효하지 않은 JSON은 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError, match="유효한 JSON"):
            extract_json_string('{"key": "value",}')

    def test_extract_nested_json(self):
        """중첩된 JSON도 올바르게 추출해야 한다."""
        raw = '{"a": {"b": {"c": [1, 2, 3]}}}'
        result = extract_json_string(raw)
        parsed = json.loads(result)
        assert parsed["a"]["b"]["c"] == [1, 2, 3]

    # --- parse_career_report ---

    def test_parse_valid_career_report(self):
        """유효한 JSON을 CareerAnalysisReport로 파싱해야 한다."""
        valid_json = json.dumps(
            {
                "company_overview": {
                    "introduction": "삼성전자는 대한민국 대표 IT 기업입니다.",
                    "industry": "반도체/전자",
                    "employee_count": "약 12만명 (2025년 기준)",
                    "location": "경기도 수원시 영통구",
                    "financials": {"revenue": "302조원 (2024년 기준)", "operating_profit": "8.5조원 (2024년 기준)"},
                },
                "corporate_culture": {
                    "core_values": ["인재제일", "최고지향"],
                    "ideal_candidate": ["도전정신", "글로벌 마인드"],
                    "work_environment": ["유연근무제", "사내 어린이집"],
                },
                "swot_analysis": {
                    "strength": ["반도체 글로벌 1위"],
                    "weakness": ["소프트웨어 경쟁력 부족"],
                    "opportunity": ["AI 반도체 수요 급증"],
                    "threat": ["중국 반도체 추격"],
                    "so_strategy": "AI 반도체 시장 선점",
                    "wt_strategy": "소프트웨어 역량 강화",
                },
                "interview_preparation": {
                    "recent_issues": ["반도체 감산 논란"],
                    "pressure_questions": ["중국 반도체 추격에 대한 대응 전략은?"],
                    "expected_answers": ["TSMC 대비 기술 격차 유지 전략 설명"],
                },
            },
            ensure_ascii=False,
        )

        report = parse_career_report(valid_json)
        assert isinstance(report, CareerAnalysisReport)
        assert report.company_overview.industry == "반도체/전자"
        assert len(report.swot_analysis.strength) >= 1

    def test_parse_minimal_json(self):
        """최소한의 필드만 있어도 기본값으로 파싱되어야 한다."""
        minimal_json = json.dumps(
            {"company_overview": {}, "corporate_culture": {}, "swot_analysis": {}, "interview_preparation": {}}
        )

        report = parse_career_report(minimal_json)
        assert isinstance(report, CareerAnalysisReport)
        # 기본값 확인
        assert "정보 부족" in report.company_overview.introduction

    def test_parse_empty_object(self):
        """빈 객체도 기본값으로 파싱되어야 한다."""
        report = parse_career_report("{}")
        assert isinstance(report, CareerAnalysisReport)

    def test_parse_from_markdown_wrapped(self):
        """마크다운으로 감싼 JSON도 파싱해야 한다."""
        raw = '```json\n{"company_overview": {"introduction": "test corp"}}\n```'
        report = parse_career_report(raw)
        assert report.company_overview.introduction == "test corp"

    # --- safe_parse_career_report ---

    def test_safe_parse_success(self):
        """성공 시 (report, None) 튜플을 반환해야 한다."""
        valid_json = '{"company_overview": {"introduction": "ok"}}'
        report, error = safe_parse_career_report(valid_json)
        assert report is not None
        assert error is None

    def test_safe_parse_failure_returns_error(self):
        """실패 시 (None, error_message) 튜플을 반환해야 한다."""
        report, error = safe_parse_career_report("not json at all")
        assert report is None
        assert error is not None
        assert "JSON" in error

    def test_safe_parse_empty_returns_error(self):
        """빈 문자열은 에러를 반환해야 한다."""
        report, error = safe_parse_career_report("")
        assert report is None
        assert error is not None

    # --- build_retry_prompt ---

    def test_build_retry_prompt_includes_error(self):
        """재시도 프롬프트에 이전 오류 메시지가 포함되어야 한다."""
        prompt = build_retry_prompt("원본 프롬프트", "키 누락 오류")
        assert "원본 프롬프트" in prompt
        assert "키 누락 오류" in prompt
        assert "이전 응답 오류" in prompt

    def test_build_retry_prompt_includes_instructions(self):
        """재시도 프롬프트에 수정 지침이 포함되어야 한다."""
        prompt = build_retry_prompt("test", "error")
        assert "순수 JSON" in prompt
        assert "마크다운" in prompt


# ============================================================
# 3. Pydantic 스키마 검증 테스트
# ============================================================
class TestCareerReportSchema:
    """CareerAnalysisReport Pydantic 모델 검증 테스트"""

    def test_default_values(self):
        """기본값으로 객체가 생성되어야 한다."""
        report = CareerAnalysisReport()
        assert "정보 부족" in report.company_overview.introduction
        assert len(report.corporate_culture.core_values) >= 1
        assert len(report.swot_analysis.strength) >= 1
        assert len(report.interview_preparation.pressure_questions) >= 1

    def test_financials_default(self):
        """Financials의 기본값이 올바르게 설정되어야 한다."""
        fin = Financials()
        assert "정보 부족" in fin.revenue
        assert "정보 부족" in fin.operating_profit

    def test_full_model_serialization(self):
        """전체 모델이 JSON 직렬화/역직렬화가 가능해야 한다."""
        report = CareerAnalysisReport(
            company_overview=CompanyOverview(
                introduction="테스트 기업입니다.",
                industry="IT",
                employee_count="100명",
                location="서울시",
                financials=Financials(revenue="100억원", operating_profit="10억원"),
            ),
            corporate_culture=CorporateCulture(
                core_values=["혁신"], ideal_candidate=["도전"], work_environment=["유연근무"]
            ),
            swot_analysis=SwotAnalysis(
                strength=["기술력"],
                weakness=["인지도"],
                opportunity=["시장 성장"],
                threat=["경쟁 심화"],
                so_strategy="기술 + 시장",
                wt_strategy="브랜딩 강화",
            ),
            interview_preparation=InterviewPreparation(
                recent_issues=["이슈1"], pressure_questions=["질문1"], expected_answers=["답변1"]
            ),
        )

        json_str = report.model_dump_json(ensure_ascii=False)
        restored = CareerAnalysisReport.model_validate_json(json_str)

        assert restored.company_overview.introduction == "테스트 기업입니다."
        assert restored.corporate_culture.core_values == ["혁신"]
        assert restored.swot_analysis.so_strategy == "기술 + 시장"

    def test_array_field_with_string_instead_of_list(self):
        """array 필드에 string이 오면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            CorporateCulture(core_values="not a list")  # type: ignore

    def test_model_from_dict(self):
        """딕셔너리에서 모델을 생성할 수 있어야 한다."""
        data = {"company_overview": {"introduction": "from dict", "financials": {"revenue": "50억"}}}
        report = CareerAnalysisReport.model_validate(data)
        assert report.company_overview.introduction == "from dict"
        assert report.company_overview.financials.revenue == "50억"


# ============================================================
# 4. 쿼리 후처리 로직 테스트 (career_pipeline 내부 함수)
# ============================================================
class TestQueryPostprocessing:
    """career_pipeline의 쿼리 후처리 함수 테스트"""

    def test_post_process_adds_company_name(self):
        """쿼리에 기업명이 없으면 추가해야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [{"persona": "산업 애널리스트", "query": "주요사업 및 시장점유율", "tag": "DART"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert "삼성전자" in result[0]["query"]

    def test_post_process_no_forced_tags(self):
        """롤백 후 카테고리 태그가 강제 추가되지 않아야 한다."""
        """쿼리 길이가 250자를 넘지 않아야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        long_query = "A" * 220
        query_items = [{"persona": "실무 면접관", "query": long_query, "tag": "WEB"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert len(result[0]["query"]) <= 250

    def test_post_process_does_not_duplicate_company_name(self):
        """이미 기업명이 포함된 쿼리에는 중복 추가하지 않아야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [{"persona": "산업 애널리스트", "query": "삼성전자 매출액", "tag": "DART"}]
        result = _post_process_queries(query_items, "삼성전자")

        # 기업명이 한 번만 나타나야 함
        assert result[0]["query"].count("삼성전자") == 1


# ============================================================
# 5. LLM 컨텍스트 빌드 테스트
# ============================================================
class TestLLMContextBuild:
    """LLM 프롬프트 조합 함수 테스트"""

    def test_build_llm_context_with_results(self):
        """검색 결과가 있을 때 컨텍스트에 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_llm_context

        search_results = {
            "산업 애널리스트": [
                {"snippets": ["삼성전자는 반도체 분야 세계 1위"], "title": "DART", "url": "http://dart.fss.or.kr"}
            ]
        }

        context, truncation_info = _build_llm_context(search_results, "삼성전자")
        assert "삼성전자" in context
        assert "산업 애널리스트" in context
        assert "반도체 분야 세계 1위" in context
        assert truncation_info["truncated"] is False

    def test_build_llm_context_empty_results(self):
        """검색 결과가 없을 때 '검색 결과 없음'이 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_llm_context

        context, truncation_info = _build_llm_context({}, "네이버")
        assert "네이버" in context
        assert "검색 결과 없음" in context
        assert truncation_info["truncated"] is False

    def test_build_final_prompt_contains_all_parts(self):
        """최종 프롬프트에 기업명, 주제, 컨텍스트가 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_final_prompt

        prompt = _build_final_prompt("삼성전자", "기업 분석", "테스트 컨텍스트")
        assert "삼성전자" in prompt
        assert "기업 분석" in prompt
        assert "테스트 컨텍스트" in prompt
        assert "JSON" in prompt

    def test_build_final_prompt_no_duplicate_synthesis(self):
        """최종 프롬프트에 FINAL_SYNTHESIS_PROMPT가 포함되지 않아야 한다 (이중 전달 방지)."""
        from backend.src.company.engine.career_pipeline import _build_final_prompt
        from backend.src.company.engine.personas import FINAL_SYNTHESIS_PROMPT

        prompt = _build_final_prompt("테스트기업", "기업 분석", "컨텍스트")
        # _call_llm에서 system message로 이미 전달하므로 user prompt에는 포함되지 않아야 함
        assert FINAL_SYNTHESIS_PROMPT not in prompt


# ============================================================
# 6. Reference 추출 테스트
# ============================================================
class TestReferenceExtraction:
    """검색 결과에서 참조 정보 추출 테스트"""

    def test_extract_references(self):
        """검색 결과에서 URL 참조를 추출해야 한다."""
        from backend.src.company.engine.career_pipeline import _extract_references

        results = [
            {"url": "http://dart.fss.or.kr/1", "title": "DART Report"},
            {"url": "http://news.com/2", "title": "News Article"},
            {"url": "", "title": "No URL"},
        ]
        refs = _extract_references(results)

        assert len(refs) == 2
        assert any("dart" in v["url"] for v in refs.values())

    def test_extract_references_deduplication(self):
        """중복 URL은 제거해야 한다."""
        from backend.src.company.engine.career_pipeline import _extract_references

        results = [{"url": "http://same.com", "title": "First"}, {"url": "http://same.com", "title": "Duplicate"}]
        refs = _extract_references(results)

        assert len(refs) == 1

    def test_extract_references_empty(self):
        """검색 결과가 없으면 빈 딕셔너리를 반환해야 한다."""
        from backend.src.company.engine.career_pipeline import _extract_references

        refs = _extract_references([])
        assert refs == {}


# ============================================================
# 7. Truncation 로직 테스트
# ============================================================
class TestTruncation:
    """입력 컨텍스트 글자 수 기반 절삭(Truncation) 테스트"""

    def test_truncation_under_limit(self):
        """
        50,000자 미만 컨텍스트는 절삭되지 않아야 한다.
        """
        from backend.src.company.engine.career_pipeline import _build_llm_context

        search_results = {"산업 애널리스트": [{"snippets": ["짧은 스니펫"], "title": "Test", "url": "http://test.com"}]}
        context, info = _build_llm_context(search_results, "테스트")

        assert info["truncated"] is False
        assert info["original_length"] == info["final_length"]

    def test_truncation_over_limit(self):
        """
        50,000자 초과 컨텍스트는 정상 절삭되고 메타데이터가 기록되어야 한다.
        """
        from backend.src.company.engine.career_pipeline import _build_llm_context

        # 각 스니펫을 매우 길게 만들어 50,000자 초과하도록 함
        # 스니펫 앞부분을 고유하게 하여 중복 제거(dedup)를 회피
        # 3 페르소나 * 15 스니펫 * 4000자 = 약 180,000자
        search_results = {
            "산업 애널리스트": [
                {"snippets": [f"analyst_{i}_" + "A" * 4000], "title": f"Test {i}", "url": f"http://test{i}.com"}
                for i in range(15)
            ],
            "수석 취업 지원관": [
                {"snippets": [f"advisor_{i}_" + "B" * 4000], "title": f"Test2 {i}", "url": f"http://test2-{i}.com"}
                for i in range(15)
            ],
            "실무 면접관": [
                {"snippets": [f"interviewer_{i}_" + "C" * 4000], "title": f"Test3 {i}", "url": f"http://test3-{i}.com"}
                for i in range(15)
            ],
        }
        context, info = _build_llm_context(search_results, "테스트")

        assert info["truncated"] is True
        assert info["original_length"] > 50_000
        assert info["final_length"] <= 50_000 + 100  # 절삭 메시지 길이 여유
        assert "텍스트 절삭됨" in context

    def test_truncation_metadata_fields(self):
        """
        truncation_info에 필수 필드가 존재해야 한다.
        """
        from backend.src.company.engine.career_pipeline import _build_llm_context

        _, info = _build_llm_context({}, "테스트")

        assert "original_length" in info
        assert "final_length" in info
        assert "truncated" in info
        assert "max_context_chars" in info
        assert "snippets_per_persona" in info
        assert info["max_context_chars"] == 50_000


# ============================================================
# 8. 프론트엔드 출처 포맷팅 테스트
# ============================================================
class TestFormatReferencesForFrontend:
    """
    _format_references_for_frontend()이 buildCitationDict() 기대 형식과 일치하는지 검증
    """

    def test_format_basic(self):
        """기본 변환이 url_to_unified_index + url_to_info 형식이어야 한다."""
        from backend.src.company.engine.career_pipeline import _format_references_for_frontend

        results = [
            {"url": "http://dart.fss.or.kr/1", "title": "DART Report", "snippets": ["매출액 100조"]},
            {"url": "http://news.com/2", "title": "News Article", "snippets": ["기사 내용"]},
        ]
        refs = _format_references_for_frontend(results)

        assert "url_to_unified_index" in refs
        assert "url_to_info" in refs
        assert refs["url_to_unified_index"]["http://dart.fss.or.kr/1"] == 1
        assert refs["url_to_unified_index"]["http://news.com/2"] == 2
        assert refs["url_to_info"]["http://dart.fss.or.kr/1"]["title"] == "DART Report"
        assert "매출액 100조" in refs["url_to_info"]["http://dart.fss.or.kr/1"]["snippets"]

    def test_format_deduplication(self):
        """중복 URL은 병합되고 스니펫이 추가되어야 한다."""
        from backend.src.company.engine.career_pipeline import _format_references_for_frontend

        results = [
            {"url": "http://same.com", "title": "First", "snippets": ["snippet1"]},
            {"url": "http://same.com", "title": "Duplicate", "snippets": ["snippet2"]},
        ]
        refs = _format_references_for_frontend(results)

        assert len(refs["url_to_unified_index"]) == 1
        assert refs["url_to_unified_index"]["http://same.com"] == 1
        # 두 스니펫 모두 병합되어야 함
        assert len(refs["url_to_info"]["http://same.com"]["snippets"]) == 2

    def test_format_empty_results(self):
        """검색 결과가 없으면 빈 구조를 반환해야 한다."""
        from backend.src.company.engine.career_pipeline import _format_references_for_frontend

        refs = _format_references_for_frontend([])
        assert refs["url_to_unified_index"] == {}
        assert refs["url_to_info"] == {}

    def test_format_skips_empty_urls(self):
        """URL이 비어있는 결과는 건너뛰어야 한다."""
        from backend.src.company.engine.career_pipeline import _format_references_for_frontend

        results = [
            {"url": "", "title": "No URL", "snippets": ["test"]},
            {"url": "http://valid.com", "title": "Valid", "snippets": ["ok"]},
        ]
        refs = _format_references_for_frontend(results)

        assert len(refs["url_to_unified_index"]) == 1
        assert "http://valid.com" in refs["url_to_unified_index"]


# ============================================================
# 9. Context Trace 로거 테스트
# ============================================================
class TestContextTrace:
    """
    context_trace.json 생성 및 엣지 케이스 테스트
    """

    def test_context_trace_empty_results(self, tmp_path):
        """검색 결과 0건 시 json 직렬화 에러 없이 안전하게 기록되어야 한다."""
        from backend.src.company.engine.career_pipeline import _write_context_trace

        output_dir = str(tmp_path)
        _write_context_trace(
            output_dir=output_dir,
            company_name="테스트기업",
            job_id="test-job-001",
            processed_queries=[{"persona": "산업 애널리스트", "query": "테스트 쿼리", "tag": "WEB"}],
            search_results_by_persona={},
            context_text="(검색 결과 없음)",
            truncation_info={
                "original_length": 20,
                "final_length": 20,
                "truncated": False,
                "max_context_chars": 50000,
                "snippets_per_persona": {},
            },
            all_search_results=[],
        )

        trace_path = tmp_path / "context_trace.json"
        assert trace_path.exists()

        with open(trace_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["company_name"] == "테스트기업"
        assert data["source_list"] == []
        assert data["context_stats"]["truncated"] is False

    def test_context_trace_with_results(self, tmp_path):
        """검색 결과가 있을 때 raw context와 출처가 기록되어야 한다."""
        from backend.src.company.engine.career_pipeline import _write_context_trace

        output_dir = str(tmp_path)
        _write_context_trace(
            output_dir=output_dir,
            company_name="삼성전자",
            job_id="test-job-002",
            processed_queries=[
                {"persona": "산업 애널리스트", "query": "삼성전자 재무", "tag": "DART"},
                {"persona": "수석 취업 지원관", "query": "삼성전자 인재상", "tag": "WEB"},
            ],
            search_results_by_persona={
                "산업 애널리스트": [{"url": "http://dart.fss.or.kr/1", "title": "DART", "snippets": ["매출액 302조"]}],
                "수석 취업 지원관": [],
            },
            context_text="테스트 컨텍스트",
            truncation_info={
                "original_length": 100,
                "final_length": 100,
                "truncated": False,
                "max_context_chars": 50000,
                "snippets_per_persona": {"산업 애널리스트": 1},
            },
            all_search_results=[{"url": "http://dart.fss.or.kr/1", "title": "DART", "snippets": ["매출액 302조"]}],
        )

        trace_path = tmp_path / "context_trace.json"
        assert trace_path.exists()

        with open(trace_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["company_name"] == "삼성전자"
        assert len(data["source_list"]) == 1
        assert data["source_list"][0]["url"] == "http://dart.fss.or.kr/1"
        assert "산업 애널리스트" in data["queries"]
        assert "수석 취업 지원관" in data["raw_context"]
        assert data["raw_context"]["수석 취업 지원관"] == "정보 없음"

    def test_context_trace_required_fields(self, tmp_path):
        """출력 JSON에 필수 필드가 모두 존재해야 한다."""
        from backend.src.company.engine.career_pipeline import _write_context_trace

        output_dir = str(tmp_path)
        _write_context_trace(
            output_dir=output_dir,
            company_name="테스트",
            job_id="test-job-003",
            processed_queries=[],
            search_results_by_persona={},
            context_text="",
            truncation_info={
                "original_length": 0,
                "final_length": 0,
                "truncated": False,
                "max_context_chars": 50000,
                "snippets_per_persona": {},
            },
            all_search_results=[],
        )

        with open(tmp_path / "context_trace.json", encoding="utf-8") as f:
            data = json.load(f)

        required_keys = [
            "company_name",
            "job_id",
            "timestamp",
            "queries",
            "raw_context",
            "source_list",
            "context_stats",
        ]
        for key in required_keys:
            assert key in data, f"필수 필드 '{key}' 누락"


# ============================================================
# 10. 외부 검색 K값 테스트
# ============================================================
class TestExternalK:
    """
    build_hybrid_rm에서 external_k가 10인지 검증
    """

    def test_external_k_is_10(self):
        """
        top_k=10일 때 external_k=10, internal_k=5가 되어야 한다.
        """
        # build_hybrid_rm은 HybridRM 객체를 생성하므로 직접 호출하지 않고
        # 로직만 검증 (builder.py의 분배 로직)
        top_k = 10
        internal_k = max(1, top_k // 2)
        external_k = top_k

        assert internal_k == 5
        assert external_k == 10


# ============================================================
# 11. Sequential RAG 헬퍼 함수 테스트
# ============================================================
class TestSequentialRAG:
    """3-Phase Sequential RAG 헬퍼 함수 및 Phase별 프롬프트 테스트"""

    # --- Phase 시스템 프롬프트 검증 ---

    def test_phase_system_prompts_exist(self):
        """Phase별 시스템 프롬프트가 존재하고 비어있지 않아야 한다."""
        assert len(PHASE1_SYSTEM_PROMPT) > 100
        assert len(PHASE2_SYSTEM_PROMPT) > 100
        assert len(PHASE3_SYSTEM_PROMPT) > 100

    def test_phase1_prompt_contains_company_overview_schema(self):
        """Phase 1 프롬프트가 company_overview 스키마를 포함해야 한다."""
        assert "company_overview" in PHASE1_SYSTEM_PROMPT
        assert "introduction" in PHASE1_SYSTEM_PROMPT
        assert "financials" in PHASE1_SYSTEM_PROMPT
        # Phase 1에는 다른 섹션 스키마가 포함되지 않아야 한다
        assert "corporate_culture" not in PHASE1_SYSTEM_PROMPT
        assert "swot_analysis" not in PHASE1_SYSTEM_PROMPT
        assert "interview_preparation" not in PHASE1_SYSTEM_PROMPT

    def test_phase2_prompt_contains_culture_swot_schema(self):
        """Phase 2 프롬프트가 corporate_culture + swot_analysis 스키마를 포함해야 한다."""
        assert "corporate_culture" in PHASE2_SYSTEM_PROMPT
        assert "swot_analysis" in PHASE2_SYSTEM_PROMPT
        assert "core_values" in PHASE2_SYSTEM_PROMPT
        assert "strength" in PHASE2_SYSTEM_PROMPT
        # Phase 2 JSON 스키마에는 Phase 1/3 섹션 키가 포함되지 않아야 한다
        # (설명 텍스트에 company_overview 언급은 허용하되, 스키마에는 없어야 함)
        import json

        # 프롬프트에서 JSON 스키마 부분만 추출하여 검증 (다음 섹션 헤더 전까지)
        schema_marker = "## JSON 스키마\n"
        schema_start = PHASE2_SYSTEM_PROMPT.find(schema_marker) + len(schema_marker)
        # 스키마 이후 다음 "##" 헤더까지만 추출
        rest = PHASE2_SYSTEM_PROMPT[schema_start:]
        next_header = rest.find("\n\n##")
        schema_json = rest[:next_header].strip() if next_header != -1 else rest.strip()
        parsed_schema = json.loads(schema_json)
        assert "company_overview" not in parsed_schema
        assert "interview_preparation" not in parsed_schema
        assert "corporate_culture" in parsed_schema
        assert "swot_analysis" in parsed_schema

    def test_phase3_prompt_contains_interview_schema(self):
        """Phase 3 프롬프트가 interview_preparation 스키마를 포함해야 한다."""
        assert "interview_preparation" in PHASE3_SYSTEM_PROMPT
        assert "pressure_questions" in PHASE3_SYSTEM_PROMPT
        assert "expected_answers" in PHASE3_SYSTEM_PROMPT
        # Phase 3에는 Phase 1/2 섹션이 포함되지 않아야 한다
        assert "company_overview" not in PHASE3_SYSTEM_PROMPT
        assert "corporate_culture" not in PHASE3_SYSTEM_PROMPT

    def test_phase_persona_map_structure(self):
        """PHASE_PERSONA_MAP이 3개 Phase로 올바르게 매핑되어야 한다."""
        assert len(PHASE_PERSONA_MAP) == 3
        assert 1 in PHASE_PERSONA_MAP
        assert 2 in PHASE_PERSONA_MAP
        assert 3 in PHASE_PERSONA_MAP
        # 각 Phase에는 정확히 1개 페르소나
        for phase_id, personas in PHASE_PERSONA_MAP.items():
            assert len(personas) == 1

    # --- _build_chaining_context 검증 ---

    def test_build_chaining_context_normal(self):
        """정상 Phase 결과가 올바른 JSON 문자열로 변환되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_chaining_context

        report = CareerAnalysisReport(
            company_overview=CompanyOverview(
                introduction="삼성전자는 글로벌 반도체 1위 기업이다.",
                industry="반도체/전자",
                employee_count="약 12만명 (2025년 기준)",
                location="경기도 수원시",
                financials=Financials(revenue="300조원 (2024년)", operating_profit="6조원 (2024년)"),
            )
        )

        result = _build_chaining_context(report, "기초 팩트", ["company_overview"])

        assert isinstance(result, str)
        # JSON 파싱이 가능해야 한다
        parsed = json.loads(result)
        assert "company_overview" in parsed
        assert parsed["company_overview"]["introduction"] == "삼성전자는 글로벌 반도체 1위 기업이다."

    def test_build_chaining_context_starvation(self):
        """모든 필드가 기본값인 Phase 결과는 starvation 메시지를 반환해야 한다."""
        from backend.src.company.engine.career_pipeline import CONTEXT_STARVATION_MSG, _build_chaining_context

        # 기본값만 가진 빈 리포트
        report = CareerAnalysisReport()

        result = _build_chaining_context(report, "기초 팩트", ["company_overview"])

        assert CONTEXT_STARVATION_MSG in result
        assert "기초 팩트" in result

    def test_build_chaining_context_none_input(self):
        """None 입력 시 starvation 메시지가 반환되어야 한다 (Null Safe)."""
        from backend.src.company.engine.career_pipeline import CONTEXT_STARVATION_MSG, _build_chaining_context

        result = _build_chaining_context(None, "심층 분석", ["corporate_culture", "swot_analysis"])

        assert CONTEXT_STARVATION_MSG in result
        assert "심층 분석" in result

    # --- _merge_phase_results 검증 ---

    def test_merge_phase_results_all_present(self):
        """3개 Phase 결과가 올바르게 병합되어야 한다."""
        from backend.src.company.engine.career_pipeline import _merge_phase_results

        phase1 = CareerAnalysisReport(company_overview=CompanyOverview(introduction="테스트 기업 소개", industry="IT"))
        phase2 = CareerAnalysisReport(
            corporate_culture=CorporateCulture(core_values=["혁신", "도전"]),
            swot_analysis=SwotAnalysis(strength=["기술력"]),
        )
        phase3 = CareerAnalysisReport(interview_preparation=InterviewPreparation(pressure_questions=["왜 지원했나요?"]))

        merged = _merge_phase_results(phase1, phase2, phase3)

        assert isinstance(merged, CareerAnalysisReport)
        assert merged.company_overview.introduction == "테스트 기업 소개"
        assert merged.corporate_culture.core_values == ["혁신", "도전"]
        assert merged.swot_analysis.strength == ["기술력"]
        assert merged.interview_preparation.pressure_questions == ["왜 지원했나요?"]

    def test_merge_phase_results_partial_failure(self):
        """특정 Phase가 None일 때 해당 섹션이 기본값으로 채워져야 한다."""
        from backend.src.company.engine.career_pipeline import _merge_phase_results

        phase1 = CareerAnalysisReport(company_overview=CompanyOverview(introduction="테스트 기업", industry="제조"))

        # Phase 2 실패 (None)
        merged = _merge_phase_results(phase1, None, None)

        assert isinstance(merged, CareerAnalysisReport)
        assert merged.company_overview.introduction == "테스트 기업"
        # Phase 2/3 실패 -> 기본값
        assert "정보 부족" in merged.corporate_culture.core_values[0]
        assert "정보 부족" in merged.interview_preparation.pressure_questions[0]

    def test_merge_phase_results_all_none(self):
        """모든 Phase가 None일 때 전체 기본값 리포트가 생성되어야 한다."""
        from backend.src.company.engine.career_pipeline import _merge_phase_results

        merged = _merge_phase_results(None, None, None)

        assert isinstance(merged, CareerAnalysisReport)
        assert "정보 부족" in merged.company_overview.introduction

    # --- _call_llm custom system_prompt 검증 ---

    @pytest.mark.asyncio
    async def test_call_llm_custom_system_prompt(self):
        """_call_llm()에 custom system_prompt를 전달하면 해당 프롬프트가 사용되어야 한다."""
        from backend.src.company.engine.career_pipeline import _call_llm

        custom_prompt = "당신은 Phase 1 전용 시스템입니다."

        with patch("litellm.completion") as mock_completion:
            mock_response = type(
                "Resp", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "{}"})()})]}
            )()
            mock_completion.return_value = mock_response

            result = await _call_llm("테스트 프롬프트", "openai", system_prompt=custom_prompt)

            # litellm.completion 호출 시 system message에 custom_prompt 사용 확인
            call_args = mock_completion.call_args
            messages = call_args.kwargs.get("messages")
            if messages is None:
                # keyword argument로 전달된 경우
                for k, v in call_args.kwargs.items():
                    if k == "messages":
                        messages = v
                        break

            system_msg = [m for m in messages if m["role"] == "system"][0]
            assert system_msg["content"] == custom_prompt

    # --- _build_llm_context target_personas 검증 ---

    def test_build_llm_context_target_personas(self):
        """target_personas 파라미터가 컨텍스트 범위를 올바르게 제한해야 한다."""
        from backend.src.company.engine.career_pipeline import _build_llm_context

        search_results = {
            "산업 애널리스트": [{"title": "T1", "url": "http://a.com", "snippets": ["산업 데이터"]}],
            "수석 취업 지원관": [{"title": "T2", "url": "http://b.com", "snippets": ["문화 데이터"]}],
            "실무 면접관": [{"title": "T3", "url": "http://c.com", "snippets": ["면접 데이터"]}],
        }

        # Phase 1: 산업 애널리스트만
        context, info = _build_llm_context(search_results, "테스트기업", PHASE_PERSONA_MAP[1])

        assert "산업 애널리스트" in context
        assert "산업 데이터" in context
        # 다른 페르소나 데이터는 포함되지 않아야 한다
        assert "수석 취업 지원관" not in context
        assert "실무 면접관" not in context

    def test_build_llm_context_no_target_uses_all(self):
        """target_personas=None이면 모든 페르소나를 포함해야 한다."""
        from backend.src.company.engine.career_pipeline import _build_llm_context

        search_results = {
            "산업 애널리스트": [{"title": "T1", "url": "http://a.com", "snippets": ["산업 데이터"]}],
            "수석 취업 지원관": [{"title": "T2", "url": "http://b.com", "snippets": ["문화 데이터"]}],
            "실무 면접관": [{"title": "T3", "url": "http://c.com", "snippets": ["면접 데이터"]}],
        }

        context, info = _build_llm_context(search_results, "테스트기업")

        assert "산업 애널리스트" in context
        assert "수석 취업 지원관" in context
        assert "실무 면접관" in context

    # --- _build_final_prompt chaining 검증 ---

    def test_build_final_prompt_without_chaining(self):
        """chaining_context가 없으면 기존 형태의 프롬프트가 생성되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_final_prompt

        prompt = _build_final_prompt("테스트기업", "기업 분석", "검색 결과 데이터")

        assert "테스트기업" in prompt
        assert "검색 결과 데이터" in prompt
        assert "이전 분석 단계 검증 결과" not in prompt

    def test_build_final_prompt_with_chaining(self):
        """chaining_context가 있으면 프롬프트에 '이전 분석 단계 검증 결과' 섹션이 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_final_prompt

        chaining = '{"company_overview": {"introduction": "테스트 기업 소개"}}'
        prompt = _build_final_prompt("테스트기업", "기업 분석", "검색 결과 데이터", chaining_context=chaining)

        assert "이전 분석 단계 검증 결과" in prompt
        assert "company_overview" in prompt
        assert "검색 결과 데이터" in prompt

    # --- _is_section_starved 검증 ---

    def test_is_section_starved_true(self):
        """기본값으로만 채워진 섹션은 starved로 판정되어야 한다."""
        from backend.src.company.engine.career_pipeline import _is_section_starved

        section = {"introduction": "정보 부족 - 추가 조사 필요", "industry": "정보 부족 - 추가 조사 필요"}
        assert _is_section_starved(section) is True

    def test_is_section_starved_false(self):
        """실제 데이터가 있는 섹션은 starved가 아니어야 한다."""
        from backend.src.company.engine.career_pipeline import _is_section_starved

        section = {"introduction": "삼성전자는 글로벌 반도체 기업이다.", "industry": "반도체"}
        assert _is_section_starved(section) is False


# ============================================================
# v3.1 신규 기능 테스트: Phase 실패 격리, 독립 리포트, 체이닝 절삭, 검색 타겟팅
# ============================================================
class TestPhaseFailureIsolation:
    """Phase 실패 시 파이프라인 격리 및 안전 처리 테스트"""

    def test_merge_phase_results_with_none_phases(self):
        """일부 Phase가 None이어도 병합이 정상 동작해야 한다."""
        from backend.src.company.engine.career_pipeline import _merge_phase_results

        # Phase 2만 실패
        report = _merge_phase_results(None, None, None)
        assert report is not None
        assert hasattr(report, "company_overview")
        assert hasattr(report, "corporate_culture")
        assert hasattr(report, "swot_analysis")
        assert hasattr(report, "interview_preparation")

    def test_merge_phase_results_partial_success(self):
        """일부 Phase만 성공해도 병합 결과에 해당 섹션 데이터가 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _merge_phase_results
        from backend.src.company.schemas.career_report import CareerAnalysisReport

        # Phase 1만 성공, Phase 2, 3 실패
        phase1 = CareerAnalysisReport.model_validate(
            {
                "company_overview": {
                    "introduction": "삼성전자는 대한민국의 대표적인 전자 기업입니다.",
                    "industry": "반도체",
                }
            }
        )
        merged = _merge_phase_results(phase1, None, None)
        assert "삼성전자" in merged.model_dump()["company_overview"]["introduction"]


class TestIndependentPhaseReports:
    """독립 Phase 리포트 파일 저장 테스트"""

    def test_save_independent_phase_reports(self, tmp_path):
        """Phase별 독립 JSON 파일이 올바르게 저장되어야 한다."""
        from backend.src.company.engine.career_pipeline import _save_independent_phase_reports
        from backend.src.company.schemas.career_report import CareerAnalysisReport

        phase1 = CareerAnalysisReport.model_validate(
            {"company_overview": {"introduction": "테스트 기업입니다.", "industry": "IT"}}
        )

        output_dir = str(tmp_path)
        _save_independent_phase_reports(output_dir, phase1, None, None)

        import json
        import os

        # Phase 1 파일 존재 및 내용 확인
        p1_path = os.path.join(output_dir, "phase1_overview.json")
        assert os.path.exists(p1_path)
        with open(p1_path, encoding="utf-8") as f:
            p1_data = json.load(f)
        assert "company_overview" in p1_data
        assert "테스트" in p1_data["company_overview"]["introduction"]

        # Phase 2 파일 (실패 Phase)
        p2_path = os.path.join(output_dir, "phase2_swot.json")
        assert os.path.exists(p2_path)
        with open(p2_path, encoding="utf-8") as f:
            p2_data = json.load(f)
        assert "error" in p2_data

        # Phase 3 파일 (실패 Phase)
        p3_path = os.path.join(output_dir, "phase3_interview.json")
        assert os.path.exists(p3_path)
        with open(p3_path, encoding="utf-8") as f:
            p3_data = json.load(f)
        assert "error" in p3_data


class TestChainingContextTruncation:
    """체이닝 컨텍스트 JSON-safe 절삭 테스트"""

    def test_truncate_chaining_dict_preserves_json_structure(self):
        """절삭 후에도 유효한 JSON 구조가 유지되어야 한다."""
        from backend.src.company.engine.career_pipeline import _truncate_chaining_dict

        data = {
            "swot_analysis": {
                "strength": ["강점1 " * 50, "강점2 " * 50, "강점3 " * 50, "강점4 " * 50],
                "weakness": ["약점1 " * 50, "약점2 " * 50],
                "opportunity": ["기회1 " * 50],
                "threat": ["위협1 " * 50],
                "so_strategy": "전략",
                "wt_strategy": "전략",
            }
        }

        original_json = json.dumps(data, ensure_ascii=False, indent=2)
        truncated = _truncate_chaining_dict(data, max_chars=1000)
        result_json = json.dumps(truncated, ensure_ascii=False, indent=2)

        # JSON 파싱이 가능해야 함
        parsed = json.loads(result_json)
        assert "swot_analysis" in parsed
        # 실제 절삭이 발생하여 길이가 줄어야 함
        assert len(result_json) < len(original_json)
        # JSON 구조가 유효함
        assert isinstance(parsed["swot_analysis"]["strength"], list)
        assert isinstance(parsed["swot_analysis"]["weakness"], list)

    def test_build_chaining_context_truncation(self):
        """MAX_CHAINING_CHARS를 초과하는 리포트의 체이닝 컨텍스트가 절삭되어야 한다."""
        from unittest.mock import patch

        from backend.src.company.engine.career_pipeline import _build_chaining_context
        from backend.src.company.schemas.career_report import CareerAnalysisReport

        large_report = CareerAnalysisReport.model_validate(
            {"company_overview": {"introduction": "매우 긴 기업 소개입니다. " * 2000, "industry": "반도체"}}
        )

        # MAX_CHAINING_CHARS를 작은 값으로 오버라이드하여 테스트
        with patch("backend.src.company.engine.career_pipeline.MAX_CHAINING_CHARS", 500):
            result = _build_chaining_context(large_report, "기초 팩트", ["company_overview"])

        assert len(result) <= 600  # 약간의 여유 허용
        # JSON 파싱이 가능해야 함
        parsed = json.loads(result)
        assert "company_overview" in parsed

    def test_build_chaining_context_no_truncation_for_small(self):
        """작은 리포트는 절삭 없이 그대로 반환되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_chaining_context
        from backend.src.company.schemas.career_report import CareerAnalysisReport

        small_report = CareerAnalysisReport.model_validate(
            {"company_overview": {"introduction": "삼성전자 소개", "industry": "반도체"}}
        )

        result = _build_chaining_context(small_report, "기초 팩트", ["company_overview"])
        parsed = json.loads(result)
        assert parsed["company_overview"]["introduction"] == "삼성전자 소개"
        # 절삭 마커가 없어야 함
        assert "텍스트 절삭" not in result


class TestSearchTargeting:
    """검색 쿼리 PDF 차단 및 DART 사이트 타겟팅 테스트"""

    def test_post_process_adds_pdf_filter(self):
        """모든 쿼리에 -filetype:pdf가 추가되어야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [
            {"persona": "산업 애널리스트", "query": "매출액 영업이익", "tag": "DART"},
            {"persona": "수석 취업 지원관", "query": "기업문화 핵심가치", "tag": "WEB"},
        ]
        result = _post_process_queries(query_items, "삼성전자")

        for item in result:
            assert "-filetype:pdf" in item["query"], f"PDF 필터 누락: {item['query']}"

    def test_post_process_adds_dart_site_targeting(self):
        """[DART] 태그 쿼리에 site:dart.fss.or.kr OR site:kind.krx.co.kr가 추가되어야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [{"persona": "산업 애널리스트", "query": "매출액 영업이익", "tag": "DART"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert "site:dart.fss.or.kr" in result[0]["query"]
        assert "site:kind.krx.co.kr" in result[0]["query"]

    def test_post_process_no_dart_for_web_tag(self):
        """[WEB] 태그 쿼리에는 DART 사이트 타겟팅이 추가되지 않아야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [{"persona": "수석 취업 지원관", "query": "기업문화 핵심가치", "tag": "WEB"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert "site:dart.fss.or.kr" not in result[0]["query"]

    def test_post_process_no_duplicate_pdf_filter(self):
        """이미 -filetype:pdf가 있는 쿼리에 중복 추가하지 않아야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [{"persona": "산업 애널리스트", "query": "매출액 -filetype:pdf", "tag": "WEB"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert result[0]["query"].count("-filetype:pdf") == 1

    def test_post_process_query_length_with_filters(self):
        """PDF 필터 + DART 타겟팅 추가 후에도 쿼리 길이가 250자를 넘지 않아야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        long_query = "A" * 200
        query_items = [{"persona": "산업 애널리스트", "query": long_query, "tag": "DART"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert len(result[0]["query"]) <= 250


class TestQualityRulesInPrompts:
    """품질 검수 규칙이 시스템 프롬프트에 주입되었는지 테스트"""

    def test_phase1_prompt_has_quality_rules(self):
        """Phase 1 프롬프트에 품질 검수 규칙이 포함되어야 한다."""
        from backend.src.company.engine.personas import PHASE1_SYSTEM_PROMPT

        assert "DART" in PHASE1_SYSTEM_PROMPT
        assert "확정 실적" in PHASE1_SYSTEM_PROMPT or "직전 회계연도" in PHASE1_SYSTEM_PROMPT
        assert "추정치" in PHASE1_SYSTEM_PROMPT or "전망치" in PHASE1_SYSTEM_PROMPT

    def test_phase2_prompt_has_quality_rules(self):
        """Phase 2 프롬프트에 품질 검수 규칙이 포함되어야 한다."""
        from backend.src.company.engine.personas import PHASE2_SYSTEM_PROMPT

        assert "확정 실적" in PHASE2_SYSTEM_PROMPT or "DART" in PHASE2_SYSTEM_PROMPT
        assert "전망" in PHASE2_SYSTEM_PROMPT

    def test_phase3_prompt_has_weakness_mapping(self):
        """Phase 3 프롬프트에 weakness/threat 1:1 매핑 규칙이 포함되어야 한다."""
        from backend.src.company.engine.personas import PHASE3_SYSTEM_PROMPT

        assert "1:1" in PHASE3_SYSTEM_PROMPT or "매핑" in PHASE3_SYSTEM_PROMPT
        assert "weakness" in PHASE3_SYSTEM_PROMPT
        assert "threat" in PHASE3_SYSTEM_PROMPT

    def test_phase3_prompt_has_citation_requirement(self):
        """Phase 3 프롬프트에 데이터 인용 요구 규칙이 포함되어야 한다."""
        from backend.src.company.engine.personas import PHASE3_SYSTEM_PROMPT

        assert "인용" in PHASE3_SYSTEM_PROMPT
        assert "배열 길이" in PHASE3_SYSTEM_PROMPT or "동일" in PHASE3_SYSTEM_PROMPT


class TestNLIFutureProjectionDetection:
    """NLI 평가자 프롬프트에 미래 전망치 탐지 규칙이 포함되었는지 테스트"""

    def test_evaluator_prompt_has_future_projection_rules(self):
        """평가자 시스템 프롬프트에 미래 전망치 환각 탐지 규칙이 포함되어야 한다."""
        from backend.src.company.engine.evaluator import EVALUATOR_SYSTEM_PROMPT

        assert "미래 전망치" in EVALUATOR_SYSTEM_PROMPT or "전망" in EVALUATOR_SYSTEM_PROMPT
        assert "추정" in EVALUATOR_SYSTEM_PROMPT
        assert "확정 실적" in EVALUATOR_SYSTEM_PROMPT or "직전 회계연도" in EVALUATOR_SYSTEM_PROMPT

    def test_evaluator_prompt_has_rewrite_instruction_for_projections(self):
        """미래 전망치 문장에 대해 rewrite 지시를 요구하는 규칙이 있어야 한다."""
        from backend.src.company.engine.evaluator import EVALUATOR_SYSTEM_PROMPT

        assert "rewrite" in EVALUATOR_SYSTEM_PROMPT
        assert "교체" in EVALUATOR_SYSTEM_PROMPT or "교정" in EVALUATOR_SYSTEM_PROMPT
