from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.repositories.base_repository import BaseRepository, RepositoryError
from backend.src.company.models.analysis_report import AnalysisReport
from backend.src.company.models.company import Company
from backend.src.company.models.source_material import SourceMaterial


class SourceMaterialRepository(BaseRepository[SourceMaterial]):
    def __init__(self, session: AsyncSession):
        super().__init__(SourceMaterial, session)

    async def get_by_analysis_report_id(self, analysis_report_id: int) -> Sequence[SourceMaterial]:
        try:
            stmt = (
                select(self.model)
                .where(self.model.analysis_report_id == analysis_report_id)
                .order_by(self.model.sequence_order.asc())
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            raise RepositoryError(f"Failed to get source materials for report {analysis_report_id}: {e}") from e

    async def search_by_vector(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        company_id_list: list[int] | None = None,
        chunk_type_filter: str | None = None,
    ) -> Sequence[Any]:
        try:
            # Cosine Distance Operator (<=>)
            distance_col = self.model.embedding.cosine_distance(query_embedding).label("distance")

            stmt = (
                select(self.model, Company.company_name, distance_col, AnalysisReport.title.label("report_title"))
                .join(AnalysisReport, self.model.analysis_report_id == AnalysisReport.id)
                .join(Company, AnalysisReport.company_id == Company.id)
                .where(self.model.chunk_type != "noise_merged")
            )

            if company_id_list:
                stmt = stmt.where(Company.id.in_(company_id_list))

            if chunk_type_filter:
                stmt = stmt.where(self.model.chunk_type == chunk_type_filter)

            stmt = stmt.order_by(distance_col.asc()).limit(top_k)

            result = await self.session.execute(stmt)
            return result.all()

        except Exception as e:
            raise RepositoryError(f"Vector search failed: {e}") from e

    async def get_context_window(
        self, analysis_report_id: int, center_sequence: int, window_size: int = 1
    ) -> Sequence[SourceMaterial]:
        try:
            min_seq = center_sequence - window_size
            max_seq = center_sequence + window_size

            stmt = (
                select(self.model)
                .where(
                    and_(
                        self.model.analysis_report_id == analysis_report_id,
                        self.model.sequence_order.between(min_seq, max_seq),
                        self.model.chunk_type != "noise_merged",
                        self.model.sequence_order != center_sequence,
                    )
                )
                .order_by(self.model.sequence_order.asc())
            )

            result = await self.session.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            raise RepositoryError(
                f"Failed to get context window for report {analysis_report_id}, seq {center_sequence}: {e}"
            ) from e

    async def create_bulk(self, analysis_report_id: int, chunks: list[dict[str, Any]]) -> Sequence[SourceMaterial]:
        if not chunks:
            return []

        try:
            new_objects = []
            for chunk in chunks:
                material = self.model(
                    analysis_report_id=analysis_report_id,
                    chunk_type=chunk.get("chunk_type", "text"),
                    section_path=chunk.get("section_path", ""),
                    sequence_order=chunk.get("sequence_order", 0),
                    raw_content=chunk.get("raw_content", ""),
                    embedding=chunk.get("embedding"),
                    table_metadata=chunk.get("table_metadata"),
                    meta_info=chunk.get("meta_info"),
                )
                new_objects.append(material)

            self.session.add_all(new_objects)
            await self.session.flush()

            return new_objects

        except Exception as e:
            raise RepositoryError(f"Bulk create failed for report {analysis_report_id}: {e}") from e

    async def get_nearest_next_chunk(self, analysis_report_id: int, current_seq: int) -> SourceMaterial | None:
        """
        현재 시퀀스 이후에 등장하는 '첫 번째 유효 청크'를 조회합니다.
        중간에 'noise_merged'로 죽은 청크들이 있어도 건너뛰고 진짜를 찾아옵니다.
        """
        stmt = (
            select(self.model)
            .where(
                self.model.analysis_report_id == analysis_report_id,
                self.model.sequence_order > current_seq,
                self.model.chunk_type != "noise_merged",
            )
            .order_by(self.model.sequence_order.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_embeddings(self, limit: int | None = None, force: bool = False) -> Sequence[SourceMaterial]:
        """
        임베딩이 필요한 청크 조회
        - force=False: embedding이 None인 것만
        - chunk_type != 'noise_merged' (이미 병합된 노이즈는 제외)
        """
        stmt = select(self.model).where(self.model.chunk_type != "noise_merged")

        if not force:
            stmt = stmt.where(self.model.embedding.is_(None))

        stmt = stmt.order_by(self.model.analysis_report_id.asc(), self.model.sequence_order.asc(), self.model.id.asc())

        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_previous_neighbor(self, analysis_report_id: int, current_seq: int) -> SourceMaterial | None:
        """
        현재 시퀀스 바로 직전의 청크 조회 (Context Look-back 용)
        """
        stmt = (
            select(self.model)
            .where(self.model.analysis_report_id == analysis_report_id, self.model.sequence_order < current_seq)
            .order_by(self.model.sequence_order.desc())  # 역순 정렬해서
            .limit(1)  # 첫 번째 것 (가장 가까운 과거)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_analysis_report_id(self, analysis_report_id: int) -> int:
        """
        특정 리포트의 모든 청크를 삭제합니다.
        """
        stmt = delete(SourceMaterial).where(SourceMaterial.analysis_report_id == analysis_report_id)
        result = await self.session.execute(stmt)
        await self.session.flush()

        return result.rowcount
