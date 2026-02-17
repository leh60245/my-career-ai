"""
LLM Client Wrapper (공통 인프라)

OpenAI GPT-4o 호출을 위한 Async Wrapper.
JSON Mode를 강제하여 Pydantic 모델 기반의 구조화된 응답을 보장한다.

사용 예시:
    from backend.src.common.llm.client import LLMClient
    from pydantic import BaseModel

    class MyResponse(BaseModel):
        answer: str

    client = LLMClient()
    result = await client.generate(
        system_prompt="당신은 도우미입니다.",
        user_prompt="안녕하세요",
        response_model=MyResponse,
    )
"""

import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel

from backend.src.common.config import AI_CONFIG


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 재시도 및 타임아웃 설정
_DEFAULT_TIMEOUT = 60.0
_MAX_RETRIES = 2


class LLMClientError(Exception):
    """LLM 호출 중 발생하는 기본 예외."""


class LLMTokenLimitError(LLMClientError):
    """토큰 한도 초과 시 발생하는 예외."""


class LLMTimeoutError(LLMClientError):
    """LLM 응답 타임아웃 시 발생하는 예외."""


class LLMClient:
    """
    OpenAI Chat Completions API를 위한 Async 클라이언트.

    특징:
        - JSON Mode 강제: response_model(Pydantic)을 인자로 받아 구조화된 응답 보장
        - 자동 재시도: Timeout/5xx 에러 시 최대 2회 재시도
        - Token Limit 예외 처리
    """

    def __init__(self, model: str | None = None, api_key: str | None = None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        """
        LLM 클라이언트를 초기화한다.

        Args:
            model: 사용할 모델명 (기본값: config의 default_model)
            api_key: OpenAI API 키 (기본값: config에서 로드)
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.model = model or AI_CONFIG.get("default_model", "gpt-4o")
        self.api_key = api_key or AI_CONFIG.get("openai_api_key")
        self.timeout = timeout
        self._base_url = "https://api.openai.com/v1/chat/completions"

        if not self.api_key:
            raise LLMClientError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> T | str:
        """
        LLM에 프롬프트를 전송하고 응답을 반환한다.

        Args:
            system_prompt: 시스템 프롬프트 (역할 정의)
            user_prompt: 사용자 프롬프트 (실제 질문/지시)
            response_model: 응답을 파싱할 Pydantic 모델 (None이면 raw text 반환)
            temperature: 생성 온도 (0.0 ~ 2.0)
            max_tokens: 최대 생성 토큰 수

        Returns:
            response_model이 주어지면 파싱된 Pydantic 인스턴스, 아니면 raw text

        Raises:
            LLMTokenLimitError: 토큰 한도 초과
            LLMTimeoutError: 응답 타임아웃
            LLMClientError: 기타 API 호출 실패
        """
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # JSON Mode 강제: response_model이 있으면 JSON 출력 요청
        if response_model:
            payload["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(self._base_url, headers=headers, json=payload)

                # Token limit 에러 처리
                if response.status_code == 400:
                    error_body = response.json()
                    error_msg = error_body.get("error", {}).get("message", "")
                    if "token" in error_msg.lower() or "context_length" in error_msg.lower():
                        raise LLMTokenLimitError(f"토큰 한도 초과: {error_msg}")
                    raise LLMClientError(f"API 요청 실패 (400): {error_msg}")

                if response.status_code == 429:
                    logger.warning(f"Rate limited (attempt {attempt + 1}/{_MAX_RETRIES + 1})")
                    last_error = LLMClientError("Rate limit exceeded")
                    continue

                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Pydantic 모델로 파싱
                if response_model is not None:
                    return self._parse_json_response(content, response_model)

                return content

            except httpx.TimeoutException as e:
                logger.warning(f"LLM timeout (attempt {attempt + 1}/{_MAX_RETRIES + 1}): {e}")
                last_error = LLMTimeoutError(f"LLM 응답 타임아웃 ({self.timeout}초)")
                continue

            except (LLMTokenLimitError, LLMClientError):
                raise

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    logger.warning(f"LLM server error (attempt {attempt + 1}): {e}")
                    last_error = LLMClientError(f"서버 오류: {e}")
                    continue
                raise LLMClientError(f"API 오류: {e}") from e

            except Exception as e:
                raise LLMClientError(f"예기치 않은 오류: {e}") from e

        raise last_error or LLMClientError("최대 재시도 횟수 초과")

    @staticmethod
    def _parse_json_response(content: str, response_model: type[T]) -> T:
        """
        LLM 응답 문자열을 Pydantic 모델로 파싱한다.

        JSON 블록이 마크다운 코드펜스로 감싸져 있는 경우도 처리.

        Args:
            content: LLM 원본 응답 문자열
            response_model: 파싱 대상 Pydantic 모델

        Returns:
            파싱된 Pydantic 모델 인스턴스
        """
        text = content.strip()

        # 마크다운 코드펜스 제거
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # 첫 줄 (```json) 제거
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            parsed = json.loads(text)
            return response_model.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            raise LLMClientError(f"JSON 파싱 실패: {e}\n원본: {text[:500]}") from e
