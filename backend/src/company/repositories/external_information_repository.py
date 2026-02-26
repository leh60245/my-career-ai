"""
외부 검색 정보 적재 리포지토리

역할:
    - ExternalInformation 모델에 대한 CRUD 및 Upsert 로직을 제공합니다.
    - URL 해시 기반 중복 방지(Upsert) 처리를 지원합니다.
"""

import hashlib
import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.repositories.base_repository import BaseRepository, RepositoryError
from backend.src.company.models.external_information import ExternalInformation


logger = logging.getLogger(__name__)


def _hash_url(url: str) -> str:
    """URL을 SHA-256 해시로 변환합니다."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class ExternalInformationRepository(BaseRepository[ExternalInformation]):
    """외부 검색 정보 리포지토리"""

    def __init__(self, session: AsyncSession):
        super().__init__(ExternalInformation, session)

    async def upsert_batch(self, items: list[dict]) -> int:
        """
        외부 검색 정보를 일괄 Upsert합니다.

        동일 URL(url_hash 기준)이 이미 존재하면 스니펫만 병합(JSONB concat)하고,
        존재하지 않으면 새로 INSERT합니다.

        Args:
            items: [{"url": str, "title": str, "snippets": list, "description": str,
                     "source_type": str, "company_name": str, "job_id": str}, ...]

        Returns:
            처리된 행 수
        """
        if not items:
            return 0

        rows_to_upsert = []
        for item in items:
            url = item.get("url", "")
            if not url:
                continue

            rows_to_upsert.append(
                {
                    "url": url,
                    "url_hash": _hash_url(url),
                    "title": (item.get("title") or "")[:1000],
                    "snippets": item.get("snippets") or [],
                    "description": item.get("description"),
                    "source_type": item.get("source_type", "WEB"),
                    "company_name": item.get("company_name"),
                    "job_id": item.get("job_id"),
                }
            )

        if not rows_to_upsert:
            return 0

        try:
            stmt = pg_insert(ExternalInformation).values(rows_to_upsert)
            # ON CONFLICT (url_hash) DO UPDATE: 스니펫 병합, 제목 갱신
            stmt = stmt.on_conflict_do_update(
                constraint="uq_external_informations_url_hash",
                set_={
                    "title": stmt.excluded.title,
                    "snippets": stmt.excluded.snippets,
                    "description": stmt.excluded.description,
                },
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"ExternalInformation upsert_batch 실패: {e}")
            raise RepositoryError(f"Upsert batch failed: {e}") from e

    async def get_by_url(self, url: str) -> ExternalInformation | None:
        """URL 해시로 단건 조회합니다."""
        url_hash = _hash_url(url)
        try:
            stmt = select(ExternalInformation).where(ExternalInformation.url_hash == url_hash)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"ExternalInformation get_by_url 실패: {e}")
            raise RepositoryError(f"Failed to get by URL: {e}") from e

    async def get_by_company(self, company_name: str, limit: int = 100) -> Sequence[ExternalInformation]:
        """기업명으로 검색 정보를 조회합니다."""
        try:
            stmt = (
                select(ExternalInformation)
                .where(ExternalInformation.company_name == company_name)
                .order_by(ExternalInformation.collected_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"ExternalInformation get_by_company 실패: {e}")
            raise RepositoryError(f"Failed to get by company: {e}") from e

    async def get_by_job_id(self, job_id: str) -> Sequence[ExternalInformation]:
        """Job ID로 검색 정보를 조회합니다."""
        try:
            stmt = (
                select(ExternalInformation)
                .where(ExternalInformation.job_id == job_id)
                .order_by(ExternalInformation.collected_at.desc())
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"ExternalInformation get_by_job_id 실패: {e}")
            raise RepositoryError(f"Failed to get by job_id: {e}") from e
