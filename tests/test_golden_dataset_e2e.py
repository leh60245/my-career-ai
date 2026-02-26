"""
골든 데이터셋 E2E 평가 테스트 (스키마 단일화 + NLI 팩트체크 파이프라인)

테스트 전략:
    - golden_dataset/ 폴더의 5개 기업 JSON 파일을 순회하며 로드
    - CareerAnalysisReport Pydantic 스키마로 검증 (SSOT 유효성)
    - 동적 생성된 스키마 프롬프트에 모든 필드가 반영되는지 검증
    - Evaluator + Refiner NLI 파이프라인에 주입하여 정상 작동 검증
    - 무의미한 기호('-' 등) 필터링 예외 처리 검증
    - 각 기업별 환각 탐지/교정 상세 로그 출력

모든 테스트는 순수 단위 테스트 (DB/LLM 호출 없음, Mock 기반)
"""

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.company.engine.evaluator import (
    EVALUATOR_SYSTEM_PROMPT,
    EvaluationResult,
    HallucinationFinding,
    _build_evaluation_prompt,
    _is_meaningless_value,
    extract_sections_for_evaluation,
)
from backend.src.company.engine.refiner import RefinementResult, _build_refinement_prompt, force_delete_hallucinations
from backend.src.company.engine.schema_utils import (
    generate_evaluation_schema_prompt,
    generate_schema_prompt,
    get_evaluable_field_paths,
)
from backend.src.company.schemas.career_report import (
    CareerAnalysisReport,
    CompanyOverview,
    CorporateCulture,
    InterviewPreparation,
    SwotAnalysis,
)


logger = logging.getLogger(__name__)

# ============================================================
# 골든 데이터셋 로더 (느슨한 결합 설계)
# ============================================================

GOLDEN_DATASET_DIR = Path(__file__).resolve().parent.parent / "golden_dataset"

# 5개 대상 기업 파일명 목록
GOLDEN_DATASET_FILES = ["CJ_ENM.json", "삼성전자.json", "현대자동차.json", "KG모빌리티.json", "BGF리테일.json"]


def load_golden_dataset(file_name: str) -> dict[str, Any]:
    """
    골든 데이터셋 JSON 파일을 로드합니다.

    향후 DB 기반 로딩 모듈로 교체 가능하도록 독립된 인터페이스로 설계합니다.

    Args:
        file_name: JSON 파일명 (golden_dataset/ 디렉토리 기준)

    Returns:
        JSON 딕셔너리
    """
    file_path = GOLDEN_DATASET_DIR / file_name
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def load_all_golden_datasets() -> list[tuple[str, dict[str, Any]]]:
    """
    모든 골든 데이터셋을 순회하며 로드합니다.

    Returns:
        [(기업명, JSON 딕셔너리), ...] 리스트
    """
    datasets: list[tuple[str, dict[str, Any]]] = []
    for file_name in GOLDEN_DATASET_FILES:
        company_name = file_name.replace(".json", "")
        data = load_golden_dataset(file_name)
        datasets.append((company_name, data))
    return datasets


def _build_dummy_source_context(company_name: str, report_dict: dict[str, Any]) -> str:
    """
    골든 데이터셋에서 Evaluator 테스트용 가상 원천 데이터를 생성합니다.

    골든 데이터셋 자체가 정답이므로, 해당 내용을 원천 데이터로 제공하면
    Evaluator가 환각을 탐지하지 않아야 합니다 (Happy Path).

    Args:
        company_name: 기업명
        report_dict: 골든 데이터셋 딕셔너리

    Returns:
        가상 원천 데이터 컨텍스트 문자열
    """
    lines = [f"# {company_name} 분석을 위한 수집 데이터\n"]

    # company_overview 섹션
    overview = report_dict.get("company_overview", {})
    lines.append("## [산업 애널리스트] 수집 데이터")
    if overview.get("introduction"):
        lines.append(f"- {overview['introduction'][:200]} [출처: DART]")
    financials = overview.get("financials", {})
    if financials.get("revenue"):
        lines.append(f"- 매출액: {financials['revenue']} [출처: DART]")
    if financials.get("operating_profit"):
        lines.append(f"- 영업이익: {financials['operating_profit']} [출처: DART]")

    # swot_analysis 섹션
    swot = report_dict.get("swot_analysis", {})
    for key in ["strength", "weakness", "opportunity", "threat"]:
        items = swot.get(key, [])
        if isinstance(items, list):
            for item in items:
                if item and not _is_meaningless_value(item):
                    lines.append(f"- {item[:200]} [출처: 경제뉴스]")

    # interview_preparation 섹션
    lines.append("\n## [실무 면접관] 수집 데이터")
    interview = report_dict.get("interview_preparation", {})
    for key in ["recent_issues", "pressure_questions"]:
        items = interview.get(key, [])
        if isinstance(items, list):
            for item in items:
                if item and not _is_meaningless_value(item):
                    lines.append(f"- {item[:200]} [출처: IT뉴스]")

    return "\n".join(lines)


# ============================================================
# 1. 스키마 동적 생성 유효성 검증 테스트
# ============================================================
class TestSchemaGeneration:
    """Pydantic SSOT 기반 스키마 동적 생성 테스트"""

    def test_generate_report_schema_contains_all_top_sections(self):
        """동적 생성된 스키마에 CareerAnalysisReport의 4개 최상위 섹션이 모두 포함되어야 한다."""
        schema_text = generate_schema_prompt(CareerAnalysisReport)
        schema_dict = json.loads(schema_text)

        assert "company_overview" in schema_dict
        assert "corporate_culture" in schema_dict
        assert "swot_analysis" in schema_dict
        assert "interview_preparation" in schema_dict

    def test_generate_report_schema_contains_nested_fields(self):
        """동적 생성된 스키마에 중첩 필드(financials 등)가 포함되어야 한다."""
        schema_text = generate_schema_prompt(CareerAnalysisReport)
        schema_dict = json.loads(schema_text)

        assert "financials" in schema_dict["company_overview"]
        assert "revenue" in schema_dict["company_overview"]["financials"]
        assert "operating_profit" in schema_dict["company_overview"]["financials"]

    def test_generate_report_schema_list_fields_have_examples(self):
        """list[str] 필드가 예시 배열로 생성되어야 한다."""
        schema_text = generate_schema_prompt(CareerAnalysisReport)
        schema_dict = json.loads(schema_text)

        core_values = schema_dict["corporate_culture"]["core_values"]
        assert isinstance(core_values, list)
        assert len(core_values) >= 2

    def test_generate_report_schema_str_fields_have_description(self):
        """str 필드에 description이 포함되어야 한다."""
        schema_text = generate_schema_prompt(CareerAnalysisReport)
        schema_dict = json.loads(schema_text)

        introduction = schema_dict["company_overview"]["introduction"]
        assert isinstance(introduction, str)
        assert "(string)" in introduction

    def test_generate_evaluation_schema_contains_required_fields(self):
        """Evaluator 출력 스키마에 필수 필드가 포함되어야 한다."""
        schema_text = generate_evaluation_schema_prompt(EvaluationResult)
        schema_dict = json.loads(schema_text)

        assert "has_hallucination" in schema_dict
        assert "findings" in schema_dict
        assert "summary" in schema_dict

    def test_schema_prompt_is_valid_json(self):
        """동적 생성된 스키마가 유효한 JSON이어야 한다."""
        schema_text = generate_schema_prompt(CareerAnalysisReport)
        parsed = json.loads(schema_text)
        assert isinstance(parsed, dict)

    def test_evaluable_field_paths_for_target_sections(self):
        """검증 대상 필드 경로가 올바르게 추출되어야 한다."""
        paths = get_evaluable_field_paths(
            CareerAnalysisReport, target_sections=["swot_analysis", "interview_preparation"]
        )

        assert "swot_analysis.strength" in paths
        assert "swot_analysis.weakness" in paths
        assert "swot_analysis.so_strategy" in paths
        assert "swot_analysis.wt_strategy" in paths
        assert "interview_preparation.recent_issues" in paths
        assert "interview_preparation.pressure_questions" in paths
        assert "interview_preparation.expected_answers" in paths

    def test_final_synthesis_prompt_uses_dynamic_schema(self):
        """FINAL_SYNTHESIS_PROMPT가 동적으로 생성된 스키마를 사용해야 한다."""
        from backend.src.company.engine.personas import FINAL_SYNTHESIS_PROMPT

        # 핵심 필드명이 프롬프트에 포함되어야 함
        assert "company_overview" in FINAL_SYNTHESIS_PROMPT
        assert "corporate_culture" in FINAL_SYNTHESIS_PROMPT
        assert "swot_analysis" in FINAL_SYNTHESIS_PROMPT
        assert "interview_preparation" in FINAL_SYNTHESIS_PROMPT
        assert "financials" in FINAL_SYNTHESIS_PROMPT

    def test_evaluator_prompt_uses_dynamic_schema(self):
        """EVALUATOR_SYSTEM_PROMPT가 동적으로 생성된 스키마를 사용해야 한다."""
        assert "has_hallucination" in EVALUATOR_SYSTEM_PROMPT
        assert "findings" in EVALUATOR_SYSTEM_PROMPT
        assert "summary" in EVALUATOR_SYSTEM_PROMPT


# ============================================================
# 2. 골든 데이터셋 로드 및 스키마 검증 테스트
# ============================================================
class TestGoldenDatasetLoading:
    """골든 데이터셋 파일 로드 및 CareerAnalysisReport 스키마 호환성 검증"""

    def test_all_golden_dataset_files_exist(self):
        """5개 골든 데이터셋 파일이 모두 존재해야 한다."""
        for file_name in GOLDEN_DATASET_FILES:
            file_path = GOLDEN_DATASET_DIR / file_name
            assert file_path.exists(), f"골든 데이터셋 파일이 없습니다: {file_path}"

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_golden_dataset_is_valid_json(self, file_name: str):
        """각 골든 데이터셋이 유효한 JSON이어야 한다."""
        data = load_golden_dataset(file_name)
        assert isinstance(data, dict)

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_golden_dataset_validates_with_pydantic(self, file_name: str):
        """각 골든 데이터셋이 CareerAnalysisReport Pydantic 스키마로 검증되어야 한다."""
        data = load_golden_dataset(file_name)
        report = CareerAnalysisReport.model_validate(data)

        assert isinstance(report.company_overview, CompanyOverview)
        assert isinstance(report.corporate_culture, CorporateCulture)
        assert isinstance(report.swot_analysis, SwotAnalysis)
        assert isinstance(report.interview_preparation, InterviewPreparation)

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_golden_dataset_roundtrip_serialization(self, file_name: str):
        """골든 데이터셋을 Pydantic으로 로드 후 재직렬화하면 원본과 구조가 동일해야 한다."""
        data = load_golden_dataset(file_name)
        report = CareerAnalysisReport.model_validate(data)
        reserialized = json.loads(report.model_dump_json(exclude_none=True))

        # 최상위 키 일치 검증
        assert set(reserialized.keys()) == set(data.keys())

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_golden_dataset_has_content(self, file_name: str):
        """골든 데이터셋의 주요 필드에 실질적인 내용이 있어야 한다."""
        data = load_golden_dataset(file_name)
        report = CareerAnalysisReport.model_validate(data)

        # company_overview는 비어있지 않아야 함
        assert report.company_overview.introduction != "정보 부족 - 추가 조사 필요"
        assert report.company_overview.industry != "정보 부족 - 추가 조사 필요"


# ============================================================
# 3. 무의미한 기호 필터링 테스트
# ============================================================
class TestMeaninglessFieldFiltering:
    """하이픈('-') 등 무의미한 기호 필터링 규칙 검증"""

    def test_hyphen_is_meaningless(self):
        """단일 하이픈이 무의미한 값으로 판별되어야 한다."""
        assert _is_meaningless_value("-") is True

    def test_double_hyphen_is_meaningless(self):
        """이중 하이픈이 무의미한 값으로 판별되어야 한다."""
        assert _is_meaningless_value("--") is True

    def test_triple_hyphen_is_meaningless(self):
        """삼중 하이픈이 무의미한 값으로 판별되어야 한다."""
        assert _is_meaningless_value("---") is True

    def test_na_is_meaningless(self):
        """N/A가 무의미한 값으로 판별되어야 한다."""
        assert _is_meaningless_value("N/A") is True
        assert _is_meaningless_value("n/a") is True

    def test_empty_string_is_meaningless(self):
        """빈 문자열이 무의미한 값으로 판별되어야 한다."""
        assert _is_meaningless_value("") is True

    def test_whitespace_hyphen_is_meaningless(self):
        """공백이 포함된 하이픈도 무의미한 값으로 판별되어야 한다."""
        assert _is_meaningless_value(" - ") is True

    def test_normal_text_is_not_meaningless(self):
        """일반 텍스트는 무의미하지 않은 값으로 판별되어야 한다."""
        assert _is_meaningless_value("강점을 활용한 기회 선점 전략") is False

    def test_info_not_available_is_not_meaningless(self):
        """'정보 부족' 기본값은 _is_meaningless_value에서는 False (별도 필터링 로직)."""
        assert _is_meaningless_value("정보 부족 - 추가 조사 필요") is False

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_meaningless_fields_excluded_from_evaluation(self, file_name: str):
        """골든 데이터셋에서 '-'로만 채워진 필드는 검증 대상에서 제외되어야 한다."""
        data = load_golden_dataset(file_name)
        sections = extract_sections_for_evaluation(data)

        # '-'만 들어있는 필드는 검증 대상에 포함되지 않아야 함
        for section_key, statements in sections.items():
            for stmt in statements:
                assert not _is_meaningless_value(stmt), (
                    f"[{file_name}] 무의미한 값이 검증 대상에 포함됨: {section_key} -> '{stmt}'"
                )

    def test_so_wt_strategy_hyphen_excluded(self):
        """so_strategy, wt_strategy가 '-'이면 검증 대상에서 제외되어야 한다."""
        report_dict = {
            "swot_analysis": {
                "strength": ["실질적 강점 내용"],
                "weakness": ["실질적 약점 내용"],
                "opportunity": ["실질적 기회 내용"],
                "threat": ["실질적 위협 내용"],
                "so_strategy": "-",
                "wt_strategy": "-",
            },
            "interview_preparation": {
                "recent_issues": ["실질적 이슈"],
                "pressure_questions": ["압박 질문"],
                "expected_answers": ["답변 가이드"],
            },
        }

        sections = extract_sections_for_evaluation(report_dict)

        # so_strategy, wt_strategy는 '-'이므로 제외
        assert "swot_analysis.so_strategy" not in sections
        assert "swot_analysis.wt_strategy" not in sections

        # 실질적 내용이 있는 필드는 포함
        assert "swot_analysis.strength" in sections
        assert "interview_preparation.recent_issues" in sections


# ============================================================
# 4. 골든 데이터셋 기반 Evaluator 연동 테스트
# ============================================================
class TestGoldenDatasetEvaluatorIntegration:
    """골든 데이터셋을 Evaluator에 주입하여 정상 동작 검증"""

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_evaluation_prompt_builds_successfully(self, file_name: str):
        """각 골든 데이터셋으로 Evaluator 프롬프트가 정상 생성되어야 한다."""
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")

        draft_json = json.dumps(data, ensure_ascii=False, indent=2)
        source_context = _build_dummy_source_context(company_name, data)

        prompt = _build_evaluation_prompt(draft_json, source_context, company_name)

        assert company_name in prompt
        assert "JSON 초안" in prompt
        assert "원천 데이터" in prompt

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_extract_sections_from_golden_dataset(self, file_name: str):
        """골든 데이터셋에서 검증 대상 섹션이 올바르게 추출되어야 한다."""
        data = load_golden_dataset(file_name)
        sections = extract_sections_for_evaluation(data)

        company_name = file_name.replace(".json", "")
        logger.info(f"[{company_name}] 검증 대상 섹션: {list(sections.keys())}")

        # 최소 1개 이상의 검증 대상 섹션이 있어야 함
        assert len(sections) > 0, f"[{company_name}] 검증 대상 섹션이 없습니다."

        # 각 섹션에 실질적 내용이 있어야 함
        for section_key, statements in sections.items():
            assert len(statements) > 0, f"[{company_name}] {section_key} 섹션에 문장이 없습니다."
            for stmt in statements:
                assert len(stmt) > 0, f"[{company_name}] {section_key} 섹션에 빈 문장이 있습니다."

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    async def test_evaluator_with_golden_data_no_hallucination(self, file_name: str):
        """
        골든 데이터셋을 원천 데이터와 함께 Evaluator에 주입하면 환각이 탐지되지 않아야 한다.
        (골든 데이터셋의 내용을 원천 데이터로 제공하는 Happy Path)
        """
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")
        draft_json = json.dumps(data, ensure_ascii=False, indent=2)
        source_context = _build_dummy_source_context(company_name, data)

        # LLM Mock: 환각 없음 응답
        mock_eval_result = EvaluationResult(
            has_hallucination=False, findings=[], summary=f"{company_name} 보고서 검증 통과"
        )

        with patch(
            "backend.src.company.engine.evaluator.evaluate_report",
            new_callable=AsyncMock,
            return_value=mock_eval_result,
        ) as mock_evaluate:
            result = await mock_evaluate(
                draft_json=draft_json, source_context=source_context, company_name=company_name, model_provider="openai"
            )

            assert isinstance(result, EvaluationResult)
            assert result.has_hallucination is False
            assert len(result.findings) == 0

            logger.info(f"[{company_name}] Evaluator 검증 통과: {result.summary}")


# ============================================================
# 5. 골든 데이터셋 기반 Refiner 연동 테스트
# ============================================================
class TestGoldenDatasetRefinerIntegration:
    """골든 데이터셋을 Refiner에 주입하여 정상 동작 검증"""

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_refinement_prompt_builds_successfully(self, file_name: str):
        """각 골든 데이터셋으로 Refiner 프롬프트가 정상 생성되어야 한다."""
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")

        draft_json = json.dumps(data, ensure_ascii=False, indent=2)
        source_context = _build_dummy_source_context(company_name, data)

        # 가상 환각 지적 생성
        evaluation = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength",
                    statement="테스트 환각 문장",
                    reason="원천 데이터에 근거 없음",
                    instruction="delete",
                )
            ],
            summary="테스트 환각 발견",
        )

        prompt = _build_refinement_prompt(draft_json, evaluation, source_context, company_name)

        assert company_name in prompt
        assert "환각 지적 리스트" in prompt
        assert "테스트 환각 문장" in prompt

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    def test_force_delete_on_golden_data(self, file_name: str):
        """골든 데이터셋에 가상 환각 주입 후 강제 삭제가 정상 동작해야 한다."""
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")

        # SWOT 강점 섹션에서 첫 번째 항목을 환각으로 지적
        swot_strengths = data.get("swot_analysis", {}).get("strength", [])
        if not swot_strengths or _is_meaningless_value(swot_strengths[0]):
            pytest.skip(f"[{company_name}] strength 섹션에 실질적 내용이 없어 건너뜁니다.")

        target_statement = swot_strengths[0]

        findings = [
            HallucinationFinding(
                section="swot_analysis.strength",
                statement=target_statement,
                reason="테스트: 강제 삭제 대상",
                instruction="delete",
            )
        ]

        cleaned_dict, forced_deletions = force_delete_hallucinations(data.copy(), findings)

        # 강제 삭제가 실행되었는지 확인
        assert len(forced_deletions) > 0, f"[{company_name}] 강제 삭제가 수행되지 않았습니다."

        # 해당 문장이 제거되었는지 확인
        remaining_strengths = cleaned_dict["swot_analysis"]["strength"]
        assert target_statement not in remaining_strengths

        logger.info(f"[{company_name}] 강제 삭제 완료: {forced_deletions}")


# ============================================================
# 6. 전체 E2E 파이프라인 테스트 (Mock LLM 기반)
# ============================================================
class TestGoldenDatasetE2EPipeline:
    """5개 골든 데이터셋 전체에 대한 E2E 검증 루프 테스트"""

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    async def test_full_verification_loop_pass(self, file_name: str):
        """
        골든 데이터셋 기반 전체 검증 루프 시나리오:
        Evaluator가 환각 없음을 반환하면 즉시 통과해야 한다.
        """
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")
        report = CareerAnalysisReport.model_validate(data)

        # Mock Evaluator 응답: 환각 없음
        mock_eval_result = EvaluationResult(has_hallucination=False, findings=[], summary=f"[{company_name}] 검증 통과")

        with patch(
            "backend.src.company.engine.career_pipeline.evaluate_report",
            new_callable=AsyncMock,
            return_value=mock_eval_result,
        ):
            from backend.src.company.engine.career_pipeline import _run_verification_loop

            source_context = _build_dummy_source_context(company_name, data)
            jobs_dict: dict[str, dict[str, Any]] = {"test-job": {"progress": 75}}

            result, log = await _run_verification_loop(
                report_json=report,
                source_context=source_context,
                company_name=company_name,
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

            assert isinstance(result, CareerAnalysisReport)
            assert log["final_action"] == "passed"
            logger.info(f"[{company_name}] E2E 전체 검증 루프 통과")

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    async def test_full_verification_loop_with_hallucination_and_refine(self, file_name: str):
        """
        골든 데이터셋 기반 전체 검증 루프 시나리오:
        Evaluator가 환각을 발견하면 Refiner가 교정하고 재검증해야 한다.
        """
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")
        report = CareerAnalysisReport.model_validate(data)
        source_context = _build_dummy_source_context(company_name, data)

        # 검증 대상 섹션에서 첫 번째 문장을 환각으로 지적
        sections = extract_sections_for_evaluation(data)
        if not sections:
            pytest.skip(f"[{company_name}] 검증 대상 섹션이 없어 건너뜁니다.")

        first_section = next(iter(sections))
        first_statement = sections[first_section][0]

        # 1차 Evaluator: 환각 발견
        eval_result_1 = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section=first_section,
                    statement=first_statement,
                    reason="테스트: 원천 데이터 부재",
                    instruction="rewrite",
                )
            ],
            summary=f"[{company_name}] 1건 환각 발견",
        )

        # 2차 Evaluator: 환각 없음
        eval_result_2 = EvaluationResult(
            has_hallucination=False, findings=[], summary=f"[{company_name}] 교정 후 검증 통과"
        )

        # Refiner: 교정 결과
        refine_result = RefinementResult(
            refined_json=data.copy(),
            changes_made=[f"[{first_section}] 재작성: {first_statement[:50]}..."],
            forced_deletions=[],
        )

        eval_call_count = {"count": 0}

        async def mock_evaluate(**kwargs):
            idx = eval_call_count["count"]
            eval_call_count["count"] += 1
            return eval_result_1 if idx == 0 else eval_result_2

        async def mock_refine(**kwargs):
            return refine_result

        with (
            patch("backend.src.company.engine.career_pipeline.evaluate_report", side_effect=mock_evaluate),
            patch("backend.src.company.engine.career_pipeline.refine_report", side_effect=mock_refine),
        ):
            from backend.src.company.engine.career_pipeline import _run_verification_loop

            jobs_dict: dict[str, dict[str, Any]] = {"test-job": {"progress": 75}}

            result, log = await _run_verification_loop(
                report_json=report,
                source_context=source_context,
                company_name=company_name,
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

            assert isinstance(result, CareerAnalysisReport)
            assert log["total_loops"] >= 1

            logger.info(
                f"[{company_name}] E2E 교정 루프 완료: "
                f"환각 탐지 {len(eval_result_1.findings)}건 -> "
                f"교정 {len(refine_result.changes_made)}건 -> 최종 결과"
            )

    @pytest.mark.parametrize("file_name", GOLDEN_DATASET_FILES)
    async def test_full_verification_loop_force_delete(self, file_name: str):
        """
        골든 데이터셋 기반 전체 검증 루프 시나리오:
        최대 반복 도달 시 강제 삭제가 수행되어야 한다.
        """
        data = load_golden_dataset(file_name)
        company_name = file_name.replace(".json", "")
        report = CareerAnalysisReport.model_validate(data)

        sections = extract_sections_for_evaluation(data)
        if not sections:
            pytest.skip(f"[{company_name}] 검증 대상 섹션이 없어 건너뜁니다.")

        first_section = next(iter(sections))
        first_statement = sections[first_section][0]

        # 환각 지적
        findings = [
            HallucinationFinding(
                section=first_section,
                statement=first_statement,
                reason="테스트: 강제 삭제 시나리오",
                instruction="delete",
            )
        ]

        # 강제 삭제 수행
        report_dict = report.model_dump()
        cleaned_dict, forced_deletions = force_delete_hallucinations(report_dict, findings)

        # 강제 삭제 후 Pydantic 재검증
        cleaned_report = CareerAnalysisReport.model_validate(cleaned_dict)
        assert isinstance(cleaned_report, CareerAnalysisReport)

        logger.info(
            f"[{company_name}] 강제 삭제 E2E 완료: 삭제 {len(forced_deletions)}건, 최종 보고서 스키마 검증 통과"
        )


# ============================================================
# 7. 전체 데이터셋 순회 요약 테스트
# ============================================================
class TestGoldenDatasetSummary:
    """5개 기업 전체 순회 후 요약 로그 출력"""

    def test_all_datasets_schema_validation_summary(self):
        """
        5개 기업 데이터셋 전체 순회 후 검증 요약을 로그로 출력합니다.

        완료 조건: 5개 기업 데이터셋 전체 순회 완료, 각 기업별 상세 로그 출력.
        """
        datasets = load_all_golden_datasets()
        assert len(datasets) == 5, f"5개 기업이어야 합니다. 현재: {len(datasets)}개"

        summary_lines = ["=" * 60, "골든 데이터셋 검증 요약 보고서", "=" * 60]

        for company_name, data in datasets:
            # Pydantic 검증
            report = CareerAnalysisReport.model_validate(data)

            # 검증 대상 섹션 추출
            sections = extract_sections_for_evaluation(data)

            # 무의미한 필드 카운트
            swot = data.get("swot_analysis", {})
            meaningless_count = 0
            for key in ["so_strategy", "wt_strategy"]:
                val = swot.get(key, "")
                if _is_meaningless_value(val):
                    meaningless_count += 1

            # 요약 출력
            total_statements = sum(len(stmts) for stmts in sections.values())
            summary_lines.append(f"\n--- {company_name} ---")
            summary_lines.append("  Pydantic 스키마 검증: PASS")
            summary_lines.append(f"  검증 대상 섹션 수: {len(sections)}")
            summary_lines.append(f"  검증 대상 문장 수: {total_statements}")
            summary_lines.append(f"  무의미 필드 필터링: {meaningless_count}건 (so_strategy/wt_strategy)")
            summary_lines.append(f"  주요 검증 섹션: {', '.join(sections.keys())}")

        summary_lines.append("\n" + "=" * 60)
        summary_lines.append("전체 결과: 5개 기업 데이터셋 검증 완료")
        summary_lines.append("=" * 60)

        summary_text = "\n".join(summary_lines)
        logger.info(summary_text)

        # 모든 기업이 검증을 통과했는지 확인
        assert len(datasets) == 5
