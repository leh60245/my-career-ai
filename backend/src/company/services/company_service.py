import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.company.models.company import Company
from src.company.repositories.company_repository import CompanyRepository


logger = logging.getLogger(__name__)


class CompanyService:
    """
    기업 정보 관리 도메인 서비스 (The Admin)
    역할: 기업 정보의 등록(Onboarding), 갱신, 조회를 담당합니다.
    """

    def __init__(self, company_repo: CompanyRepository):
        self.repo = company_repo

    @classmethod
    def from_session(cls, session: AsyncSession) -> "CompanyService":
        """AsyncSession으로부터 서비스 인스턴스 생성 (Controller용)"""
        return cls(CompanyRepository(session))

    async def onboard_company(
        self,
        corp_code: str,
        company_name: str,
        stock_code: str | None = None,
        sector: str | None = None,
        product: str | None = None,
    ) -> Company:
        """
        기업 등록 및 정보 동기화 (Idempotent Method)

        Args:
            corp_code: DART 고유번호 (Immutable Key)
            company_name: 회사명 (변경 가능)
            stock_code: 종목코드 (상장 시 생성/변경 가능)
            sector: 업종 (변경 가능)
            product: 제품/서비스 (변경 가능)

        Returns:
            Company: 생성되거나 갱신된 기업 객체
        """
        if not corp_code:
            raise ValueError("corp_code is mandatory for onboarding.")

        # 1. [Read] 고유번호로 기존 등록 여부 확인
        existing = await self.repo.get_by_corp_code(corp_code)

        # 2. [Update] 이미 존재한다면 정보 최신화 검사
        if existing:
            update_data = {}

            # 회사명이 변경되었는지 확인
            if existing.company_name != company_name:
                update_data["company_name"] = company_name

            # 종목코드가 변경되었거나 새로 생겼는지 확인
            # (None과 빈 문자열, 혹은 다른 코드로의 변경 감지)
            if existing.stock_code != stock_code:
                update_data["stock_code"] = stock_code

                # [Note] 모델에 is_listed 컬럼이 있다면 여기서 같이 갱신
                # update_data["is_listed"] = bool(stock_code)

            # 업종이 변경되었는지 확인
            if existing.sector != sector:
                update_data["sector"] = sector

            # 제품/서비스가 변경되었는지 확인
            if existing.product != product:
                update_data["product"] = product

            # 변경사항이 있을 때만 DB Update 호출 (DB 부하 절감)
            if update_data:
                logger.info(f"🔄 Updating company info for {corp_code}: {update_data}")
                existing = await self.repo.update(existing.id, update_data)

            return existing

        # 3. [Create] 신규 등록
        logger.info(f"✨ Onboarding new company: {company_name} ({corp_code})")

        new_data = {
            "corp_code": corp_code,
            "company_name": company_name,
            "stock_code": stock_code,
            "sector": sector,
            "product": product,
            "industry_code": None,  # 추후 확장 가능
        }

        return await self.repo.create(new_data)

    async def get_company(self, company_id: int) -> Company | None:
        """
        ID로 기업 정보 단건 조회
        """
        return await self.repo.get(company_id)

    async def get_by_name(self, company_name: str) -> Company | None:
        """회사명으로 단건 조회"""
        return await self.repo.get_by_company_name(company_name)

    async def get_all_companies(
        self,
        limit: int = 100,
        skip: int = 0,
        order_by: str = "company_name",
    ) -> list[Company]:
        """전체 기업 목록 조회 (기본 회사명 오름차순)"""
        companies = await self.repo.get_all(
            skip=skip, limit=limit, order_by=order_by, ascending=True
        )
        return list(companies)
