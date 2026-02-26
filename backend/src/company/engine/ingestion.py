"""
외부 검색 정보 비동기 적재 서비스

역할:
    - 파이프라인 검색 결과를 백그라운드에서 external_informations 테이블에 적재합니다.
    - 리포트 생성 프로세스를 지연시키지 않도록 비동기 태스크로 실행됩니다.
    - URL 해시 기반 Upsert로 중복 적재를 방지합니다.
"""

import asyncio
import logging
from typing import Any

from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.company.repositories.external_information_repository import ExternalInformationRepository


logger = logging.getLogger(__name__)


async def ingest_search_results(search_results: list[dict[str, Any]], company_name: str, job_id: str) -> int:
    """
    검색 결과를 external_informations 테이블에 비동기 적재합니다.

    이 함수는 백그라운드 태스크로 호출되며, 실패하더라도
    메인 파이프라인을 중단시키지 않습니다.

    Args:
        search_results: HybridRM 검색 결과 리스트
            [{"url": str, "title": str, "snippets": list, "description": str}, ...]
        company_name: 관련 기업명
        job_id: 수집 시점의 Job UUID

    Returns:
        적재 성공 행 수
    """
    if not search_results:
        logger.info(f"[{job_id}] 비동기 적재 대상 없음 (검색 결과 0건)")
        return 0

    # URL이 있는 결과만 필터링 + 중복 URL 제거
    seen_urls: set[str] = set()
    unique_items: list[dict[str, Any]] = []

    for r in search_results:
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        # source_type 추론: DART URL 패턴 감지
        source_type = "WEB"
        if "dart.fss.or.kr" in url or "opendart.fss.or.kr" in url:
            source_type = "DART"

        unique_items.append(
            {
                "url": url,
                "title": r.get("title", ""),
                "snippets": r.get("snippets", []),
                "description": r.get("description", ""),
                "source_type": source_type,
                "company_name": company_name,
                "job_id": job_id,
            }
        )

    if not unique_items:
        logger.info(f"[{job_id}] URL이 있는 고유 검색 결과 0건. 적재 건너뜀")
        return 0

    try:
        db_engine = AsyncDatabaseEngine()
        async with db_engine.get_session() as session:
            repo = ExternalInformationRepository(session)
            row_count = await repo.upsert_batch(unique_items)
            logger.info(
                f"[{job_id}] 외부 검색 정보 적재 완료: "
                f"{row_count}행 upsert (입력 {len(unique_items)}건, 원본 {len(search_results)}건)"
            )
            return row_count

    except Exception as e:
        logger.error(f"[{job_id}] 외부 검색 정보 적재 실패 (non-blocking): {e}")
        return 0


def schedule_ingestion(search_results: list[dict[str, Any]], company_name: str, job_id: str) -> asyncio.Task | None:
    """
    검색 결과 적재를 백그라운드 비동기 태스크로 스케줄링합니다.

    메인 파이프라인 실행을 지연시키지 않으며,
    실패 시에도 파이프라인에 영향을 주지 않습니다.

    Args:
        search_results: 검색 결과 리스트
        company_name: 기업명
        job_id: Job UUID

    Returns:
        생성된 asyncio.Task 또는 None (이벤트 루프 없을 시)
    """
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(
            ingest_search_results(search_results, company_name, job_id), name=f"ingest-{job_id[:8]}"
        )

        def _on_done(t: asyncio.Task) -> None:
            if t.exception():
                logger.error(f"[{job_id}] 백그라운드 적재 태스크 실패: {t.exception()}")

        task.add_done_callback(_on_done)
        logger.info(f"[{job_id}] 백그라운드 적재 태스크 스케줄링 완료 ({len(search_results)}건)")
        return task

    except RuntimeError:
        # 이벤트 루프가 없는 경우 (테스트 환경 등)
        logger.warning(f"[{job_id}] 이벤트 루프 없음. 적재 태스크 스케줄링 건너뜀")
        return None
