"""
Career Pipeline 단위 테스트

고정 페르소나 쿼리 큐, JSON 파싱 방어 로직, Pydantic 스키마 검증,
쿼리 후처리 로직 등을 검증합니다.

테스트 전략:
- personas 모듈: 순수 단위 테스트 (DB 불필요)
- json_utils 모듈: 순수 단위 테스트 (DB 불필요)
- career_report 스키마: Pydantic 검증 테스트
- career_pipeline 내부 함수: 순수 단위 테스트
"""

import json

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

    def test_post_process_adds_keyword(self):
        """페르소나별 키워드가 쿼리에 추가되어야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        query_items = [{"persona": "수석 취업 지원관", "query": "삼성전자 공식 홈페이지", "tag": "WEB"}]
        result = _post_process_queries(query_items, "삼성전자")

        # 수석 취업 지원관의 키워드 중 하나가 추가되어야 함
        added_any = any(kw in result[0]["query"] for kw in ["인재상", "핵심가치", "조직문화", "채용"])
        assert added_any

    def test_post_process_respects_length_limit(self):
        """쿼리 길이가 200자를 넘지 않아야 한다."""
        from backend.src.company.engine.career_pipeline import _post_process_queries

        long_query = "A" * 190
        query_items = [{"persona": "실무 면접관", "query": long_query, "tag": "WEB"}]
        result = _post_process_queries(query_items, "삼성전자")

        assert len(result[0]["query"]) <= 200

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

        context = _build_llm_context(search_results, "삼성전자")
        assert "삼성전자" in context
        assert "산업 애널리스트" in context
        assert "반도체 분야 세계 1위" in context

    def test_build_llm_context_empty_results(self):
        """검색 결과가 없을 때 '검색 결과 없음'이 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_llm_context

        context = _build_llm_context({}, "네이버")
        assert "네이버" in context
        assert "검색 결과 없음" in context

    def test_build_final_prompt_contains_all_parts(self):
        """최종 프롬프트에 모든 필수 요소가 포함되어야 한다."""
        from backend.src.company.engine.career_pipeline import _build_final_prompt

        prompt = _build_final_prompt("삼성전자", "기업 분석", "테스트 컨텍스트")
        assert "삼성전자" in prompt
        assert "기업 분석" in prompt
        assert "테스트 컨텍스트" in prompt
        assert "JSON" in prompt


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
