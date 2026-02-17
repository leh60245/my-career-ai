"""
Search Client (공통 인프라)

Serper API (Google Search)를 호출하는 Async Wrapper.
기업 인재상 크롤링, 직무 정보 검색 등에 사용한다.

사용 예시:
    from backend.src.common.search.client import SearchClient

    client = SearchClient()
    results = await client.search("삼성전자 인재상 핵심가치")
"""

import logging
from typing import Any

import httpx

from backend.src.common.config import AI_CONFIG, SERPER_CONFIG


logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_DEFAULT_TIMEOUT = 15.0


class SearchClientError(Exception):
    """검색 클라이언트 오류."""


class SearchClient:
    """
    Serper API 기반 Google 검색 클라이언트.

    특징:
        - 한국어 검색 최적화 (gl=kr, hl=ko)
        - 최근 1년 내 결과 우선 (tbs=qdr:y)
        - 블로그/커뮤니티 도메인 자동 필터링
    """

    def __init__(self, api_key: str | None = None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        """
        검색 클라이언트를 초기화한다.

        Args:
            api_key: Serper API 키 (기본값: config에서 로드)
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.api_key = api_key or AI_CONFIG.get("serper_api_key")
        self.timeout = timeout

        if not self.api_key:
            logger.warning("SERPER_API_KEY가 설정되지 않았습니다. 검색 기능이 비활성화됩니다.")

    async def search(self, query: str, num_results: int = 10) -> list[dict[str, Any]]:
        """
        Google 검색을 수행하고 결과를 반환한다.

        Args:
            query: 검색 쿼리
            num_results: 반환할 결과 수 (최대 100)

        Returns:
            검색 결과 리스트. 각 항목은 {title, link, snippet} 포함.

        Raises:
            SearchClientError: API 호출 실패
        """
        if not self.api_key:
            raise SearchClientError("SERPER_API_KEY가 설정되지 않았습니다.")

        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

        payload = {
            "q": query,
            "gl": SERPER_CONFIG.get("gl", "kr"),
            "hl": SERPER_CONFIG.get("hl", "ko"),
            "num": num_results,
        }

        # 선택적 파라미터
        location = SERPER_CONFIG.get("location")
        if location:
            payload["location"] = location

        tbs = SERPER_CONFIG.get("tbs")
        if tbs:
            payload["tbs"] = tbs

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(_SERPER_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            # organic 결과 정규화
            organic = data.get("organic", [])
            results = []
            for item in organic:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "position": item.get("position", 0),
                    }
                )

            logger.info(f"🔍 Search '{query[:50]}' → {len(results)} results")
            return results

        except httpx.TimeoutException as e:
            raise SearchClientError(f"검색 타임아웃 ({self.timeout}초): {e}") from e
        except httpx.HTTPStatusError as e:
            raise SearchClientError(f"Serper API 오류 ({e.response.status_code}): {e}") from e
        except Exception as e:
            raise SearchClientError(f"검색 실패: {e}") from e

    async def search_snippets(self, query: str, num_results: int = 5) -> str:
        """
        검색 결과의 snippet을 하나의 텍스트로 합쳐 반환한다.

        LLM 프롬프트에 검색 컨텍스트로 주입할 때 유용하다.

        Args:
            query: 검색 쿼리
            num_results: 사용할 결과 수

        Returns:
            합쳐진 snippet 텍스트
        """
        results = await self.search(query, num_results=num_results)

        snippets = []
        for r in results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            link = r.get("link", "")
            if snippet:
                snippets.append(f"[{title}]({link})\n{snippet}")

        return "\n\n".join(snippets)
