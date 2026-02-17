"""
Talent Service (인재상 관리)

"DB First, Search Fallback" 전략으로 인재상 데이터를 제공한다.
DB에 데이터가 없으면 Serper + LLM으로 크롤링 → 추출 → 저장한다.
"""

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.llm.client import LLMClient, LLMClientError
from backend.src.common.search.client import SearchClient, SearchClientError
from backend.src.company.models.talent import CompanyTalent
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.repositories.talent_repository import CompanyTalentRepository


logger = logging.getLogger(__name__)


# ============================================================
# LLM 응답 스키마 (내부용)
# ============================================================
class ExtractedTalentInfo(BaseModel):
    """LLM이 검색 결과에서 추출한 인재상 데이터."""

    core_values: list[str] = Field(default_factory=list, description="기업의 핵심 가치 키워드 리스트 (3~7개)")
    description: str = Field(default="", description="인재상에 대한 종합 설명 (200자 내외)")


# ============================================================
# Talent Service
# ============================================================
class TalentService:
    """
    기업 인재상 서비스.

    Read-Through Cache 전략:
        1. DB 조회 → 데이터 있으면 즉시 반환
        2. DB에 없으면 → Serper 검색 → LLM 추출 → DB 저장 → 반환
    """

    def __init__(self, talent_repo: CompanyTalentRepository, company_repo: CompanyRepository) -> None:
        self.talent_repo = talent_repo
        self.company_repo = company_repo

    @classmethod
    def from_session(cls, session: AsyncSession) -> "TalentService":
        """AsyncSession으로부터 서비스 인스턴스를 생성한다."""
        return cls(talent_repo=CompanyTalentRepository(session), company_repo=CompanyRepository(session))

    async def get_or_crawl_talent(self, company_name: str) -> CompanyTalent | None:
        """
        기업 인재상을 조회하거나, 없으면 크롤링하여 생성한다.

        Args:
            company_name: 기업명

        Returns:
            CompanyTalent 인스턴스 또는 None (기업을 찾을 수 없는 경우)
        """
        # 1. Company 조회
        company = await self.company_repo.get_by_company_name(company_name)
        if not company:
            logger.warning(f"기업 '{company_name}' 을(를) DB에서 찾을 수 없습니다.")
            return None

        # 2. DB에서 인재상 조회
        existing = await self.talent_repo.get_latest_by_company_id(company.id)
        if existing:
            logger.info(f" DB 캐시 사용: {company_name} 인재상 (id={existing.id})")
            return existing

        # 3. Fallback: 검색 + LLM 추출
        logger.info(f"🔍 인재상 크롤링 시작: {company_name}")
        try:
            extracted = await self._search_and_extract(company_name)
        except (SearchClientError, LLMClientError) as e:
            logger.error(f"인재상 크롤링 실패 ({company_name}): {e}")
            return None

        if not extracted or (not extracted.core_values and not extracted.description):
            logger.warning(f"인재상 추출 결과 없음: {company_name}")
            return None

        # 4. DB 저장
        current_year = datetime.now(UTC).year
        talent = await self.talent_repo.create(
            {
                "company_id": company.id,
                "year": current_year,
                "core_values": extracted.core_values,
                "description": extracted.description,
                "source_url": None,
            }
        )
        logger.info(f"💾 인재상 저장 완료: {company_name} → {extracted.core_values}")
        return talent

    async def get_talent_context(self, company_name: str) -> dict:
        """
        프롬프트에 주입할 인재상 컨텍스트를 딕셔너리로 반환한다.

        Args:
            company_name: 기업명

        Returns:
            {"core_values": [...], "description": "..."} 또는 빈 dict
        """
        talent = await self.get_or_crawl_talent(company_name)
        if not talent:
            return {"core_values": [], "description": ""}
        return {"core_values": talent.core_values or [], "description": talent.description or ""}

    # ============================================================
    # Private: 검색 + LLM 추출
    # ============================================================
    async def _search_and_extract(self, company_name: str) -> ExtractedTalentInfo:
        """
        Serper 검색 → LLM으로 인재상 정보를 추출한다.

        Args:
            company_name: 기업명

        Returns:
            추출된 인재상 정보
        """
        search_client = SearchClient()
        snippets = await search_client.search_snippets(query=f"{company_name} 인재상 핵심가치 인재육성", num_results=5)

        if not snippets.strip():
            return ExtractedTalentInfo()

        llm_client = LLMClient()
        system_prompt = (
            "당신은 기업 HR 분석 전문가입니다. "
            "아래 검색 결과에서 해당 기업의 '인재상'과 '핵심 가치'를 추출하세요.\n\n"
            "규칙:\n"
            "1. core_values: 기업이 공식적으로 사용하는 핵심 가치 키워드 3~7개를 리스트로 추출\n"
            "2. description: 인재상을 200자 이내로 요약\n"
            "3. 검색 결과에서 확인되는 정보만 사용하고, 추측하지 마세요\n"
            "4. 반드시 JSON으로 응답하세요"
        )

        user_prompt = f"기업: {company_name}\n\n검색 결과:\n{snippets}\n\n위 정보에서 인재상과 핵심가치를 추출해주세요."

        result = await llm_client.generate(
            system_prompt=system_prompt, user_prompt=user_prompt, response_model=ExtractedTalentInfo, temperature=0.3
        )

        return result
