"""
인증 및 권한 검증 미들웨어.

사용자 역할(role) 기반의 접근 제어를 제공합니다.
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import UserRole
from backend.src.user.services import UserService


logger = logging.getLogger(__name__)


async def check_admin_permission(user_id: int, session: AsyncSession) -> None:
    """
    사용자가 관리자(MANAGER 또는 SYSTEM_ADMIN) 권한을 가지고 있는지 확인합니다.

    관리자 엔드포인트 접근 시 이 함수를 호출하여 권한을 검증합니다.

    Args:
        user_id: 사용자 ID
        session: 데이터베이스 세션

    Raises:
        HTTPException(403): 관리자 권한이 없을 경우
        HTTPException(404): 사용자를 찾을 수 없을 경우
    """
    try:
        service = UserService.from_session(session)
        user = await service.get_user(user_id)

        if not user:
            logger.warning(f"User not found: {user_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from None

        # 관리자 권한 확인
        if user.role not in (UserRole.MANAGER, UserRole.SYSTEM_ADMIN):
            logger.warning(f"Unauthorized access attempt by user {user_id} with role {user.role}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permission required") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Permission check failed for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Permission check failed") from e
