import logging
import re
from collections.abc import Sequence
from typing import Any

from src.common.services.embedding import Embedding
from src.company.models.source_material import SourceMaterial
from src.company.repositories.source_material_repository import SourceMaterialRepository


logger = logging.getLogger(__name__)


class IngestionService:
    """
    데이터 적재 및 전처리 서비스 (Shift-Left Strategy 적용)

    역할:
    1. Raw Chunks 전처리 (노이즈 병합, 고아 노이즈 제거)
    2. Context-Aware 임베딩 생성 (Text -> Table 문맥 주입)
    3. DB Bulk Insert
    """

    # 노이즈 테이블 판별을 위한 키워드
    NOISE_KEYWORDS = [
        "단위",
        "Unit",
        "범례",
        "참조",
        "※",
        "주)",
        "(주)",
        "원",
        "천원",
        "백만원",
        "억원",
        "주1)",
        "주2)",
        "(단위",
    ]
    NOISE_TABLE_MAX_ROWS = 2

    def __init__(self, source_repo: SourceMaterialRepository, embedding: Embedding):
        self.source_repo = source_repo
        self.embedding = embedding

    async def save_chunks(self, analysis_report_id: int, chunks: list[dict[str, Any]]) -> Sequence[SourceMaterial]:
        """
        [Main Pipeline] 전처리 -> 임베딩 -> 저장

        Note: Idempotency(멱등성)를 보장하기 위해, 저장 전 해당 리포트의 기존 청크를 삭제합니다.
        """
        if not chunks:
            return []

        logger.info(f"   ⚙️ Processing {len(chunks)} chunks for Report ID {analysis_report_id}...")

        # 1. [Clean Slate] 기존 데이터 삭제 (중복 방지)
        await self.delete_report_chunks(analysis_report_id)

        # 2. [전처리] 노이즈 병합 및 정제 (Shift Left)
        clean_chunks = self._preprocess_and_merge(chunks)

        logger.debug(f"      Noise filtering: {len(chunks)} -> {len(clean_chunks)} chunks")

        # 3. [임베딩] 문맥 주입 (Context Injection) 및 벡터 생성
        await self._generate_embeddings(clean_chunks)

        # 4. [저장] DB Bulk Insert
        # Repository가 ID 주입을 담당하므로 ID와 청크 리스트를 넘김
        return await self.source_repo.create_bulk(analysis_report_id, clean_chunks)

    async def delete_report_chunks(self, analysis_report_id: int) -> None:
        """
        특정 리포트의 모든 청크를 삭제합니다. (재적재 전 초기화)
        """
        count = await self.source_repo.delete_by_analysis_report_id(analysis_report_id)
        if count > 0:
            logger.info(f"   🗑️ Deleted {count} old chunks for Report ID {analysis_report_id}")

    # =========================================================================
    #  Internal Logic (Preprocessing & Embedding)
    # =========================================================================

    def _is_noise_table(self, content: str) -> bool:
        """표가 단순 단위/범례 표(Noise)인지 판별"""
        if not content:
            return False

        lines = content.strip().split("\n")
        # 파이프(|)로 시작하는 라인 중 구분선이 아닌 데이터 행 카운트
        data_rows = [line for line in lines if "|" in line and not re.match(r"^\|[\s\-:]+\|$", line.strip())]

        if len(data_rows) <= self.NOISE_TABLE_MAX_ROWS:
            for k in self.NOISE_KEYWORDS:
                if k in content:
                    return True
        return False

    def _preprocess_and_merge(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        [핵심 로직] Forward Merge Strategy
        노이즈(단위 표)를 발견하면 다음 표의 헤더로 병합하고, 고아 노이즈는 제거합니다.
        """
        n = len(chunks)
        merge_flags = [False] * n

        for i in range(n):
            if merge_flags[i]:
                continue

            curr = chunks[i]
            curr_type = curr.get("chunk_type", "text")
            curr_content = curr.get("raw_content", "")

            # [Noise Check]
            if curr_type == "table" and self._is_noise_table(curr_content):
                # Forward Lookahead
                if i + 1 < n and chunks[i + 1].get("chunk_type") == "table":
                    next_chunk = chunks[i + 1]

                    # [Merge] 단위 정보를 다음 표의 상단에 붙임
                    next_chunk["raw_content"] = f"{curr_content}\n\n{next_chunk['raw_content']}"

                    # 메타데이터 업데이트
                    meta = next_chunk.get("meta_info", {}) if next_chunk.get("meta_info") else {}
                    meta["has_merged_meta"] = True
                    next_chunk["meta_info"] = meta

                    # 현재 청크 삭제 표시
                    merge_flags[i] = True
                else:
                    # [Drop] 고아 노이즈
                    merge_flags[i] = True

        valid_chunks = [chunks[i] for i in range(n) if not merge_flags[i]]
        return valid_chunks

    async def _generate_embeddings(self, chunks: list[dict[str, Any]]) -> None:
        """
        청크 리스트에 대해 임베딩을 생성하여 주입합니다.
        * 최적화: 텍스트가 있는 경우만 API 호출
        * 문맥 주입: Table은 직전 Text의 내용을 임베딩 프롬프트에 포함
        """
        texts_to_embed = []
        indices_to_embed = []

        for i, chunk in enumerate(chunks):
            raw_content = chunk.get("raw_content", "")
            if not raw_content.strip():
                continue

            # [Context Injection Logic]
            embedding_text = raw_content
            context_injected = False

            # 현재가 Table이고, 직전이 Text이며, 같은 섹션인 경우 -> 문맥 주입
            if chunk.get("chunk_type") == "table" and i > 0:
                prev = chunks[i - 1]
                if prev.get("chunk_type") == "text" and prev.get("section_path") == chunk.get("section_path"):
                    prev_text = prev.get("raw_content", "")
                    # 너무 길면 뒤쪽 500자만 사용
                    ctx = prev_text[-500:] if len(prev_text) > 500 else prev_text

                    path = chunk.get("section_path", "N/A")
                    embedding_text = f"문서 경로: {path}\n[문맥 설명: {ctx}]\n[표 데이터]\n{raw_content}"
                    context_injected = True

            # 일반 텍스트의 경우 경로 정보만이라도 추가하면 좋음 (선택 사항)
            elif chunk.get("chunk_type") == "text":
                path = chunk.get("section_path", "")
                embedding_text = f"{path}\n{raw_content}"

            texts_to_embed.append(embedding_text)
            indices_to_embed.append((i, context_injected))

        if not texts_to_embed:
            return

        # Batch Embedding Call (비동기)
        embeddings = await self.embedding.get_embeddings(texts_to_embed)

        # 결과 매핑
        for (idx, has_ctx), vec in zip(indices_to_embed, embeddings):
            chunks[idx]["embedding"] = vec

            # 메타 정보 업데이트
            meta = chunks[idx].get("meta_info", {}) if chunks[idx].get("meta_info") else {}
            meta["has_embedding"] = True
            if has_ctx:
                meta["context_injected"] = True
            chunks[idx]["meta_info"] = meta
