"""
Mock 사용자 시드 스크립트

FE Mock Auth 전용으로 사용하는 두 개의 테스트 사용자를 DB에 삽입한다.
- id=1  email=jobseeker@mycareer.ai  role=JOB_SEEKER
- id=2  email=admin@mycareer.ai      role=MANAGER

E2E 테스트 전 또는 개발 환경 초기화 후 1회 실행하면 된다.

Usage:
    conda activate enterprise-storm
    python scripts/seed_mock_users.py
"""

import asyncio
import logging
import os
import sys

from sqlalchemy import text

from backend.src.common.database import AsyncDatabaseEngine


# 프로젝트 루트 경로를 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SEED")

MOCK_USERS = [
    {"id": 1, "email": "jobseeker@mycareer.ai", "role": "JOB_SEEKER", "tier": "FREE"},
    {"id": 2, "email": "admin@mycareer.ai", "role": "MANAGER", "tier": "FREE"},
]


async def seed_mock_users() -> None:
    """Mock 사용자를 DB에 멱등적으로 삽입한다 (이미 존재하면 무시)."""
    db = AsyncDatabaseEngine()
    await db.initialize()

    async with db.get_session() as session:
        for mock in MOCK_USERS:
            # 이미 존재하는 ID/이메일은 건너뜀 (멱등성 보장)
            result = await session.execute(
                text("SELECT id FROM users WHERE id = :id OR email = :email"),
                {"id": mock["id"], "email": mock["email"]},
            )
            row = result.fetchone()
            if row:
                logger.info(f"[SKIP] User id={mock['id']} ({mock['email']}) already exists (found id={row[0]})")
                continue

            # id를 직접 지정하여 삽입 (시퀀스와 충돌 방지를 위해 시퀀스도 갱신)
            await session.execute(
                text(
                    "INSERT INTO users (id, email, role, tier) VALUES (:id, :email, :role::user_role, :tier::user_tier) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": mock["id"], "email": mock["email"], "role": mock["role"], "tier": mock["tier"]},
            )
            logger.info(f"[INSERT] User id={mock['id']} ({mock['email']}, role={mock['role'].value})")

        # id 시퀀스를 max(id)보다 크게 업데이트하여 자동 증가 충돌 방지
        await session.execute(
            text(
                "SELECT setval("
                "  pg_get_serial_sequence('users', 'id'),"
                "  GREATEST((SELECT COALESCE(MAX(id), 0) FROM users), 2)"
                ")"
            )
        )
        await session.commit()

    logger.info("Mock user seeding completed.")
    await db.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(seed_mock_users())
    except KeyboardInterrupt:
        logger.info("Seeding stopped by user.")
