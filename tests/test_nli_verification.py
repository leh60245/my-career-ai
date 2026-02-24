"""
NLI 팩트체크 파이프라인 테스트 (Evaluator + Refiner + 검증 루프)

테스트 전략:
    - evaluator: Pydantic 스키마 검증, 프롬프트 빌드, 파싱 로직 단위 테스트
    - refiner: 강제 삭제 로직, 프롬프트 빌드, 파싱 로직 단위 테스트
    - 검증 루프: Mock LLM을 활용한 E2E 시나리오 테스트
    - 환각 탐지 E2E: 원천 데이터에 없는 허위 사실 주입 -> 탐지 -> 삭제 검증

모든 테스트는 순수 단위 테스트 (DB/LLM 호출 없음, Mock 기반)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.company.engine.evaluator import (
    EVALUATOR_SYSTEM_PROMPT,
    EvaluationResult,
    HallucinationFinding,
    _build_evaluation_prompt,
    _parse_evaluation_result,
    extract_sections_for_evaluation,
)
from backend.src.company.engine.refiner import (
    REFINER_SYSTEM_PROMPT,
    RefinementResult,
    _build_refinement_prompt,
    _parse_refinement_result,
    force_delete_hallucinations,
)
from backend.src.company.schemas.career_report import CareerAnalysisReport


# ============================================================
# 공통 Test Fixtures
# ============================================================

SAMPLE_REPORT_DICT = {
    "company_overview": {
        "introduction": "테스트 기업은 IT 분야의 선도 기업입니다.",
        "industry": "IT/소프트웨어",
        "employee_count": "500명 (2025년 기준)",
        "location": "서울시 강남구",
        "financials": {"revenue": "1000억원 (2024년 기준)", "operating_profit": "100억원 (2024년 기준)"},
    },
    "corporate_culture": {
        "core_values": ["혁신", "도전"],
        "ideal_candidate": ["자기주도적 인재"],
        "work_environment": ["유연근무제", "자유로운 분위기"],
    },
    "swot_analysis": {
        "strength": ["클라우드 시장 점유율 1위", "AI 기술 경쟁력"],
        "weakness": ["글로벌 인지도 부족"],
        "opportunity": ["AI 시장 급성장"],
        "threat": ["글로벌 빅테크 경쟁 심화"],
        "so_strategy": "AI 클라우드 융합 서비스 확대",
        "wt_strategy": "글로벌 파트너십 강화",
    },
    "interview_preparation": {
        "recent_issues": ["최근 클라우드 장애 이슈 발생"],
        "pressure_questions": ["클라우드 장애 재발 방지 대책은?"],
        "expected_answers": ["이중화 시스템 구축 및 SLA 강화 전략 설명"],
    },
}

SAMPLE_SOURCE_CONTEXT = (
    "# 테스트 기업 분석을 위한 수집 데이터\n\n"
    "## [산업 애널리스트] 수집 데이터\n"
    "- 테스트 기업은 IT 소프트웨어 분야의 국내 기업입니다. [출처: DART]\n"
    "- 2024년 매출액 1000억원, 영업이익 100억원 기록 [출처: DART]\n"
    "- AI 기술 분야에 적극 투자 중 [출처: 경제뉴스]\n\n"
    "## [수석 취업 지원관] 수집 데이터\n"
    "- 혁신과 도전을 핵심 가치로 내세움 [출처: 기업 홈페이지]\n"
    "- 유연근무제 도입, 자유로운 조직문화 [출처: 블라인드]\n\n"
    "## [실무 면접관] 수집 데이터\n"
    "- 최근 클라우드 서비스 장애 발생으로 고객 불만 증가 [출처: IT뉴스]\n"
    "- 글로벌 빅테크 대비 규모 열세 [출처: 업계 분석]\n"
)


# ============================================================
# 1. Evaluator Pydantic 스키마 테스트
# ============================================================
class TestEvaluatorSchema:
    """Evaluator 관련 Pydantic 스키마 검증"""

    def test_hallucination_finding_creation(self):
        """HallucinationFinding 객체가 올바르게 생성되어야 한다."""
        finding = HallucinationFinding(
            section="swot_analysis.strength",
            statement="테스트 문장",
            reason="원천 데이터에 근거 없음",
            instruction="delete",
        )
        assert finding.section == "swot_analysis.strength"
        assert finding.instruction == "delete"

    def test_evaluation_result_no_hallucination(self):
        """환각이 없는 경우의 EvaluationResult 생성"""
        result = EvaluationResult(has_hallucination=False, findings=[], summary="모든 항목이 원천 데이터에 근거합니다.")
        assert not result.has_hallucination
        assert len(result.findings) == 0

    def test_evaluation_result_with_findings(self):
        """환각이 있는 경우의 EvaluationResult 생성"""
        findings = [
            HallucinationFinding(
                section="swot_analysis.strength",
                statement="매출 5조원 달성",
                reason="원천 데이터에 5조원이라는 수치 없음",
                instruction="rewrite",
            ),
            HallucinationFinding(
                section="interview_preparation.recent_issues",
                statement="CEO 사임 사건",
                reason="원천 데이터에 해당 사건 없음",
                instruction="delete",
            ),
        ]
        result = EvaluationResult(has_hallucination=True, findings=findings, summary="2건의 환각 발견")
        assert result.has_hallucination
        assert len(result.findings) == 2

    def test_evaluation_result_serialization(self):
        """EvaluationResult가 JSON 직렬화/역직렬화 가능해야 한다."""
        result = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.threat", statement="환각 문장", reason="근거 없음", instruction="delete"
                )
            ],
            summary="1건 발견",
        )
        json_str = result.model_dump_json(ensure_ascii=False)
        restored = EvaluationResult.model_validate_json(json_str)
        assert restored.has_hallucination
        assert len(restored.findings) == 1
        assert restored.findings[0].instruction == "delete"


# ============================================================
# 2. Evaluator 프롬프트 및 파싱 테스트
# ============================================================
class TestEvaluatorLogic:
    """Evaluator 프롬프트 빌드 및 파싱 로직 테스트"""

    def test_evaluator_system_prompt_not_empty(self):
        """Evaluator 시스템 프롬프트가 비어있지 않아야 한다."""
        assert EVALUATOR_SYSTEM_PROMPT
        assert len(EVALUATOR_SYSTEM_PROMPT) > 200
        assert "NLI" in EVALUATOR_SYSTEM_PROMPT
        assert "환각" in EVALUATOR_SYSTEM_PROMPT

    def test_build_evaluation_prompt_contains_all_parts(self):
        """평가 프롬프트에 모든 필수 요소가 포함되어야 한다."""
        prompt = _build_evaluation_prompt(
            draft_json='{"test": "data"}', source_context="원천 데이터 내용", company_name="삼성전자"
        )
        assert "삼성전자" in prompt
        assert '{"test": "data"}' in prompt
        assert "원천 데이터 내용" in prompt
        assert "NLI" in prompt

    def test_parse_evaluation_result_valid(self):
        """유효한 JSON에서 EvaluationResult을 파싱해야 한다."""
        raw = json.dumps(
            {
                "has_hallucination": True,
                "findings": [
                    {
                        "section": "swot_analysis.strength",
                        "statement": "테스트 환각",
                        "reason": "근거 없음",
                        "instruction": "delete",
                    }
                ],
                "summary": "1건 발견",
            },
            ensure_ascii=False,
        )
        result = _parse_evaluation_result(raw)
        assert result.has_hallucination
        assert len(result.findings) == 1

    def test_parse_evaluation_result_no_hallucination(self):
        """환각이 없는 결과를 올바르게 파싱해야 한다."""
        raw = json.dumps({"has_hallucination": False, "findings": [], "summary": "모든 항목 통과"})
        result = _parse_evaluation_result(raw)
        assert not result.has_hallucination
        assert len(result.findings) == 0

    def test_parse_evaluation_result_invalid_json(self):
        """잘못된 JSON이면 환각 없음으로 안전 처리해야 한다."""
        result = _parse_evaluation_result("이것은 JSON이 아닙니다")
        assert not result.has_hallucination
        assert "파싱 실패" in result.summary

    def test_parse_evaluation_result_from_markdown(self):
        """마크다운으로 감싼 JSON도 파싱해야 한다."""
        raw = '```json\n{"has_hallucination": false, "findings": [], "summary": "OK"}\n```'
        result = _parse_evaluation_result(raw)
        assert not result.has_hallucination

    def test_extract_sections_for_evaluation(self):
        """리포트에서 검증 대상 섹션을 올바르게 추출해야 한다."""
        sections = extract_sections_for_evaluation(SAMPLE_REPORT_DICT)

        assert "swot_analysis.strength" in sections
        assert "swot_analysis.weakness" in sections
        assert "swot_analysis.opportunity" in sections
        assert "swot_analysis.threat" in sections
        assert "swot_analysis.so_strategy" in sections
        assert "swot_analysis.wt_strategy" in sections
        assert "interview_preparation.recent_issues" in sections
        assert "interview_preparation.pressure_questions" in sections
        assert "interview_preparation.expected_answers" in sections

    def test_extract_sections_skips_default_values(self):
        """'정보 부족' 기본값 항목은 검증 대상에서 제외해야 한다."""
        report_with_defaults = {
            "swot_analysis": {
                "strength": ["정보 부족 - 추가 조사 필요"],
                "weakness": ["실제 약점"],
                "opportunity": [],
                "threat": [],
            },
            "interview_preparation": {
                "recent_issues": ["정보 부족 - 추가 조사 필요"],
                "pressure_questions": [],
                "expected_answers": [],
            },
        }
        sections = extract_sections_for_evaluation(report_with_defaults)

        assert "swot_analysis.strength" not in sections
        assert "swot_analysis.weakness" in sections
        assert "interview_preparation.recent_issues" not in sections


# ============================================================
# 3. Refiner Pydantic 스키마 및 프롬프트 테스트
# ============================================================
class TestRefinerSchema:
    """Refiner 관련 스키마 및 프롬프트 테스트"""

    def test_refinement_result_creation(self):
        """RefinementResult 객체가 올바르게 생성되어야 한다."""
        result = RefinementResult(
            refined_json=SAMPLE_REPORT_DICT,
            changes_made=["[swot_analysis.strength] 재작성: 클라우드 시장 점유율..."],
            forced_deletions=[],
        )
        assert result.refined_json == SAMPLE_REPORT_DICT
        assert len(result.changes_made) == 1

    def test_refiner_system_prompt_not_empty(self):
        """Refiner 시스템 프롬프트가 비어있지 않아야 한다."""
        assert REFINER_SYSTEM_PROMPT
        assert len(REFINER_SYSTEM_PROMPT) > 200
        assert "교정" in REFINER_SYSTEM_PROMPT

    def test_build_refinement_prompt_contains_all_parts(self):
        """교정 프롬프트에 모든 필수 요소가 포함되어야 한다."""
        evaluation = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength", statement="허위 사실", reason="근거 없음", instruction="delete"
                )
            ],
            summary="1건 발견",
        )
        prompt = _build_refinement_prompt(
            draft_json='{"test": "data"}', evaluation=evaluation, source_context="원천 데이터", company_name="네이버"
        )
        assert "네이버" in prompt
        assert '{"test": "data"}' in prompt
        assert "허위 사실" in prompt
        assert "원천 데이터" in prompt

    def test_parse_refinement_result_valid(self):
        """유효한 Refiner 응답을 RefinementResult로 파싱해야 한다."""
        evaluation = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength", statement="환각 문장", reason="근거 없음", instruction="rewrite"
                )
            ],
            summary="1건",
        )
        raw = json.dumps(SAMPLE_REPORT_DICT, ensure_ascii=False)
        result = _parse_refinement_result(raw, evaluation)

        assert isinstance(result, RefinementResult)
        assert result.refined_json == SAMPLE_REPORT_DICT
        assert len(result.changes_made) == 1
        assert "재작성" in result.changes_made[0]


# ============================================================
# 4. 강제 삭제 로직 테스트
# ============================================================
class TestForceDeleteHallucinations:
    """2회 반복 후 잔여 환각 강제 삭제 로직 테스트"""

    def test_force_delete_from_array(self):
        """배열 필드에서 환각 문장을 강제 삭제해야 한다."""
        report = {
            "swot_analysis": {
                "strength": ["사실 기반 강점", "환각 강점"],
                "weakness": ["약점"],
                "opportunity": [],
                "threat": [],
            },
            "interview_preparation": {},
        }
        findings = [
            HallucinationFinding(
                section="swot_analysis.strength", statement="환각 강점", reason="근거 없음", instruction="delete"
            )
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)

        assert "환각 강점" not in cleaned["swot_analysis"]["strength"]
        assert "사실 기반 강점" in cleaned["swot_analysis"]["strength"]
        assert len(deletions) == 1

    def test_force_delete_array_becomes_empty(self):
        """배열이 비게 되면 기본값을 삽입해야 한다."""
        report = {"swot_analysis": {"strength": ["유일한 환각 강점"]}, "interview_preparation": {}}
        findings = [
            HallucinationFinding(
                section="swot_analysis.strength", statement="유일한 환각 강점", reason="근거 없음", instruction="delete"
            )
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)

        assert cleaned["swot_analysis"]["strength"] == ["정보 부족 - 추가 조사 필요"]
        assert len(deletions) == 1

    def test_force_delete_string_field(self):
        """문자열 필드의 환각을 기본값으로 대체해야 한다."""
        report = {"swot_analysis": {"so_strategy": "허위 전략 내용"}, "interview_preparation": {}}
        findings = [
            HallucinationFinding(
                section="swot_analysis.so_strategy",
                statement="허위 전략 내용",
                reason="근거 없음",
                instruction="delete",
            )
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)

        assert cleaned["swot_analysis"]["so_strategy"] == "정보 부족 - 추가 조사 필요"
        assert len(deletions) == 1

    def test_force_delete_multiple_findings(self):
        """여러 환각 항목을 동시에 강제 삭제해야 한다."""
        report = {
            "swot_analysis": {"strength": ["환각1", "진짜 강점", "환각2"], "weakness": ["환각 약점"]},
            "interview_preparation": {"recent_issues": ["환각 이슈"]},
        }
        findings = [
            HallucinationFinding(
                section="swot_analysis.strength", statement="환각1", reason="없음", instruction="delete"
            ),
            HallucinationFinding(
                section="swot_analysis.strength", statement="환각2", reason="없음", instruction="delete"
            ),
            HallucinationFinding(
                section="swot_analysis.weakness", statement="환각 약점", reason="없음", instruction="delete"
            ),
            HallucinationFinding(
                section="interview_preparation.recent_issues",
                statement="환각 이슈",
                reason="없음",
                instruction="delete",
            ),
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)

        assert cleaned["swot_analysis"]["strength"] == ["진짜 강점"]
        assert cleaned["swot_analysis"]["weakness"] == ["정보 부족 - 추가 조사 필요"]
        assert cleaned["interview_preparation"]["recent_issues"] == ["정보 부족 - 추가 조사 필요"]
        assert len(deletions) == 4

    def test_force_delete_nonexistent_section(self):
        """존재하지 않는 섹션 경로는 무시해야 한다."""
        report = {"swot_analysis": {"strength": ["강점"]}, "interview_preparation": {}}
        findings = [
            HallucinationFinding(section="nonexistent.field", statement="테스트", reason="없음", instruction="delete")
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)

        assert cleaned["swot_analysis"]["strength"] == ["강점"]
        assert len(deletions) == 0

    def test_force_delete_invalid_path_format(self):
        """잘못된 경로 형식(점이 없는)은 무시해야 한다."""
        report = {"swot_analysis": {"strength": ["강점"]}, "interview_preparation": {}}
        findings = [
            HallucinationFinding(section="invalid_path", statement="테스트", reason="없음", instruction="delete")
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)
        assert len(deletions) == 0

    def test_force_delete_statement_not_found_in_array(self):
        """배열에서 대상 문장을 찾지 못하면 삭제하지 않아야 한다."""
        report = {"swot_analysis": {"strength": ["실제 강점 A", "실제 강점 B"]}, "interview_preparation": {}}
        findings = [
            HallucinationFinding(
                section="swot_analysis.strength", statement="존재하지 않는 문장", reason="없음", instruction="delete"
            )
        ]

        cleaned, deletions = force_delete_hallucinations(report, findings)

        assert len(cleaned["swot_analysis"]["strength"]) == 2
        assert len(deletions) == 0


# ============================================================
# 5. 검증 루프 통합 E2E 테스트 (Mock LLM 기반)
# ============================================================
class TestVerificationLoopE2E:
    """Mock LLM을 활용한 검증 루프 E2E 테스트"""

    @pytest.fixture
    def sample_report(self):
        """테스트용 CareerAnalysisReport 객체"""
        return CareerAnalysisReport.model_validate(SAMPLE_REPORT_DICT)

    @pytest.fixture
    def jobs_dict(self):
        """테스트용 jobs_dict"""
        return {"test-job": {"status": "PROCESSING", "progress": 75}}

    @pytest.mark.asyncio
    async def test_verification_loop_no_hallucination(self, sample_report, jobs_dict):
        """환각이 없을 때 루프가 1회만 실행되고 원본을 유지해야 한다."""
        from backend.src.company.engine.career_pipeline import _run_verification_loop

        eval_result = EvaluationResult(has_hallucination=False, findings=[], summary="모든 항목 통과")

        with patch(
            "backend.src.company.engine.career_pipeline.evaluate_report",
            new_callable=AsyncMock,
            return_value=eval_result,
        ):
            result, log = await _run_verification_loop(
                report_json=sample_report,
                source_context=SAMPLE_SOURCE_CONTEXT,
                company_name="테스트기업",
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

        assert isinstance(result, CareerAnalysisReport)
        assert log["total_loops"] == 1
        assert log["final_action"] == "passed"
        assert log["loops"][0]["action"] == "pass"

    @pytest.mark.asyncio
    async def test_verification_loop_hallucination_refined(self, sample_report, jobs_dict):
        """환각이 발견되면 Refiner를 호출하고 재검증해야 한다."""
        from backend.src.company.engine.career_pipeline import _run_verification_loop

        # 1차 Evaluator: 환각 발견
        eval_result_1 = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength",
                    statement="클라우드 시장 점유율 1위",
                    reason="원천 데이터에 점유율 순위 정보 없음",
                    instruction="rewrite",
                )
            ],
            summary="1건 환각 발견",
        )

        # 2차 Evaluator: 환각 없음 (교정 후)
        eval_result_2 = EvaluationResult(has_hallucination=False, findings=[], summary="교정 후 모든 항목 통과")

        # Refiner 결과
        refined_dict = SAMPLE_REPORT_DICT.copy()
        refined_dict["swot_analysis"] = SAMPLE_REPORT_DICT["swot_analysis"].copy()
        refined_dict["swot_analysis"]["strength"] = ["AI 기술 분야 적극 투자 중", "AI 기술 경쟁력"]

        refine_result = RefinementResult(
            refined_json=refined_dict,
            changes_made=["[swot_analysis.strength] 재작성: 클라우드 시장 점유율 1위..."],
            forced_deletions=[],
        )

        with (
            patch(
                "backend.src.company.engine.career_pipeline.evaluate_report",
                new_callable=AsyncMock,
                side_effect=[eval_result_1, eval_result_2],
            ),
            patch(
                "backend.src.company.engine.career_pipeline.refine_report",
                new_callable=AsyncMock,
                return_value=refine_result,
            ),
        ):
            result, log = await _run_verification_loop(
                report_json=sample_report,
                source_context=SAMPLE_SOURCE_CONTEXT,
                company_name="테스트기업",
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

        assert isinstance(result, CareerAnalysisReport)
        assert log["total_loops"] == 2
        assert log["loops"][0]["action"] == "refined"
        assert log["loops"][1]["action"] == "pass"

    @pytest.mark.asyncio
    async def test_verification_loop_force_delete_after_max_loops(self, sample_report, jobs_dict):
        """최대 루프 후에도 환각이 남으면 강제 삭제해야 한다."""
        from backend.src.company.engine.career_pipeline import _run_verification_loop

        hallucination_finding = HallucinationFinding(
            section="swot_analysis.strength",
            statement="클라우드 시장 점유율 1위",
            reason="원천 데이터에 근거 없음",
            instruction="delete",
        )

        # 1차: 환각 발견 -> Refiner 호출
        eval_result_1 = EvaluationResult(has_hallucination=True, findings=[hallucination_finding], summary="1건 환각")

        # 2차 (마지막 루프): 여전히 환각 -> 강제 삭제
        eval_result_2 = EvaluationResult(
            has_hallucination=True, findings=[hallucination_finding], summary="교정 후에도 환각 잔존"
        )

        # Refiner가 교정했지만 환각이 남아있는 상황
        refine_result = RefinementResult(
            refined_json=SAMPLE_REPORT_DICT, changes_made=["교정 시도"], forced_deletions=[]
        )

        with (
            patch(
                "backend.src.company.engine.career_pipeline.evaluate_report",
                new_callable=AsyncMock,
                side_effect=[eval_result_1, eval_result_2],
            ),
            patch(
                "backend.src.company.engine.career_pipeline.refine_report",
                new_callable=AsyncMock,
                return_value=refine_result,
            ),
        ):
            result, log = await _run_verification_loop(
                report_json=sample_report,
                source_context=SAMPLE_SOURCE_CONTEXT,
                company_name="테스트기업",
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

        assert isinstance(result, CareerAnalysisReport)
        assert log["total_loops"] == 2
        assert log["final_action"] == "force_deleted"
        assert log["loops"][-1]["action"] == "force_delete"
        assert len(log["loops"][-1]["forced_deletions"]) >= 1

        # 강제 삭제된 문장이 최종 리포트에 없어야 함
        assert "클라우드 시장 점유율 1위" not in result.swot_analysis.strength

    @pytest.mark.asyncio
    async def test_verification_loop_evaluator_failure(self, sample_report, jobs_dict):
        """Evaluator 호출 실패 시 루프를 종료하고 원본을 유지해야 한다."""
        from backend.src.company.engine.career_pipeline import _run_verification_loop

        with patch(
            "backend.src.company.engine.career_pipeline.evaluate_report",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API 오류"),
        ):
            result, log = await _run_verification_loop(
                report_json=sample_report,
                source_context=SAMPLE_SOURCE_CONTEXT,
                company_name="테스트기업",
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

        # 원본 유지
        assert isinstance(result, CareerAnalysisReport)
        assert log["total_loops"] == 1
        assert "evaluator_error" in log["loops"][0]

    @pytest.mark.asyncio
    async def test_verification_loop_refiner_failure(self, sample_report, jobs_dict):
        """Refiner 호출 실패 시 루프를 종료하고 현재 상태를 유지해야 한다."""
        from backend.src.company.engine.career_pipeline import _run_verification_loop

        eval_result = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength", statement="환각 문장", reason="근거 없음", instruction="rewrite"
                )
            ],
            summary="1건",
        )

        with (
            patch(
                "backend.src.company.engine.career_pipeline.evaluate_report",
                new_callable=AsyncMock,
                return_value=eval_result,
            ),
            patch(
                "backend.src.company.engine.career_pipeline.refine_report",
                new_callable=AsyncMock,
                side_effect=Exception("Refiner API 오류"),
            ),
        ):
            result, log = await _run_verification_loop(
                report_json=sample_report,
                source_context=SAMPLE_SOURCE_CONTEXT,
                company_name="테스트기업",
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

        assert isinstance(result, CareerAnalysisReport)
        assert log["loops"][0]["action"] == "refiner_failed"


# ============================================================
# 6. 환각 탐지 E2E 시나리오 테스트
# ============================================================
class TestHallucinationDetectionE2E:
    """
    고의로 원천 데이터에 없는 허위 사실을 주입하여
    Evaluator가 탐지하고 Refiner/강제 삭제가 제거하는지 검증합니다.
    """

    def test_fabricated_hallucination_detected_and_deleted(self):
        """원천 데이터에 없는 허위 사실이 강제 삭제되어야 한다."""
        # 의도적으로 원천 데이터에 없는 허위 사실 주입
        hallucinated_report = {
            "company_overview": {
                "introduction": "테스트 기업입니다.",
                "industry": "IT",
                "employee_count": "500명",
                "location": "서울",
                "financials": {"revenue": "1000억원", "operating_profit": "100억원"},
            },
            "corporate_culture": {
                "core_values": ["혁신"],
                "ideal_candidate": ["도전"],
                "work_environment": ["유연근무"],
            },
            "swot_analysis": {
                "strength": [
                    "AI 기술 경쟁력",  # 원천 데이터에 있음 (통과)
                    "2024년 글로벌 클라우드 시장 점유율 35% 달성",  # 허위 수치 (환각)
                ],
                "weakness": ["글로벌 인지도 부족"],
                "opportunity": ["AI 시장 급성장"],
                "threat": ["글로벌 빅테크 경쟁 심화"],
                "so_strategy": "AI 클라우드 융합 서비스 확대",
                "wt_strategy": "SpaceX와의 전략적 파트너십 체결 예정",  # 허위 사실 (환각)
            },
            "interview_preparation": {
                "recent_issues": [
                    "최근 클라우드 서비스 장애 발생",  # 원천 데이터에 있음 (통과)
                    "CEO가 횡령 혐의로 검찰 조사 중",  # 허위 사실 (환각)
                ],
                "pressure_questions": ["클라우드 장애 대응?"],
                "expected_answers": ["SLA 강화"],
            },
        }

        # Evaluator가 탐지한 환각 리스트 (시뮬레이션)
        findings = [
            HallucinationFinding(
                section="swot_analysis.strength",
                statement="2024년 글로벌 클라우드 시장 점유율 35% 달성",
                reason="원천 데이터에 35%라는 점유율 수치 없음",
                instruction="delete",
            ),
            HallucinationFinding(
                section="swot_analysis.wt_strategy",
                statement="SpaceX와의 전략적 파트너십 체결 예정",
                reason="원천 데이터에 SpaceX 관련 정보 없음",
                instruction="delete",
            ),
            HallucinationFinding(
                section="interview_preparation.recent_issues",
                statement="CEO가 횡령 혐의로 검찰 조사 중",
                reason="원천 데이터에 해당 사건 없음",
                instruction="delete",
            ),
        ]

        # 강제 삭제 실행
        cleaned, deletions = force_delete_hallucinations(hallucinated_report, findings)

        # 검증: 허위 사실이 모두 제거되었는지 확인
        assert "2024년 글로벌 클라우드 시장 점유율 35% 달성" not in cleaned["swot_analysis"]["strength"]
        assert "AI 기술 경쟁력" in cleaned["swot_analysis"]["strength"]  # 진짜는 유지

        assert cleaned["swot_analysis"]["wt_strategy"] == "정보 부족 - 추가 조사 필요"

        assert "CEO가 횡령 혐의로 검찰 조사 중" not in cleaned["interview_preparation"]["recent_issues"]
        assert "최근 클라우드 서비스 장애 발생" in cleaned["interview_preparation"]["recent_issues"]  # 진짜는 유지

        assert len(deletions) == 3

    @pytest.mark.asyncio
    async def test_full_pipeline_with_fabricated_hallucination(self):
        """
        전체 파이프라인 시나리오: 허위 사실 주입 -> Evaluator 탐지 -> 강제 삭제 -> 최종 리포트 정제

        - 1차 루프: Evaluator가 환각 발견 -> Refiner 교정 시도
        - 2차 루프: Evaluator가 여전히 환각 발견 -> 강제 삭제
        - 최종: 허위 사실이 제거된 정제된 리포트 반환
        """
        from backend.src.company.engine.career_pipeline import _run_verification_loop

        # 허위 사실이 포함된 초안
        hallucinated_dict = SAMPLE_REPORT_DICT.copy()
        hallucinated_dict["swot_analysis"] = SAMPLE_REPORT_DICT["swot_analysis"].copy()
        hallucinated_dict["swot_analysis"]["strength"] = [
            "AI 기술 경쟁력",
            "글로벌 시장 점유율 50% 달성",  # 허위
        ]
        hallucinated_dict["interview_preparation"] = SAMPLE_REPORT_DICT["interview_preparation"].copy()
        hallucinated_dict["interview_preparation"]["recent_issues"] = [
            "최근 클라우드 장애 이슈 발생",
            "대규모 개인정보 유출 사고 발생",  # 허위
        ]

        hallucinated_report = CareerAnalysisReport.model_validate(hallucinated_dict)

        # 1차 Evaluator: 환각 2건 발견
        eval_1 = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength",
                    statement="글로벌 시장 점유율 50% 달성",
                    reason="원천 데이터에 50% 점유율 정보 없음",
                    instruction="delete",
                ),
                HallucinationFinding(
                    section="interview_preparation.recent_issues",
                    statement="대규모 개인정보 유출 사고 발생",
                    reason="원천 데이터에 해당 사건 없음",
                    instruction="delete",
                ),
            ],
            summary="2건 환각 발견",
        )

        # Refiner: 교정 시도했지만 환각이 완전히 사라지지 않음
        refiner_dict = hallucinated_dict.copy()
        refiner_dict["swot_analysis"] = hallucinated_dict["swot_analysis"].copy()
        refiner_dict["swot_analysis"]["strength"] = [
            "AI 기술 경쟁력",
            "글로벌 시장 점유율 50% 달성",  # Refiner가 교정 실패 (여전히 환각)
        ]
        refiner_dict["interview_preparation"] = hallucinated_dict["interview_preparation"].copy()
        refiner_dict["interview_preparation"]["recent_issues"] = [
            "최근 클라우드 장애 이슈 발생",
            "대규모 개인정보 유출 사고 발생",  # 여전히 잔존
        ]

        refine_result = RefinementResult(refined_json=refiner_dict, changes_made=["교정 시도"], forced_deletions=[])

        # 2차 Evaluator: 여전히 환각 발견 -> 강제 삭제 트리거
        eval_2 = EvaluationResult(
            has_hallucination=True,
            findings=[
                HallucinationFinding(
                    section="swot_analysis.strength",
                    statement="글로벌 시장 점유율 50% 달성",
                    reason="교정 후에도 근거 없음",
                    instruction="delete",
                ),
                HallucinationFinding(
                    section="interview_preparation.recent_issues",
                    statement="대규모 개인정보 유출 사고 발생",
                    reason="교정 후에도 근거 없음",
                    instruction="delete",
                ),
            ],
            summary="2건 잔존",
        )

        jobs_dict = {"test-job": {"status": "PROCESSING", "progress": 75}}

        with (
            patch(
                "backend.src.company.engine.career_pipeline.evaluate_report",
                new_callable=AsyncMock,
                side_effect=[eval_1, eval_2],
            ),
            patch(
                "backend.src.company.engine.career_pipeline.refine_report",
                new_callable=AsyncMock,
                return_value=refine_result,
            ),
        ):
            result, log = await _run_verification_loop(
                report_json=hallucinated_report,
                source_context=SAMPLE_SOURCE_CONTEXT,
                company_name="테스트기업",
                model_provider="openai",
                job_id="test-job",
                jobs_dict=jobs_dict,
            )

        # 최종 검증: 허위 사실이 완전히 제거됨
        assert "글로벌 시장 점유율 50% 달성" not in result.swot_analysis.strength
        assert "AI 기술 경쟁력" in result.swot_analysis.strength

        assert "대규모 개인정보 유출 사고 발생" not in result.interview_preparation.recent_issues
        assert "최근 클라우드 장애 이슈 발생" in result.interview_preparation.recent_issues

        # 검증 로그 확인
        assert log["total_loops"] == 2
        assert log["final_action"] == "force_deleted"
        assert len(log["loops"]) == 2
        assert log["loops"][0]["action"] == "refined"
        assert log["loops"][1]["action"] == "force_delete"
        assert len(log["loops"][1]["forced_deletions"]) >= 2
