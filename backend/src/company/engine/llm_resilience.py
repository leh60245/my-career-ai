"""
LLM API 동시성 제어 및 백오프(Backoff) 시스템

역할:
    - 모든 litellm.completion 호출을 감싸는 공통 래퍼 함수 제공
    - 토큰 버킷 대신 asyncio.Semaphore 기반 동시 호출 제한
    - 429 에러 발생 시 지수적 백오프(2초, 4초, 8초, 16초) 후 재시도
    - 연속 429 에러 초과 시 안전 모드(Concurrency=1) 자동 전환
    - 최대 재시도 초과 시 Graceful Degradation (None 반환, 파이프라인 유지)

설계 원칙:
    - 파이프라인 세션 단위로 LLMResilienceState 인스턴스를 생성하여 상태를 관리합니다.
    - 호출자는 resilient_llm_call()의 반환값이 None인 경우 기본값으로 폴백해야 합니다.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import litellm


logger = logging.getLogger(__name__)

# 동시성 제어 상수
MAX_GLOBAL_LLM_CONCURRENCY = 5
# 지수적 백오프 상수
BACKOFF_BASE_DELAY_SEC = 2.0
BACKOFF_MAX_DELAY_SEC = 30.0
MAX_RETRIES_PER_CALL = 5
# 안전 모드 전환 임계값 (연속 429 에러 횟수)
SAFE_MODE_THRESHOLD = 3


@dataclass
class LLMResilienceState:
    """파이프라인 세션 단위의 LLM 호출 상태 관리"""

    consecutive_429_count: int = 0
    safe_mode: bool = False
    total_429_count: int = 0
    total_retries: int = 0
    total_calls: int = 0
    safe_mode_activated_at: float | None = None
    _semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(MAX_GLOBAL_LLM_CONCURRENCY))
    _safe_semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))

    @property
    def current_semaphore(self) -> asyncio.Semaphore:
        """현재 활성 세마포어 반환 (안전 모드 여부에 따라 분기)"""
        return self._safe_semaphore if self.safe_mode else self._semaphore

    def record_429(self) -> None:
        """429 에러 발생 기록 및 안전 모드 전환 판단"""
        self.consecutive_429_count += 1
        self.total_429_count += 1

        if not self.safe_mode and self.consecutive_429_count >= SAFE_MODE_THRESHOLD:
            self.safe_mode = True
            self.safe_mode_activated_at = time.time()
            logger.warning(
                f"[Resilience] 안전 모드 전환: 연속 429 에러 {self.consecutive_429_count}회 발생. "
                f"동시성을 {MAX_GLOBAL_LLM_CONCURRENCY} -> 1로 축소합니다."
            )

    def record_success(self) -> None:
        """성공 기록 (연속 429 카운터 리셋)"""
        self.consecutive_429_count = 0

    def get_stats(self) -> dict[str, Any]:
        """상태 통계 반환 (run_metadata.json 기록용)"""
        return {
            "total_calls": self.total_calls,
            "total_retries": self.total_retries,
            "total_429_count": self.total_429_count,
            "safe_mode_activated": self.safe_mode,
            "safe_mode_activated_at": self.safe_mode_activated_at,
            "max_concurrency": 1 if self.safe_mode else MAX_GLOBAL_LLM_CONCURRENCY,
        }


def _is_429_error(error: Exception) -> bool:
    """예외가 429 Rate Limit 에러인지 판별합니다."""
    error_str = str(error).lower()
    # litellm은 RateLimitError를 발생시키거나, 메시지에 429/rate limit/quota를 포함
    error_type = type(error).__name__.lower()

    if "ratelimit" in error_type or "rate_limit" in error_type:
        return True
    if "429" in error_str:
        return True
    if "rate limit" in error_str or "quota" in error_str:
        return True
    if "exceeded" in error_str and ("limit" in error_str or "quota" in error_str):
        return True
    return False


def _is_retryable_error(error: Exception) -> bool:
    """재시도 가능한 에러인지 판별합니다."""
    if _is_429_error(error):
        return True

    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # 5xx 서버 에러
    for code in ("500", "502", "503", "504"):
        if code in error_str:
            return True

    # 타임아웃
    if "timeout" in error_str or "timeout" in error_type:
        return True

    # 연결 에러
    if "connection" in error_str or "connection" in error_type:
        return True

    return False


async def resilient_llm_call(
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
    state: LLMResilienceState | None = None,
    temperature: float = 0.3,
    max_tokens: int = 8000,
    response_format: dict[str, str] | None = None,
    max_retries: int = MAX_RETRIES_PER_CALL,
) -> str | None:
    """
    LLM API를 호출하되, 세마포어 + 지수적 백오프 + 안전모드를 적용합니다.

    Args:
        model: litellm 모델 식별자 (예: 'gpt-4o', 'gemini/gemini-2.0-flash')
        messages: LLM 메시지 배열
        api_key: API 키
        state: 파이프라인 세션 상태 (None이면 내부 기본 상태 생성)
        temperature: 샘플링 온도
        max_tokens: 최대 토큰 수
        response_format: 응답 형식 (예: {"type": "json_object"})
        max_retries: 최대 재시도 횟수

    Returns:
        LLM 응답 텍스트. 모든 재시도 실패 시 None (Graceful Degradation)
    """
    if state is None:
        state = LLMResilienceState()

    state.total_calls += 1
    semaphore = state.current_semaphore

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            async with semaphore:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: litellm.completion(**kwargs))

            content = response.choices[0].message.content  # type: ignore[union-attr]
            if content is None:
                raise ValueError("LLM이 빈 응답을 반환했습니다.")

            state.record_success()
            return content

        except Exception as e:
            last_error = e

            if _is_429_error(e):
                state.record_429()
                # 안전 모드 전환 후 세마포어 업데이트
                semaphore = state.current_semaphore

            if not _is_retryable_error(e):
                logger.error(
                    f"[Resilience] 재시도 불가능한 에러 (model={model}, attempt={attempt}): {type(e).__name__}: {e}"
                )
                break

            if attempt < max_retries:
                # 지수적 백오프 계산
                delay = min(BACKOFF_BASE_DELAY_SEC * (2 ** (attempt - 1)), BACKOFF_MAX_DELAY_SEC)
                state.total_retries += 1

                logger.warning(
                    f"[Resilience] 재시도 대기 (model={model}, attempt={attempt}/{max_retries}, "
                    f"delay={delay:.1f}s, safe_mode={state.safe_mode}, "
                    f"error={type(e).__name__}): {str(e)[:200]}"
                )
                await asyncio.sleep(delay)
            else:
                state.total_retries += 1
                logger.error(
                    f"[Resilience] 최대 재시도 횟수 초과 (model={model}, "
                    f"max_retries={max_retries}): {type(e).__name__}: {str(e)[:200]}"
                )

    # Graceful Degradation: 파이프라인 크래시 방지, None 반환
    logger.warning(
        f"[Resilience] Graceful Degradation 발동: model={model}, "
        f"total_429={state.total_429_count}, safe_mode={state.safe_mode}. "
        f"호출자가 기본값으로 폴백해야 합니다. 마지막 에러: {last_error}"
    )
    return None
