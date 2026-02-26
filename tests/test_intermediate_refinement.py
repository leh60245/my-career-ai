"""
중간 정제 파이프라인 및 외부 데이터 적재 테스트

테스트 대상:
    1. ExternalInformation 모델 및 리포지토리 (DB 통합 테스트)
    2. QuestionToQuery 쿼리 다각화 (단위 테스트, LLM mock)
    3. AnswerQuestion 중간 정제 (단위 테스트, LLM mock)
    4. refine_search_results Map-Reduce 정제 (단위 테스트, LLM mock)
    5. ingest_search_results 비동기 DB 적재 (DB 통합 테스트)
    6. _build_refined_llm_context 컨텍스트 빌드 (단위 테스트)
    7. Edge Cases: Context Starvation, 중복 URL, Rate Limit 방어
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.company.engine.intermediate_refinement import (
    _ANSWER_QUESTION_SYSTEM_PROMPT,
    _QUESTION_TO_QUERY_SYSTEM_PROMPT,
    expand_queries,
    extract_answer,
    refine_search_results,
)
from backend.src.company.models.external_information import ExternalInformation
from backend.src.company.repositories.external_information_repository import ExternalInformationRepository, _hash_url


# ============================================================
# 헬퍼: litellm.completion mock 응답 생성기
# ============================================================
def _make_llm_response(content: str) -> MagicMock:
    """litellm.completion이 반환할 MagicMock 응답을 생성한다."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


# ============================================================
# 1. ExternalInformation 모델 및 리포지토리 테스트
# ============================================================
class TestExternalInformationModel:
    """ExternalInformation 모델 기본 동작 테스트"""

    async def test_create_external_information(self, session: AsyncSession):
        """외부 검색 정보를 정상 생성할 수 있다."""
        repo = ExternalInformationRepository(session)
        info = ExternalInformation(
            url="https://example.com/test-page",
            url_hash=_hash_url("https://example.com/test-page"),
            title="테스트 페이지",
            snippets=["테스트 스니펫 1", "테스트 스니펫 2"],
            source_type="WEB",
            company_name="테스트기업",
            job_id="test-job-001",
        )

        created = await repo.create(info)
        assert created.id is not None
        assert created.url == "https://example.com/test-page"
        assert created.title == "테스트 페이지"
        assert created.snippets == ["테스트 스니펫 1", "테스트 스니펫 2"]
        assert created.source_type == "WEB"
        assert created.company_name == "테스트기업"
        assert created.created_at is not None


class TestExternalInformationRepository:
    """ExternalInformation 리포지토리 Upsert 및 조회 테스트"""

    async def test_upsert_batch_insert(self, session: AsyncSession):
        """upsert_batch가 새로운 항목을 정상 INSERT 한다."""
        repo = ExternalInformationRepository(session)
        items = [
            {
                "url": "https://example.com/page-1",
                "title": "Page 1",
                "snippets": ["Snippet 1"],
                "description": "Desc 1",
                "source_type": "WEB",
                "company_name": "Test Corp",
                "job_id": "job-001",
            },
            {
                "url": "https://example.com/page-2",
                "title": "Page 2",
                "snippets": ["Snippet 2"],
                "description": "Desc 2",
                "source_type": "DART",
                "company_name": "Test Corp",
                "job_id": "job-001",
            },
        ]

        count = await repo.upsert_batch(items)
        assert count == 2

    async def test_upsert_batch_dedup(self, session: AsyncSession):
        """동일 URL에 대해 upsert_batch가 UPDATE를 수행한다."""
        repo = ExternalInformationRepository(session)

        # 1차 INSERT
        items1 = [
            {
                "url": "https://example.com/dedup-test",
                "title": "Original Title",
                "snippets": ["Original Snippet"],
                "source_type": "WEB",
                "company_name": "Test Corp",
                "job_id": "job-001",
            }
        ]
        await repo.upsert_batch(items1)

        # 2차 UPSERT (같은 URL, 다른 title)
        items2 = [
            {
                "url": "https://example.com/dedup-test",
                "title": "Updated Title",
                "snippets": ["Updated Snippet"],
                "source_type": "WEB",
                "company_name": "Test Corp",
                "job_id": "job-002",
            }
        ]
        count = await repo.upsert_batch(items2)
        assert count == 1

        # 확인: title이 업데이트되었는지
        found = await repo.get_by_url("https://example.com/dedup-test")
        assert found is not None
        assert found.title == "Updated Title"

    async def test_upsert_batch_empty_list(self, session: AsyncSession):
        """빈 리스트로 upsert_batch 호출 시 0을 반환한다."""
        repo = ExternalInformationRepository(session)
        count = await repo.upsert_batch([])
        assert count == 0

    async def test_upsert_batch_skips_empty_url(self, session: AsyncSession):
        """URL이 빈 항목은 건너뛴다."""
        repo = ExternalInformationRepository(session)
        items = [{"url": "", "title": "No URL"}, {"url": "https://example.com/valid", "title": "Valid"}]
        count = await repo.upsert_batch(items)
        assert count == 1

    async def test_get_by_url(self, session: AsyncSession):
        """URL로 단건 조회가 동작한다."""
        repo = ExternalInformationRepository(session)
        url = "https://example.com/get-by-url-test"
        await repo.upsert_batch([{"url": url, "title": "Test", "snippets": ["s1"]}])

        result = await repo.get_by_url(url)
        assert result is not None
        assert result.url == url

    async def test_get_by_url_not_found(self, session: AsyncSession):
        """존재하지 않는 URL 조회 시 None을 반환한다."""
        repo = ExternalInformationRepository(session)
        result = await repo.get_by_url("https://nonexistent.example.com")
        assert result is None

    async def test_get_by_company(self, session: AsyncSession):
        """기업명으로 검색 정보를 조회한다."""
        repo = ExternalInformationRepository(session)
        await repo.upsert_batch(
            [
                {"url": "https://example.com/company-1", "title": "T1", "company_name": "TestCorp"},
                {"url": "https://example.com/company-2", "title": "T2", "company_name": "TestCorp"},
                {"url": "https://example.com/other", "title": "T3", "company_name": "OtherCorp"},
            ]
        )

        results = await repo.get_by_company("TestCorp")
        assert len(results) == 2
        assert all(r.company_name == "TestCorp" for r in results)

    async def test_get_by_job_id(self, session: AsyncSession):
        """Job ID로 검색 정보를 조회한다."""
        repo = ExternalInformationRepository(session)
        await repo.upsert_batch(
            [
                {"url": "https://example.com/job-a", "title": "T1", "job_id": "job-aaa"},
                {"url": "https://example.com/job-b", "title": "T2", "job_id": "job-aaa"},
                {"url": "https://example.com/job-c", "title": "T3", "job_id": "job-bbb"},
            ]
        )

        results = await repo.get_by_job_id("job-aaa")
        assert len(results) == 2


# ============================================================
# 2. URL 해시 유틸리티 테스트
# ============================================================
class TestUrlHash:
    """URL 해시 함수 테스트"""

    def test_hash_url_deterministic(self):
        """동일 URL은 항상 동일한 해시를 반환한다."""
        url = "https://example.com/test"
        assert _hash_url(url) == _hash_url(url)

    def test_hash_url_different_urls(self):
        """다른 URL은 다른 해시를 반환한다."""
        assert _hash_url("https://a.com") != _hash_url("https://b.com")

    def test_hash_url_is_sha256(self):
        """해시 결과가 SHA-256 형식 (64자 hex)이다."""
        h = _hash_url("https://example.com")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ============================================================
# 3. QuestionToQuery 쿼리 다각화 테스트
# ============================================================
class TestExpandQueries:
    """QuestionToQuery 함수 테스트

    expand_queries 내부에서 litellm이 로컬 임포트되고
    loop.run_in_executor로 호출되므로, litellm.completion을
    직접 패치하여 동기 MagicMock을 반환합니다.
    """

    def test_system_prompt_has_required_placeholders(self):
        """시스템 프롬프트에 {year} 및 {company_name} 플레이스홀더가 존재한다."""
        assert "{year}" in _QUESTION_TO_QUERY_SYSTEM_PROMPT
        assert "{company_name}" in _QUESTION_TO_QUERY_SYSTEM_PROMPT

    @patch("litellm.completion")
    async def test_expand_queries_happy_path(self, mock_completion):
        """정상 LLM 응답 시 다각화된 쿼리 배열을 반환한다."""
        mock_completion.return_value = _make_llm_response(
            json.dumps(
                {"queries": ["삼성전자 2026 사업보고서 매출", "삼성전자 반도체 시장점유율", "삼성전자 DART 재무제표"]}
            )
        )

        result = await expand_queries("삼성전자 매출액", "삼성전자", "openai")

        assert len(result) == 3
        assert all("삼성전자" in q for q in result)

    @patch("litellm.completion")
    async def test_expand_queries_adds_company_name(self, mock_completion):
        """기업명이 없는 쿼리에 기업명을 자동 추가한다."""
        mock_completion.return_value = _make_llm_response(
            json.dumps({"queries": ["반도체 시장 전망", "삼성전자 실적"]})
        )

        result = await expand_queries("시장 전망", "삼성전자", "openai")

        assert len(result) == 2
        assert "삼성전자" in result[0]  # 기업명 추가됨

    @patch("litellm.completion")
    async def test_expand_queries_fallback_on_error(self, mock_completion):
        """LLM 호출 실패 시 원본 질문을 반환한다."""
        mock_completion.side_effect = Exception("API Error")

        result = await expand_queries("삼성전자 매출액", "삼성전자", "openai")

        assert result == ["삼성전자 매출액"]

    @patch("litellm.completion")
    async def test_expand_queries_fallback_on_empty_response(self, mock_completion):
        """LLM이 빈 queries 배열을 반환해도 원본 질문을 반환한다."""
        mock_completion.return_value = _make_llm_response(json.dumps({"queries": []}))

        result = await expand_queries("테스트 쿼리", "테스트기업", "openai")

        assert result == ["테스트 쿼리"]

    @patch("litellm.completion")
    async def test_expand_queries_respects_max_queries(self, mock_completion):
        """max_queries 파라미터로 최대 쿼리 수를 제한한다."""
        mock_completion.return_value = _make_llm_response(
            json.dumps({"queries": ["q1", "q2", "q3", "q4", "q5", "q6", "q7"]})
        )

        result = await expand_queries("테스트", "테스트기업", "openai", max_queries=3)

        assert len(result) <= 3

    @patch("litellm.completion")
    async def test_expand_queries_truncates_long_query(self, mock_completion):
        """200자를 초과하는 쿼리를 절삭한다."""
        long_query = "A" * 250
        mock_completion.return_value = _make_llm_response(json.dumps({"queries": [long_query]}))

        result = await expand_queries("긴 쿼리", "테스트기업", "openai")

        assert len(result) == 1
        assert len(result[0]) <= 200

    @patch("litellm.completion")
    async def test_expand_queries_gemini_provider(self, mock_completion):
        """gemini 프로바이더 선택 시 올바른 모델로 호출된다."""
        mock_completion.return_value = _make_llm_response(json.dumps({"queries": ["쿼리"]}))

        await expand_queries("테스트", "기업", "gemini")

        call_args = mock_completion.call_args
        assert call_args[1]["model"] == "gemini/gemini-2.0-flash"


# ============================================================
# 4. AnswerQuestion 중간 정제 테스트
# ============================================================
class TestExtractAnswer:
    """AnswerQuestion 함수 테스트"""

    def test_system_prompt_has_required_rules(self):
        """시스템 프롬프트에 핵심 규칙이 포함되어 있다."""
        assert "추측이나 창작은 절대 금지" in _ANSWER_QUESTION_SYSTEM_PROMPT
        assert "300자 이내" in _ANSWER_QUESTION_SYSTEM_PROMPT

    async def test_extract_answer_empty_snippets(self):
        """빈 스니펫 리스트에 대해 빈 문자열을 반환한다 (Context Starvation 방어)."""
        result = await extract_answer("테스트 질문", [], "테스트기업", "openai")
        assert result == ""

    @patch("litellm.completion")
    async def test_extract_answer_happy_path(self, mock_completion):
        """정상 LLM 응답 시 정제된 답변을 반환한다."""
        mock_completion.return_value = _make_llm_response(
            json.dumps({"answer": "삼성전자의 2025년 매출액은 93.8조원입니다. [출처: DART]"})
        )

        result = await extract_answer(
            "삼성전자 매출액", ["삼성전자 2025년 매출 93.8조원 달성", "전년 대비 10% 성장"], "삼성전자", "openai"
        )

        assert "93.8조원" in result

    @patch("litellm.completion")
    async def test_extract_answer_fallback_on_error(self, mock_completion):
        """LLM 호출 실패 시 빈 문자열을 반환한다."""
        mock_completion.side_effect = Exception("API Error")

        result = await extract_answer("테스트 질문", ["스니펫 1"], "테스트기업", "openai")

        assert result == ""

    @patch("litellm.completion")
    async def test_extract_answer_with_semaphore(self, mock_completion):
        """Semaphore 기반 동시성 제어가 동작한다."""
        mock_completion.return_value = _make_llm_response(json.dumps({"answer": "테스트 답변"}))

        sem = asyncio.Semaphore(2)
        result = await extract_answer("질문", ["스니펫"], "기업", "openai", semaphore=sem)

        assert result == "테스트 답변"

    @patch("litellm.completion")
    async def test_extract_answer_truncates_long_snippets(self, mock_completion):
        """3000자 초과 스니펫이 절삭되어 LLM에 전달된다."""
        mock_completion.return_value = _make_llm_response(json.dumps({"answer": "답변"}))

        long_snippets = ["X" * 2000, "Y" * 2000]

        result = await extract_answer("질문", long_snippets, "기업", "openai")
        assert result == "답변"

        # LLM 호출 시 truncation이 적용되었는지 검증
        call_args = mock_completion.call_args
        messages = call_args[1]["messages"]
        user_msg = messages[1]["content"]
        assert "이하 생략" in user_msg


# ============================================================
# 5. Map-Reduce 정제 테스트
# ============================================================
class TestRefineSearchResults:
    """refine_search_results 함수 테스트"""

    @patch("litellm.completion")
    async def test_refine_search_results_happy_path(self, mock_completion):
        """정상 동작 시 질문별 정제된 답변 딕셔너리를 반환한다."""
        mock_completion.return_value = _make_llm_response(json.dumps({"answer": "정제된 답변"}))

        query_items = [
            {"persona": "산업 애널리스트", "query": "삼성전자 매출", "tag": "DART"},
            {"persona": "산업 애널리스트", "query": "삼성전자 사업분야", "tag": "WEB"},
        ]
        search_results_by_query = {
            "삼성전자 매출": [{"snippets": ["매출 93.8조원"]}],
            "삼성전자 사업분야": [{"snippets": ["반도체, 디스플레이"]}],
        }

        result = await refine_search_results(query_items, search_results_by_query, "삼성전자", "openai")

        assert len(result) == 2
        assert "삼성전자 매출" in result
        assert "삼성전자 사업분야" in result

    @patch("litellm.completion")
    async def test_refine_search_results_handles_empty_results(self, mock_completion):
        """검색 결과가 없는 질문도 안전하게 처리한다."""
        mock_completion.return_value = _make_llm_response(json.dumps({"answer": ""}))

        query_items = [{"persona": "P", "query": "빈 결과 쿼리", "tag": "WEB"}]
        search_results_by_query = {"빈 결과 쿼리": []}

        result = await refine_search_results(query_items, search_results_by_query, "기업", "openai")

        assert "빈 결과 쿼리" in result
        assert result["빈 결과 쿼리"] == ""  # 빈 스니펫 -> 빈 답변

    @patch("litellm.completion")
    async def test_refine_search_results_parallel_execution(self, mock_completion):
        """여러 질문을 병렬로 처리한다."""
        call_count = 0

        def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            return _make_llm_response(json.dumps({"answer": f"답변 {call_count}"}))

        mock_completion.side_effect = _side_effect

        query_items = [{"persona": "P1", "query": f"쿼리{i}", "tag": "WEB"} for i in range(5)]
        search_results_by_query = {f"쿼리{i}": [{"snippets": [f"스니펫{i}"]}] for i in range(5)}

        result = await refine_search_results(query_items, search_results_by_query, "기업", "openai")

        assert len(result) == 5
        assert call_count == 5  # 각 질문에 대해 1회씩 호출


# ============================================================
# 6. 정제 컨텍스트 빌드 테스트
# ============================================================
class TestBuildRefinedLlmContext:
    """_build_refined_llm_context 함수 테스트"""

    def test_builds_context_with_refined_answers(self):
        """정제된 답변으로 LLM 컨텍스트를 빌드한다."""
        from backend.src.company.engine.career_pipeline import _build_refined_llm_context
        from backend.src.company.engine.personas import INDUSTRY_ANALYST

        refined_answers = {"삼성전자 매출": "매출 93.8조원 (2025년 기준)", "삼성전자 경쟁사": "SK하이닉스, 마이크론 등"}
        expanded_queries = [
            {"persona": "산업 애널리스트", "query": "삼성전자 매출", "tag": "DART"},
            {"persona": "산업 애널리스트", "query": "삼성전자 경쟁사", "tag": "WEB"},
        ]
        search_results_by_persona = {
            "산업 애널리스트": [{"snippets": ["raw snippet"], "title": "T", "url": "http://a.com"}]
        }

        context, truncation = _build_refined_llm_context(
            refined_answers, expanded_queries, search_results_by_persona, "삼성전자", [INDUSTRY_ANALYST]
        )

        assert "삼성전자" in context
        assert "정제된 분석 데이터" in context
        assert "93.8조원" in context
        assert truncation["pipeline_version"] == "v3.0-refined"

    def test_fallback_to_raw_snippets_when_no_refined(self):
        """정제된 답변이 없을 때 원시 스니펫으로 폴백한다."""
        from backend.src.company.engine.career_pipeline import _build_refined_llm_context
        from backend.src.company.engine.personas import INDUSTRY_ANALYST

        refined_answers = {"query1": ""}  # 빈 답변
        expanded_queries = [{"persona": "산업 애널리스트", "query": "query1", "tag": "WEB"}]
        search_results_by_persona = {
            "산업 애널리스트": [{"snippets": ["Raw Fallback Snippet"], "title": "Source", "url": "http://example.com"}]
        }

        context, _ = _build_refined_llm_context(
            refined_answers, expanded_queries, search_results_by_persona, "테스트기업", [INDUSTRY_ANALYST]
        )

        assert "Raw Fallback Snippet" in context
        assert "원시 검색 결과 폴백" in context

    def test_truncation_metadata_correct(self):
        """truncation 메타데이터가 올바르게 반환된다."""
        from backend.src.company.engine.career_pipeline import _build_refined_llm_context
        from backend.src.company.engine.personas import INDUSTRY_ANALYST

        refined_answers = {"q": "짧은 답변"}
        expanded_queries = [{"persona": "산업 애널리스트", "query": "q", "tag": "WEB"}]
        search_results_by_persona = {"산업 애널리스트": []}

        _, truncation = _build_refined_llm_context(
            refined_answers, expanded_queries, search_results_by_persona, "기업", [INDUSTRY_ANALYST]
        )

        assert truncation["truncated"] is False
        assert "refined_per_persona" in truncation
        assert truncation["refined_per_persona"]["산업 애널리스트"] == 1

    def test_dedup_same_answer(self):
        """동일한 답변이 중복으로 나오면 제거된다."""
        from backend.src.company.engine.career_pipeline import _build_refined_llm_context
        from backend.src.company.engine.personas import INDUSTRY_ANALYST

        refined_answers = {"q1": "동일 답변", "q2": "동일 답변"}
        expanded_queries = [
            {"persona": "산업 애널리스트", "query": "q1", "tag": "WEB"},
            {"persona": "산업 애널리스트", "query": "q2", "tag": "WEB"},
        ]
        search_results_by_persona = {"산업 애널리스트": []}

        _, truncation = _build_refined_llm_context(
            refined_answers, expanded_queries, search_results_by_persona, "기업", [INDUSTRY_ANALYST]
        )

        # 동일 답변이 중복 제거되어 valid_count = 1
        assert truncation["refined_per_persona"]["산업 애널리스트"] == 1


# ============================================================
# 7. 비동기 DB 적재 테스트
# ============================================================
class TestIngestionService:
    """ingest_search_results 비동기 적재 테스트"""

    async def test_ingest_empty_results(self):
        """빈 검색 결과에 대해 0을 반환한다."""
        from backend.src.company.engine.ingestion import ingest_search_results

        count = await ingest_search_results([], "테스트기업", "test-job")
        assert count == 0

    async def test_ingest_filters_empty_urls(self):
        """URL이 빈 결과를 필터링한다."""
        from backend.src.company.engine.ingestion import ingest_search_results

        results = [{"url": "", "title": "No URL"}, {"title": "No URL Key"}]

        count = await ingest_search_results(results, "테스트기업", "test-job")
        assert count == 0

    async def test_ingest_deduplicates_urls(self):
        """중복 URL을 제거한다."""
        from unittest.mock import AsyncMock

        from backend.src.company.engine.ingestion import ingest_search_results

        mock_repo = MagicMock()
        mock_repo.upsert_batch = AsyncMock(return_value=2)

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_ctx.__aexit__.return_value = None

        with patch("backend.src.company.engine.ingestion.AsyncDatabaseEngine") as mock_engine:
            mock_engine.return_value.get_session.return_value = mock_ctx

            with patch("backend.src.company.engine.ingestion.ExternalInformationRepository", return_value=mock_repo):
                results = [
                    {"url": "https://example.com/dup", "title": "First"},
                    {"url": "https://example.com/dup", "title": "Second"},  # 중복
                    {"url": "https://example.com/unique", "title": "Unique"},
                ]

                await ingest_search_results(results, "기업", "job-001")

                # upsert_batch에 전달된 items에서 중복 제거 확인
                call_args = mock_repo.upsert_batch.call_args[0][0]
                urls = [item["url"] for item in call_args]
                assert len(urls) == 2
                assert len(set(urls)) == 2  # 고유 URL 2개

    async def test_ingest_detects_dart_source(self):
        """DART URL 패턴을 감지하여 source_type을 설정한다."""
        from unittest.mock import AsyncMock

        from backend.src.company.engine.ingestion import ingest_search_results

        mock_repo = MagicMock()
        mock_repo.upsert_batch = AsyncMock(return_value=2)

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_ctx.__aexit__.return_value = None

        with patch("backend.src.company.engine.ingestion.AsyncDatabaseEngine") as mock_engine:
            mock_engine.return_value.get_session.return_value = mock_ctx

            with patch("backend.src.company.engine.ingestion.ExternalInformationRepository", return_value=mock_repo):
                results = [
                    {"url": "https://dart.fss.or.kr/report/123", "title": "DART Report"},
                    {"url": "https://example.com/news", "title": "News"},
                ]

                await ingest_search_results(results, "기업", "job-001")

                call_args = mock_repo.upsert_batch.call_args[0][0]
                dart_items = [i for i in call_args if i["source_type"] == "DART"]
                web_items = [i for i in call_args if i["source_type"] == "WEB"]
                assert len(dart_items) == 1
                assert len(web_items) == 1


# ============================================================
# 8. Edge Cases 통합 테스트
# ============================================================
class TestEdgeCases:
    """엣지 케이스 및 방어 로직 테스트"""

    @patch("litellm.completion")
    async def test_expand_queries_json_decode_error_then_retry(self, mock_completion):
        """첫 번째 JSON 파싱 실패 후 재시도가 동작한다."""
        bad_response = _make_llm_response("not valid json")
        good_response = _make_llm_response(json.dumps({"queries": ["삼성전자 매출"]}))

        mock_completion.side_effect = [bad_response, good_response]

        result = await expand_queries("삼성전자 매출", "삼성전자", "openai")
        assert result == ["삼성전자 매출"]

    async def test_upsert_batch_large_title_truncation(self, session: AsyncSession):
        """1000자 초과 제목이 절삭된다."""
        repo = ExternalInformationRepository(session)
        items = [{"url": "https://example.com/long-title", "title": "A" * 1500, "snippets": []}]
        count = await repo.upsert_batch(items)
        assert count == 1

        found = await repo.get_by_url("https://example.com/long-title")
        assert found is not None
        assert len(found.title) <= 1000

    @patch("litellm.completion")
    async def test_refine_handles_llm_exception_gracefully(self, mock_completion):
        """Map-Reduce 중 일부 LLM 호출이 실패해도 전체가 크래시하지 않는다."""
        call_count = 0

        def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated LLM failure")
            return _make_llm_response(json.dumps({"answer": "성공 답변"}))

        mock_completion.side_effect = _side_effect

        query_items = [
            {"persona": "P", "query": "실패쿼리", "tag": "WEB"},
            {"persona": "P", "query": "성공쿼리", "tag": "WEB"},
        ]
        search_results_by_query = {"실패쿼리": [{"snippets": ["s1"]}], "성공쿼리": [{"snippets": ["s2"]}]}

        result = await refine_search_results(query_items, search_results_by_query, "기업", "openai")

        # 실패한 쿼리는 빈 답변, 성공한 쿼리는 정상 답변
        assert "실패쿼리" in result
        assert "성공쿼리" in result
