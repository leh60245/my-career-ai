"""
Pydantic SSOT 기반 JSON 스키마 동적 생성 유틸리티

역할:
    - CareerAnalysisReport (Pydantic V2) 모델로부터 JSON 스키마를 동적으로 추출합니다.
    - 프롬프트에 하드코딩된 JSON 스키마를 완전히 대체하여 SSOT(Single Source of Truth)를 보장합니다.
    - 향후 Pydantic 모델 필드를 변경하면 프롬프트에 자동 반영됩니다.

설계 원칙:
    - 느슨한 결합: 특정 Pydantic 모델에 종속되지 않으며, 어떤 BaseModel이든 스키마를 생성 가능합니다.
    - 향후 골든 데이터셋 DB 전환 및 스마트 하이브리드 라우팅 로직과 독립적으로 동작합니다.
"""

import json
from typing import Any, get_args, get_origin

from pydantic import BaseModel


def _get_field_example(field_type: type, description: str) -> Any:
    """
    필드 타입과 description으로부터 프롬프트용 예시 값을 생성합니다.

    Args:
        field_type: 필드의 파이썬 타입
        description: 필드의 description (Pydantic Field)

    Returns:
        JSON 직렬화 가능한 예시 값
    """
    origin = get_origin(field_type)
    args = get_args(field_type)

    # list[str] 처리
    if origin is list and args and args[0] is str:
        short_desc = description[:20] if description else "항목"
        return [f"{short_desc}1", f"{short_desc}2"]

    # 중첩된 Pydantic 모델
    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
        return _build_schema_dict(field_type)

    # str
    return f"{description} (string)" if description else "(string)"


def _build_schema_dict(model: type[BaseModel]) -> dict[str, Any]:
    """
    Pydantic 모델에서 프롬프트용 JSON 구조 딕셔너리를 재귀적으로 생성합니다.

    Args:
        model: Pydantic BaseModel 클래스

    Returns:
        필드명 -> 예시 값 딕셔너리
    """
    result: dict[str, Any] = {}

    for field_name, field_info in model.model_fields.items():
        description = field_info.description or field_name
        annotation = field_info.annotation

        if annotation is None:
            result[field_name] = f"{description} (string)"
            continue

        # Optional / Union 언래핑
        origin = get_origin(annotation)
        if origin is not None:
            args = get_args(annotation)
            # typing.Optional[X] = Union[X, None] 패턴
            non_none_args = [a for a in args if a is not type(None)]
            if non_none_args and origin is not list:
                annotation = non_none_args[0]

        result[field_name] = _get_field_example(annotation, description)

    return result


def generate_schema_prompt(model: type[BaseModel]) -> str:
    """
    Pydantic 모델에서 프롬프트에 삽입할 JSON 스키마 문자열을 동적으로 생성합니다.

    Args:
        model: 스키마를 추출할 대상 Pydantic BaseModel 클래스

    Returns:
        프롬프트 삽입용 JSON 스키마 문자열

    사용 예시:
        >>> from backend.src.company.schemas.career_report import CareerAnalysisReport
        >>> schema_text = generate_schema_prompt(CareerAnalysisReport)
    """
    schema_dict = _build_schema_dict(model)
    return json.dumps(schema_dict, ensure_ascii=False, indent=2)


def generate_evaluation_schema_prompt(model: type[BaseModel]) -> str:
    """
    Evaluator용 출력 JSON 스키마 문자열을 Pydantic 모델에서 동적으로 생성합니다.

    Args:
        model: Evaluator 출력 스키마 Pydantic 모델 (EvaluationResult)

    Returns:
        Evaluator 프롬프트 삽입용 JSON 스키마 문자열
    """
    schema_dict = _build_schema_dict(model)
    return json.dumps(schema_dict, ensure_ascii=False, indent=2)


def get_evaluable_field_paths(model: type[BaseModel], target_sections: list[str] | None = None) -> list[str]:
    """
    Pydantic 모델에서 검증 대상 필드 경로를 동적으로 추출합니다.

    Args:
        model: 스키마 모델
        target_sections: 검증 대상 섹션 이름 리스트 (None이면 모든 섹션)

    Returns:
        점(.) 구분자로 연결된 필드 경로 리스트
        (예: ["swot_analysis.strength", "swot_analysis.weakness", ...])
    """
    paths: list[str] = []

    for section_name, section_info in model.model_fields.items():
        if target_sections and section_name not in target_sections:
            continue

        section_type = section_info.annotation
        if section_type is None:
            continue

        # 중첩된 Pydantic 모델의 필드를 순회
        if isinstance(section_type, type) and issubclass(section_type, BaseModel):
            for field_name in section_type.model_fields:
                paths.append(f"{section_name}.{field_name}")

    return paths
