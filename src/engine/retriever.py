import asyncio
import logging
from typing import Any

import dspy
import nest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

# [허용] 세션 생성을 위한 도구는 Import 가능
from knowledge_storm.rm import SerperRM
from src.common import CompanyEntityResolver, Embedding

# Local Imports
from src.common.config import AI_CONFIG

# [Factory] DB 엔진 생성 로직은 connection.py에서 가져옴 (직접 생성 X)
from src.database.connection import AsyncDatabaseEngine, create_isolated_engine
from src.repositories.company_repository import CompanyRepository

# [Repository] 쿼리 로직은 여기서 가져옴 (직접 select X)
from src.repositories.source_material_repository import SourceMaterialRepository
from src.services.llm_query_analyzer import LLMQueryAnalyzer
from src.services.reranker_service import RerankerService

# Services
from src.services.source_material_service import SourceMaterialService

logger = logging.getLogger(__name__)


class PostgresRM(dspy.Retrieve):
    """
    [Adapter] Storm (dspy) Interface for VectorSearchService.
    """

    def __init__(self, k: int = 10, min_score: float = 0.5):
        super().__init__(k=k)
        self.min_score = min_score
        self.usage = 0
        # Stateless 서비스 미리 준비
        self.embedding = Embedding()
        self.reranker_service = RerankerService()

    def get_usage_and_reset(self):
        usage = self.usage
        self.usage = 0
        return {"PostgresRM": usage}

    async def aclose(self) -> None:
        if hasattr(self.embedding, "aclose"):
            await self.embedding.aclose()

    def forward(
        self,
        query_or_queries: str | list[str],
        k: int | None = None,
        company_ids: list[int] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:

        queries = [query_or_queries] if isinstance(query_or_queries, str) else query_or_queries
        self.usage += len(queries)
        search_k = k if k is not None else self.k
        collected_results = []

        # Thread-safe Loop 확보
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # [핵심] Loop 내부에서 독립적인 DB 연결 사용
        async def _thread_safe_search(query_text: str):
            # 1. 독립 엔진 생성 (connection.py 위임)
            local_engine = create_isolated_engine()

            # 2. 세션 팩토리 생성
            async_session_factory = async_sessionmaker(
                local_engine, expire_on_commit=False
            )
            try:
                async with async_session_factory() as session:
                    repo = SourceMaterialRepository(session)
                    service = SourceMaterialService(
                        source_material_repo=repo,
                        embedding=self.embedding,
                        reranker_service=self.reranker_service
                    )
                    return await service.search(query_text, company_ids=company_ids, top_k=search_k)
            finally:
                await local_engine.dispose()

        # dspy의 sync 호출을 async로 변환
        nest_asyncio.apply()

        for query in queries:
            try:
                results = loop.run_until_complete(_thread_safe_search(query))

                for res in results:
                    score = res.get("score", 0.0)
                    if score < self.min_score:
                        continue
                    entry = {
                        "snippets": [res.get("content", "")],
                        "title": res.get("title", "No Title"),
                        "url": res.get("url", ""),
                        "description": "",
                    }
                    collected_results.append(entry)
            except Exception as e:
                logger.error(f"PostgresRM search error: {e}")
                continue

        return collected_results


class HybridRM(dspy.Retrieve):
    """
    [Orchestrator] PostgresRM + SerperRM + EntityResolver (Lazy Loading Pattern)
    """

    def __init__(self, internal_k: int = 5, external_k: int = 5):
        super().__init__(k=internal_k + external_k)
        self.internal_k = internal_k
        self.external_k = external_k
        self.usage = 0

        self.internal_rm = PostgresRM(k=internal_k)
        serper_key = AI_CONFIG.get("serper_api_key")
        self.external_rm = SerperRM(serper_search_api_key=serper_key, k=external_k)

        # 2. Lazy Initialization
        self.analyzer: LLMQueryAnalyzer | None = None
        self.resolver: CompanyEntityResolver | None = None

        # DB Engine
        self.db_engine = AsyncDatabaseEngine()

    async def _ensure_initialized(self):
        """
        필요한 시점에 Resolver와 Analyzer를 준비합니다.
        특히 Resolver에게 DB의 최신 회사 목록을 주입합니다.
        """
        # 1. Analyzer 초기화
        if not self.analyzer:
            self.analyzer = LLMQueryAnalyzer()

        # 2. Resolver 초기화
        if not self.resolver:
            logger.info("⚡ Initializing CompanyEntityResolver with DB data...")
            self.resolver = CompanyEntityResolver()

            local_engine = create_isolated_engine()
            async_session_factory = async_sessionmaker(
                local_engine, expire_on_commit=False
            )

            try:
                async with async_session_factory() as session:
                    repo = CompanyRepository(session)
                    company_map = await repo.get_all_company_map()
                    self.resolver.update_company_map(company_map)
                    logger.info(f"HybridRM: Loaded {len(company_map)} companies.")
            except Exception as e:
                logger.error(f"HybridRM init failed: {e}")
            finally:
                await local_engine.dispose()

    def forward(self, query_or_queries: str | list[str], exclude_urls: list[str]) -> list[dict[str, Any]]:

        queries = [query_or_queries] if isinstance(query_or_queries, str) else query_or_queries
        self.usage += len(queries)
        final_results = []

        # Async Loop 확보
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _execute_hybrid_search(query_text: str):
            # [핵심] 실행 직전에 도구들 준비 (데이터 로딩 포함)
            await self._ensure_initialized()
            assert self.analyzer is not None

            target_ids = []
            target_names = []

            try:
                analysis = await self.analyzer.analyze(query_text)
            except Exception as e:
                logger.warning(f"Analyzer failed: {e}")
                analysis = None

            # 2. 기업 식별 (Resolver)
            # "삼전" -> (ID: 1, Name: "삼성전자")
            if analysis and self.resolver:
                for name in analysis.target_companies:
                    # Resolver는 이제 메모리에 맵을 갖고 있으므로 동기 호출
                    cid, cname = self.resolver.resolve_to_id(name)

                    if cid:
                        target_ids.append(cid)
                    if cname:
                        target_names.append(cname)

                    # 식별되지 않아도 원본 이름은 검색 키워드로 활용
                    if not cid and not cname:
                        target_names.append(name)

            # 3. 내부 검색 (PostgresRM)
            # 식별된 ID(target_ids)를 넘겨서 해당 기업 문서만 필터링
            i_res = self.internal_rm.forward(query_text, k=self.internal_k, company_ids=target_ids)

            # 4. 외부 검색 (SerperRM)
            # 검색어 보강: "반도체 전망" -> "반도체 전망 삼성전자 SK하이닉스"
            refined_query = query_text
            if target_names:
                entities_str = " ".join(target_names)
                # 쿼리가 너무 길어지는 것 방지
                refined_query = f"{query_text} {entities_str}"[:200]

            raw_e_res = self.external_rm.forward(refined_query, exclude_urls=exclude_urls)
            e_res = self._normalize_dspy_result(raw_e_res)

            # 5. 결과 결합 (내부 + 외부)
            return i_res + e_res[: self.external_k]

        # 쿼리별 실행
        for query in queries:
            try:
                results = loop.run_until_complete(_execute_hybrid_search(query))
                final_results.extend(results)
            except Exception as e:
                logger.error(f"HybridRM search failed: {e}")
                continue

        return final_results

    async def aclose(self) -> None:
        """Release async clients held by analyzer to avoid loop-closed errors."""
        if self.internal_rm and hasattr(self.internal_rm, "aclose"):
            await self.internal_rm.aclose()
        if self.analyzer and hasattr(self.analyzer, "aclose"):
            await self.analyzer.aclose()
        self.analyzer = None

    def _normalize_dspy_result(self, res: Any) -> list[dict[str, Any]]:
        """
        [Type Guard] dspy Prediction이나 기타 타입을 list[dict]로 강제 변환
        """
        # 1. Prediction 객체인 경우 (passages 속성에 접근)
        if hasattr(res, "passages"):
            return res.passages

        # 2. 이미 리스트인 경우
        if isinstance(res, list):
            return res

        # 3. 딕셔너리 단일 객체인 경우
        if isinstance(res, dict):
            return [res]

        # 4. 알 수 없는 타입 (빈 리스트 반환)
        logger.warning(f"Unknown return type from external RM: {type(res)}")
        return []
