"""
User 도메인 API 라우터

사용자 계정 조회, 프로필 관리 엔드포인트.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.common.repositories.base_repository import EntityNotFound
from backend.src.user.schemas import (
    JobSeekerProfileResponse,
    JobSeekerProfileUpdate,
    UserCreate,
    UserMeResponse,
    UserResponse,
)
from backend.src.user.services import UserService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])


# ============================================================
# Dependencies
# ============================================================
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제공."""
    db_engine = AsyncDatabaseEngine()
    async with db_engine.get_session() as session:
        yield session


async def get_user_service(session: AsyncSession = Depends(get_session)) -> UserService:
    """UserService 팩토리."""
    return UserService.from_session(session)


# ============================================================
# Endpoints
# ============================================================
@router.get("/me", response_model=UserMeResponse, summary="현재 사용자 정보 조회")
async def get_me(user_id: int, service: UserService = Depends(get_user_service)) -> UserMeResponse:
    """
    사용자 정보와 프로필을 함께 반환한다.

    TODO: user_id는 향후 JWT 토큰에서 추출하도록 변경.
    """
    try:
        user = await service.get_user_with_profile(user_id)
    except EntityNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    profile_resp = None
    if user.job_seeker_profile:
        profile_resp = JobSeekerProfileResponse.model_validate(user.job_seeker_profile)

    return UserMeResponse(user=UserResponse.model_validate(user), job_seeker_profile=profile_resp)


@router.put("/profile", status_code=204, summary="구직자 프로필 수정")
async def update_profile(
    user_id: int,
    body: JobSeekerProfileUpdate,
    service: UserService = Depends(get_user_service),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    구직자 프로필을 수정한다.

    TODO: user_id는 향후 JWT 토큰에서 추출하도록 변경.
    """
    try:
        await service.update_job_seeker_profile(user_id, body.model_dump())
        await session.commit()
    except EntityNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/register", response_model=UserResponse, status_code=201, summary="사용자 생성 (개발/테스트용)")
async def register_user(
    body: UserCreate, service: UserService = Depends(get_user_service), session: AsyncSession = Depends(get_session)
) -> UserResponse:
    """
    사용자를 생성한다.

    개발/테스트용 엔드포인트. 향후 Auth 도메인으로 이동 예정.
    """
    try:
        user = await service.create_user(email=body.email, role=body.role)
        await session.commit()
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error(f"사용자 생성 실패: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
