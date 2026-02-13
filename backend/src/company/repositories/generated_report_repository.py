from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.repositories.base_repository import BaseRepository
from src.company.models.generated_report import GeneratedReport


class GeneratedReportRepository(BaseRepository[GeneratedReport]):
    def __init__(self, session: AsyncSession):
        super().__init__(GeneratedReport, session)

    async def get_by_job_id(self, job_id: str) -> GeneratedReport | None:
        stmt = select(self.model).where(self.model.job_id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
