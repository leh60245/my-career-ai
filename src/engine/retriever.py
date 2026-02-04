import asyncio
import logging
from typing import Any

import dspy
import nest_asyncio

from src.common import CompanyEntityResolver
from src.services import LLMQueryAnalyzer, SourceMaterialService

logger = logging.getLogger(__name__)

nest_asyncio.apply()


class PostgresRM(dspy.Retrieve):
    """
    [Adapter] Storm (dspy) Interface for VectorSearchService.
    """

    def __init__(self, service: SourceMaterialService, k: int = 10, min_score: float = 0.5):
        super().__init__(k=k)
        self.service = service  # 이미 초기화된 서비스를 주입받음 (Dependency Injection)
        self.min_score = min_score
        self.usage = 0

    def get_usage_and_reset(self):
        usage = self.usage
        self.usage = 0
        return {"PostgresRM": usage}

    def forward(
        self,
        query_or_queries: str | list[str],
        k: int | None = None,
        company_ids: list[int] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Synchronous entry point called by Storm/dspy.
        """
        queries = [query_or_queries] if isinstance(query_or_queries, str) else query_or_queries
        self.usage += len(queries)
        search_k = k if k is not None else self.k

        collected_results = []

        # Async Loop Handling
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            for query in queries:
                # [핵심] ID 리스트(company_ids)를 서비스에 그대로 전달
                results = loop.run_until_complete(self.service.search(query, company_ids=company_ids, top_k=search_k))

                # Format Conversion (SearchResult -> Storm Dict)
                for res in results:
                    score = res.get("score", 0.0)
                    if score < self.min_score:
                        continue

                    entry = {
                        "snippets": [res["content"]],  # Storm expects list of strings
                        "title": res["title"],
                        "url": res["url"],
                        "description": "",  # Optional field
                    }
                    collected_results.append(entry)

        except Exception as e:
            logger.error(f"PostgresRM search failed: {e}")
            return []

        return collected_results


class HybridRM(dspy.Retrieve):
    """
    [Orchestrator] Intelligent Retrieval Controller.
    """

    def __init__(
        self,
        internal_rm: PostgresRM,
        external_rm: dspy.Retrieve,
        analyzer: LLMQueryAnalyzer,
        resolver: CompanyEntityResolver,
        internal_k: int = 3,
        external_k: int = 7,
    ):
        super().__init__(k=internal_k + external_k)
        self.internal_rm = internal_rm
        self.external_rm = external_rm
        self.analyzer = analyzer
        self.resolver = resolver
        self.internal_k = internal_k
        self.external_k = external_k
        self.usage = 0

        # [Startup] Resolver 초기화 (DB 로드)
        # 주의: 이 부분은 서버 시작 시점(main.py 등)에서 명시적으로 호출하는 게 더 좋으나,
        # 편의상 여기서 Async 실행을 보장해야 함.
        # (이미 데이터가 로드되어 있다면 skip 하도록 Resolver 내부 구현 권장)

    def forward(self, query_or_queries: str | list[str], exclude_urls: list[str] | None = None):
        queries = [query_or_queries] if isinstance(query_or_queries, str) else query_or_queries
        self.usage += len(queries)

        final_results = []

        # Async 로직 실행을 위한 Loop 준비
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        for query in queries:
            # 1. [Intelligence] Analyze & Resolve (Async Execution)
            # QueryAnalyzer와 EntityResolver가 Async라면 loop.run_until_complete 사용
            # 여기서는 Analyzer가 Async라고 가정
            try:
                analysis = loop.run_until_complete(self.analyzer.analyze(query))
            except Exception:
                # 분석 실패 시 기본값 처리
                analysis = None

            target_ids: list[int] = []
            target_names: list[str] = []

            if analysis:
                for name in analysis.target_companies:
                    # Resolver는 Sync(메모리 연산)이므로 바로 호출
                    cid, cname = self.resolver.resolve_to_id(name)
                    if cid:
                        target_ids.append(cid)
                    if cname:
                        target_names.append(cname)
                    if not cid and not cname:
                        target_names.append(name)

            # 2. [Internal Search] PostgresRM
            # 분석된 ID(target_ids)를 전달하여 필터링 검색
            i_res = self.internal_rm.forward(
                query,
                k=self.internal_k,
                company_ids=target_ids,  # ID 필터 전달!
            )

            # 3. External Search
            refined_query = query
            if target_names:
                entities_str = " ".join(target_names)
                refined_query = f"{query} {entities_str}"

            # [핵심] Prediction 타입 문제 해결 로직
            raw_e_res = self.external_rm.forward(refined_query, exclude_urls=exclude_urls)
            e_res = self._normalize_dspy_result(raw_e_res)  # 정규화 메서드 호출

            # Slice & Merge
            e_res = e_res[: self.external_k]
            final_results.extend(i_res + e_res)

        return final_results

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
