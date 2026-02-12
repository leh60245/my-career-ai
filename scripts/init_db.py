import argparse
import asyncio
import logging
import os
import sys

from src.common.models.base import Base
from src.database import AsyncDatabaseEngine


# [1] 프로젝트 루트 경로 설정 (src 모듈 인식을 위해 필수)
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DB_INIT")

# [2] 모델 등록 (중요: 여기서 임포트해야 Base.metadata에 테이블이 등록됨)
# 사용하지 않더라도 임포트는 반드시 유지해야 합니다.


async def init_db(reset: bool = False):
    """
    데이터베이스 테이블 초기화 함수
    Args:
        reset (bool): True일 경우 기존 테이블을 모두 삭제(Drop)하고 재생성
    """
    logger.info("🚀 Starting Database Initialization...")

    # DB 엔진 생성 (Singleton)
    db = AsyncDatabaseEngine()

    try:
        # 비동기 엔진에서 동기 메서드(create_all, drop_all)를 실행하려면 run_sync 필요
        async with db.engine.begin() as conn:
            # [3] 리셋 옵션 처리 (주의: 데이터가 모두 날아감)
            if reset:
                logger.warning("⚠️  '--reset' flag detected. Dropping all existing tables...")
                await conn.run_sync(Base.metadata.drop_all)
                logger.info("🗑️  All tables dropped.")

            # [4] 테이블 생성
            logger.info("🛠️  Creating tables...")
            await conn.run_sync(Base.metadata.create_all)

            # 생성된 테이블 목록 확인 (선택 사항)
            logger.info(f"📋 Registered Tables: {list(Base.metadata.tables.keys())}")

        logger.info("✅ Database initialization completed successfully!")

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    finally:
        # [5] 리소스 정리
        await db.dispose()


if __name__ == "__main__":
    # 커맨드라인 인자 파싱 (--reset 옵션 지원)
    parser = argparse.ArgumentParser(description="Initialize the database tables.")
    parser.add_argument(
        "--reset", action="store_true", help="CAUTION: Drop all tables before creation. Data will be lost."
    )
    args = parser.parse_args()

    # 비동기 실행
    try:
        asyncio.run(init_db(reset=args.reset))
    except KeyboardInterrupt:
        logger.info("🛑 Initialization stopped by user.")
