"""
Context Look-back 임베딩 워커

표(Table) 데이터의 임베딩 품질을 높이기 위해 직전 텍스트 문맥을 포함하여
임베딩을 생성하고 DB를 업데이트하는 스크립트입니다.

핵심 로직:
- 표(table) 데이터는 그 자체만으로는 단위(Unit)나 기준 날짜 정보가 부족함
- 보통 표 바로 위에 설명 텍스트가 존재하므로, 이를 합쳐서 벡터화
- 'previous_row'를 캐싱하며 순차적으로 처리

사용법:
    python -m scripts.run_ingestion --embed --batch-size 32
    python -m scripts.run_ingestion --embed --limit 100  # 테스트용
    python -m scripts.run_ingestion --embed --force      # 기존 임베딩 재생성


변경 이력:
    PHASE 3.5: Legacy Code Migration
    - Removed DBManager dependency (Raw SQL removed)
    - Uses VectorSearchService & SourceMaterialRepository via ORM
    - Fully Async implementation
    - [Fixed] Ensures metadata merging (parity with SQL jsonb_set)
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from tqdm.asyncio import tqdm

from src.common.embedding import EmbeddingService

# [통합 아키텍처]
from src.database import AsyncDatabaseEngine
from src.database.models.source_material import SourceMaterial
from src.database.repositories import SourceMaterialRepository

logger = logging.getLogger(__name__)


class ContextLookbackEmbeddingWorker:
    """
    Context Look-back 방식으로 임베딩을 생성하는 워커 클래스.
    표(Table) 데이터의 문맥을 보강하고 노이즈를 제거합니다.
    """

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

    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self._embedding_service: Optional[EmbeddingService] = None
        self.stats = {
            "total": 0,
            "processed": 0,
            "failed": 0,
            "text_count": 0,
            "table_count": 0,
            "table_with_context": 0,
            "noise_tables_merged": 0,
            "start_time": None,
            "end_time": None,
        }

    def _init_generator(self):
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
            logger.info(f"   Provider: {self._embedding_service.provider}")

    # ==================== 노이즈 감지 로직 ====================
    def _is_noise_table(self, table_content: str) -> bool:
        if not table_content:
            return False
        lines = table_content.strip().split("\n")
        table_rows = [line for line in lines if line.strip().startswith("|")]
        data_rows = [
            row for row in table_rows if not re.match(r"^\|[\s\-:]+\|$", row.strip())
        ]

        if len(data_rows) <= self.NOISE_TABLE_MAX_ROWS:
            for keyword in self.NOISE_KEYWORDS:
                if keyword in table_content:
                    return True

        content_text = re.sub(r"[|\-:]+", " ", table_content)
        words = [w.strip() for w in content_text.split() if len(w.strip()) > 0]
        if not words:
            return False

        keyword_count = sum(
            1 for w in words if any(k in w for k in self.NOISE_KEYWORDS)
        )
        return (keyword_count / len(words)) >= 0.5

    # ==================== DB 조회 (ORM) ====================

    async def fetch_pending_materials(
        self, repo: SourceMaterialRepository, limit: Optional[int], force: bool
    ) -> List[SourceMaterial]:
        """임베딩 대상 조회"""
        from sqlalchemy import select

        stmt = select(SourceMaterial).where(SourceMaterial.chunk_type != "noise_merged")
        if not force:
            stmt = stmt.where(SourceMaterial.embedding == None)

        stmt = stmt.order_by(
            SourceMaterial.report_id.asc(),
            SourceMaterial.sequence_order.asc(),
            SourceMaterial.id.asc(),
        )
        if limit:
            stmt = stmt.limit(limit)

        result = await repo.session.execute(stmt)
        return result.scalars().all()

    async def fetch_previous_row(
        self, repo: SourceMaterialRepository, current: SourceMaterial
    ) -> Optional[SourceMaterial]:
        """직전 행 조회"""
        from sqlalchemy import select, desc

        stmt = (
            select(SourceMaterial)
            .where(
                SourceMaterial.report_id == current.report_id,
                SourceMaterial.sequence_order < current.sequence_order,
            )
            .order_by(desc(SourceMaterial.sequence_order))
            .limit(1)
        )
        result = await repo.session.execute(stmt)
        return result.scalar_one_or_none()

    # ==================== 배치 처리 (핵심 로직) ====================

    async def process_batch(
        self,
        repo: SourceMaterialRepository,
        batch: List[SourceMaterial],
        prev_cache: Dict[int, SourceMaterial],
    ):
        texts_to_embed = []
        # (material_id, has_context, existing_meta)
        embed_targets = []

        for current in batch:
            prev = prev_cache.get(current.report_id)
            if not prev or prev.sequence_order != current.sequence_order - 1:
                prev = await self.fetch_previous_row(repo, current)

            # [CASE 1] 노이즈 테이블 처리
            if (
                current.chunk_type == "table"
                and self._is_noise_table(current.raw_content)
                and prev
            ):
                # 1. Previous에 내용 병합 (Python 문자열 연산)
                merged_content = (
                    (prev.raw_content or "")
                    + "\n\n[참조 정보]\n"
                    + (current.raw_content or "")
                )

                # 메타데이터 병합 (기존 유지 + 플래그 추가)
                prev_meta = prev.meta_info.copy() if prev.meta_info else {}
                prev_meta["has_merged_meta"] = True

                await repo.update(
                    prev.id,
                    {
                        "raw_content": merged_content,
                        "embedding": None,  # 재임베딩 유도
                        "meta_info": prev_meta,
                    },
                )

                # 2. Current는 Drop 처리
                curr_meta = current.meta_info.copy() if current.meta_info else {}
                curr_meta["is_noise_dropped"] = True

                await repo.update(
                    current.id,
                    {
                        "chunk_type": "noise_merged",
                        "embedding": None,
                        "meta_info": curr_meta,
                    },
                )

                # 3. Previous 재임베딩 예약
                path = prev.section_path or "알 수 없음"
                texts_to_embed.append(f"문서 경로: {path}\n{merged_content}")
                embed_targets.append((prev.id, False, prev_meta))

                # 캐시 갱신 (메모리 상 객체도 업데이트)
                prev.raw_content = merged_content
                prev_cache[current.report_id] = prev
                self.stats["noise_tables_merged"] += 1
                continue

            # [CASE 2] 일반 처리
            section = current.section_path or "알 수 없음"
            raw = current.raw_content or ""
            has_ctx = False

            # 문맥 주입 조건
            if (
                current.chunk_type == "table"
                and prev
                and prev.chunk_type == "text"
                and prev.section_path == current.section_path
            ):
                ctx = (
                    prev.raw_content[:500] + "..."
                    if len(prev.raw_content or "") > 500
                    else prev.raw_content
                )
                text = f"문서 경로: {section}\n[문맥 설명: {ctx}]\n[표 데이터]\n{raw}"
                has_ctx = True
            else:
                text = f"문서 경로: {section}\n{raw}"

            texts_to_embed.append(text)

            # 메타데이터 준비 (기존 데이터 로드)
            current_meta = current.meta_info.copy() if current.meta_info else {}
            embed_targets.append((current.id, has_ctx, current_meta))

            prev_cache[current.report_id] = current

            if current.chunk_type == "text":
                self.stats["text_count"] += 1
            else:
                self.stats["table_count"] += 1
                if has_ctx:
                    self.stats["table_with_context"] += 1

        # [임베딩 일괄 생성]
        if texts_to_embed:
            embeddings = self._embedding_service.embed_texts(texts_to_embed)

            for (mid, has_ctx, meta), vec in zip(embed_targets, embeddings):
                # 메타데이터 업데이트 (메모리에서 병합된 dict 사용)
                meta["has_embedding"] = True
                meta["context_injected"] = has_ctx

                # DB 업데이트
                await repo.update(mid, {"embedding": vec, "meta_info": meta})

        return prev_cache

    # ==================== 실행 (Async) ====================

    async def run_async(self, limit: Optional[int], force: bool):
        self.stats["start_time"] = datetime.now()
        logger.info("🚀 Embedding Worker Started (Async/ORM)")

        self._init_generator()
        db_engine = AsyncDatabaseEngine()

        async with db_engine.get_session() as session:
            repo = SourceMaterialRepository(session)

            pending = await self.fetch_pending_materials(repo, limit, force)
            self.stats["total"] = len(pending)
            logger.info(f"📋 Targets: {len(pending)}")

            if not pending:
                return self.stats

            batches = [
                pending[i : i + self.batch_size]
                for i in range(0, len(pending), self.batch_size)
            ]
            prev_cache = {}

            for batch in tqdm(batches, desc="Embedding..."):
                try:
                    prev_cache = await self.process_batch(repo, batch, prev_cache)
                    await session.commit()
                    self.stats["processed"] += len(batch)
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Batch failed: {e}")
                    self.stats["failed"] += len(batch)

        await db_engine.dispose()
        self.stats["end_time"] = datetime.now()
        self._print_summary()
        return self.stats

    def _print_summary(self):
        duration = self.stats["end_time"] - self.stats["start_time"]
        logger.info(f"🏁 Finished in {duration}")
        logger.info(f"   Success: {self.stats['processed']}/{self.stats['total']}")
        logger.info(f"   Merged Noise Tables: {self.stats['noise_tables_merged']}")

    def run(self, limit=None, force=False):
        asyncio.run(self.run_async(limit, force))
