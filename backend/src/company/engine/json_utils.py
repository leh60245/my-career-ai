"""
JSON 파싱 방어 유틸리티

역할:
    - LLM 응답에서 순수 JSON 문자열을 안전하게 추출합니다.
    - 마크다운 백틱, 부연 설명 텍스트 등을 정규식으로 제거합니다.
    - Pydantic 모델로 스키마 검증 후 CareerAnalysisReport 객체를 반환합니다.
    - 파싱 실패 시 재시도(Retry) 로직을 제공합니다.
"""

import json
import logging
import re

from pydantic import ValidationError

from backend.src.company.schemas.career_report import CareerAnalysisReport


logger = logging.getLogger(__name__)


def extract_json_string(raw_text: str) -> str:
    """
    LLM 응답에서 순수 JSON 문자열만 추출합니다.

    방어 로직:
        1. 마크다운 코드블록(```json ... ```) 내부 추출
        2. 'Here is the JSON' 등 부연 설명 텍스트 제거
        3. 최외곽 중괄호 { ... } 범위만 추출

    Args:
        raw_text: LLM이 반환한 원본 텍스트

    Returns:
        순수 JSON 문자열

    Raises:
        ValueError: JSON 구조를 찾을 수 없는 경우
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("빈 응답입니다. JSON을 추출할 수 없습니다.")

    text = raw_text.strip()

    # 1단계: 마크다운 코드블록 내부 추출 (```json ... ``` 또는 ``` ... ```)
    code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    code_blocks = re.findall(code_block_pattern, text, re.DOTALL)
    if code_blocks:
        # 가장 긴 코드 블록을 선택 (JSON이 가장 길 확률이 높음)
        text = max(code_blocks, key=len).strip()
        logger.info("마크다운 코드블록에서 JSON 추출 완료")

    # 2단계: 최외곽 중괄호 { ... } 범위만 추출
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
        raise ValueError(f"JSON 구조(중괄호)를 찾을 수 없습니다. 원본 길이: {len(raw_text)}")

    json_str = text[first_brace : last_brace + 1]

    # 3단계: 기본 유효성 검사 (json.loads 가능 여부)
    try:
        json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"추출된 문자열이 유효한 JSON이 아닙니다: {e}") from e

    return json_str


def parse_career_report(raw_text: str) -> CareerAnalysisReport:
    """
    LLM 응답을 CareerAnalysisReport Pydantic 모델로 파싱합니다.

    Args:
        raw_text: LLM이 반환한 원본 텍스트

    Returns:
        CareerAnalysisReport 객체

    Raises:
        ValueError: JSON 추출 실패
        ValidationError: 스키마 검증 실패
    """
    json_str = extract_json_string(raw_text)
    data = json.loads(json_str)
    return CareerAnalysisReport.model_validate(data)


def safe_parse_career_report(raw_text: str) -> tuple[CareerAnalysisReport | None, str | None]:
    """
    파싱 시도 후 성공/실패를 튜플로 반환합니다. (재시도 로직에서 사용)

    Returns:
        (report, None) - 성공 시
        (None, error_message) - 실패 시
    """
    try:
        report = parse_career_report(raw_text)
        return report, None
    except ValidationError as e:
        error_msg = f"스키마 검증 실패: {e.error_count()}개 오류 - {e.errors()[:3]}"
        logger.warning(error_msg)
        return None, error_msg
    except ValueError as e:
        error_msg = f"JSON 추출 실패: {e}"
        logger.warning(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"예기치 않은 파싱 오류: {e}"
        logger.error(error_msg)
        return None, error_msg


def build_retry_prompt(original_prompt: str, error_message: str) -> str:
    """
    파싱 실패 시 LLM에게 전달할 재시도 프롬프트를 생성합니다.

    Args:
        original_prompt: 원본 프롬프트
        error_message: 이전 시도에서 발생한 오류 메시지

    Returns:
        수정된 재시도 프롬프트
    """
    retry_suffix = (
        "\n\n## 이전 응답 오류 (반드시 수정하십시오)\n"
        f"이전 응답에서 다음 오류가 발생했습니다: {error_message}\n"
        "이번에는 반드시 순수 JSON 문자열만 반환하십시오. "
        "마크다운 백틱(```)이나 추가 설명 텍스트를 절대 포함하지 마십시오. "
        "모든 required 필드를 빠짐없이 포함하고, array 타입에는 string 배열을 사용하십시오."
    )
    return original_prompt + retry_suffix
