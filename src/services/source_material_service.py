import logging
from collections.abc import Sequence

from src.common import Embedding
from src.models import SourceMaterial
from src.repositories import SourceMaterialRepository
from src.schemas import SearchResult
from src.services import RerankerService

logger = logging.getLogger(__name__)


class SourceMaterialService:
    """
    Orchestrates the RAG retrieval process.
    """

    def __init__(
        self,
        source_material_repo: SourceMaterialRepository,
        embedding: Embedding,
        reranker_service: RerankerService,
    ) -> None:
        self.repo = source_material_repo
        self.embedding = embedding
        self.reranker = reranker_service

    async def search(
        self,
        query: str,
        company_ids: list[int] | None = None,
        top_k: int = 10,
        enable_rerank: bool = True,
    ) -> Sequence[SearchResult]:

        # 1. 임베딩

        query_vector = await self.embedding.get_embeddings([query])

        fetch_k = top_k * 3 if enable_rerank else top_k

        # 2. DB 검색 (순수하게 ID 필터링만 수행)
        raw_rows = await self.repo.search_by_vector(
            query_embedding=query_vector[0],
            company_id_list=company_ids,  # 외부에서 결정된 ID 리스트 사용
            top_k=fetch_k,
            chunk_type_filter="text",  # 우선 텍스트 위주로 검색
        )

        if not raw_rows:
            return []

        # 3. Process Results (Raw -> Schema + Table Attachment)
        processed_results = await self._process_results(raw_rows)

        # 4. Reranking (Cross-Encoder)
        if enable_rerank and processed_results:
            logger.info(f"🤖 Reranking {len(processed_results)} documents...")
            processed_results = await self.reranker.rerank(query=query, docs=processed_results, top_k=top_k)

        return processed_results  # type: ignore

    async def _process_results(self, raw_rows: Sequence) -> Sequence[SearchResult]:
        """
        DB의 Raw 결과(Row)를 표준 SearchResult 스키마로 변환하고,
        필요 시 다음 청크(Table)를 찾아 내용을 보강합니다.
        """
        results: list[SearchResult] = []

        for row in raw_rows:
            # SourceMaterialRepository.search_by_vector의 반환값 구조에 맞춤
            # (SourceMaterial, company_name, distance)
            material: SourceMaterial = row[0]
            company_name: str = row[1]
            distance: float = row[2]

            # Distance(거리) -> Score(유사도) 변환 (Cosine Distance 기준)
            score = 1 - distance
            content = material.raw_content

            # [Logic] Text 뒤에 Table이 숨어있는지 확인 (Forward Lookup)
            # N+1 문제가 있지만, 현재 top_k 수준에서는 허용. 나중에 bulk fetch로 최적화 가능.
            next_chunk = await self.repo.get_nearest_next_chunk(material.analysis_report_id, material.sequence_order)

            if next_chunk:
                # 다음 청크가 '표(table)'이고, 거리가 5칸 이내라면 붙이기
                seq_gap = next_chunk.sequence_order - material.sequence_order
                if next_chunk.chunk_type == "table" and seq_gap <= 5:
                    content += f"\n\n[관련 표 데이터]\n{next_chunk.raw_content}"

                    # 표 메타정보가 있으면 힌트 추가
                    meta = next_chunk.meta_info or {}
                    if meta.get("has_merged_meta"):
                        content = "[참고: 표에 단위/범례 정보가 포함됨]\n" + content

            # SearchResult TypedDict 생성
            result_item: SearchResult = {
                "content": content,
                "title": material.section_path or "No Title",
                "url": f"dart_report_{material.analysis_report_id}_chunk_{material.id}",
                "score": score,
                "source": "vector",
                # Internal Metadata
                "_company_name": company_name,
                # _intent, _matched_entities는 이제 상위(HybridRM)에서 관리하므로 여기서 굳이 안 넣어도 됨
                # 필요하다면 context passing 용도로 추가 가능
            }
            results.append(result_item)

        return results
