"""
품질 검수 서비스 (Quality Inspector)

CSV 품질 기준(기업분석 품질검수 기준)을 기반으로
생성된 리포트의 각 섹션을 A/B/C 등급으로 평가합니다.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import dspy


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. 품질 검수 기준 (CSV → 구조화 데이터)
# ──────────────────────────────────────────────────────────────


@dataclass
class SectionCriteria:
    """섹션별 품질 평가 기준"""

    section_name: str
    description: str
    criteria_types: list[str]  # 정확성, 최신성, 논리성/효용성
    grade_a: str
    grade_b: str
    grade_c: str


# CSV에서 추출한 구조화된 평가 기준
QUALITY_CRITERIA: list[SectionCriteria] = [
    # 1. 기업소개
    SectionCriteria(
        section_name="기업소개",
        description="기업에 대한 간단한 소개",
        criteria_types=["정확성", "논리성/효용성"],
        grade_a="신뢰할 수 있는 출처(DART, NICE, 기업 홈페이지)를 기반으로 작성하되, 해당 기업에 Focus를 맞춘 분석 내용을 제시하는 경우",
        grade_b="주요 언론사 뉴스/기사 정보까지 참고하여 작성하되, 해당 기업이 속한 산업과 업종에 대한 일반적인 내용을 포함하는 경우",
        grade_c="정확성(C등급) 기준에 해당하는 출처(블로그, 개인 웹사이트)를 바탕으로 작성된 내용",
    ),
    # 2. 기업개요
    SectionCriteria(
        section_name="기업개요",
        description="기업에 대한 기본적인 정보 (업종, 직원수, 본사위치, 비전, 인재상 등)",
        criteria_types=["정확성", "최신성"],
        grade_a="사업자등록 표준분류코드를 직관적으로 표현, 직전 반기 이내 기준 정보, 홈페이지 일치 여부 확인",
        grade_b="직관적 표현이나 부분적 정보, 직전 년도 기준 정보",
        grade_c="표준분류코드 그대로, 전전년도 기준 정보",
    ),
    # 3. 주요 재무제표
    SectionCriteria(
        section_name="재무제표",
        description="매출액, 영업이익, 당기순이익 등 주요 재무 수치",
        criteria_types=["정확성", "최신성"],
        grade_a="DART 전자공시 기준, 전년도 말 재무제표와 일치",
        grade_b="수치가 대략적으로 일치하나 기준일이 약간 다름",
        grade_c="수치가 부정확하거나 출처가 불분명",
    ),
    # 4. 사업분석 (3C4P) - Company
    SectionCriteria(
        section_name="주요사업(Company)",
        description="사업에 대한 소개, 설명, 특징, 시장 내 점유율, 기술력",
        criteria_types=["정확성", "최신성", "논리성/효용성"],
        grade_a="대표 사업부터 최근 진출한 신규사업까지 포괄, 특징적인 부분을 구체적으로 언급",
        grade_b="대표 사업 설명은 있으나 피상적인 수준",
        grade_c="대표 사업만 설명하고 최근 진출 사업에 대한 설명 부족",
    ),
    # 4. 사업분석 - Customer
    SectionCriteria(
        section_name="주요고객(Customer)",
        description="주 타겟 고객층",
        criteria_types=["정확성", "논리성/효용성"],
        grade_a="인구통계학적 특성 + 고객 니즈/라이프스타일 반영한 핵심 타겟 구체적 정의",
        grade_b="20대~50대, B2C/B2B 같이 범위가 너무 넓은 경우",
        grade_c="고객층 정의가 없거나 비즈니스 모델과 맞지 않는 경우",
    ),
    # 4. 사업분석 - Competitor
    SectionCriteria(
        section_name="경쟁사(Competitor)",
        description="주요사업 기준 경쟁사",
        criteria_types=["정확성", "논리성/효용성"],
        grade_a="주요 사업영역에서 실질적으로 경쟁하는 기업 2~3곳 선정",
        grade_b="사업 연관성이 낮거나 체급 차이가 큰 기업 선정",
        grade_c="경쟁사가 아닌 단순 포털 검색 연관 기업 나열",
    ),
    # 4. 사업분석 - Product
    SectionCriteria(
        section_name="제품/서비스(Product)",
        description="주요 제품 또는 서비스",
        criteria_types=["정확성", "논리성/효용성"],
        grade_a="주요사업과 관계된 제품/서비스를 포괄적으로 제시",
        grade_b="일부 사업에 대한 내용만 포함",
        grade_c="주요사업과 무관한 제품/서비스 제시",
    ),
    # 5. SWOT 분석
    SectionCriteria(
        section_name="SWOT 분석",
        description="강점(S), 약점(W), 기회(O), 위협(T), SO/WT 전략",
        criteria_types=["정확성", "논리성/효용성"],
        grade_a="구체적 수치나 팩트 기반 분석, 인과관계 명확, 실행 가능한 전략 제시",
        grade_b="일반적이고 정성적인 표현 위주, 연결고리가 부재한 거시적 환경만 서술",
        grade_c="앞의 3C4P와 관련성이 떨어지는 내용을 기술",
    ),
]


# ──────────────────────────────────────────────────────────────
# 2. 평가 결과 데이터 클래스
# ──────────────────────────────────────────────────────────────


@dataclass
class SectionGrade:
    """섹션 평가 결과"""

    section_name: str
    grade: str  # A, B, C, or N/A
    reason: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """전체 품질 검수 결과"""

    overall_grade: str
    section_grades: list[SectionGrade]
    summary: str
    total_sections_evaluated: int = 0


# ──────────────────────────────────────────────────────────────
# 3. dspy Signature for LLM Evaluation
# ──────────────────────────────────────────────────────────────


class EvaluateSection(dspy.Signature):
    """당신은 기업분석 리포트의 품질을 검수하는 전문 평가자입니다.
    주어진 섹션 내용을 평가 기준에 따라 A, B, C 등급으로 평가하세요.

    반드시 아래 JSON 형식으로만 응답하세요:
    {"grade": "A|B|C", "reason": "평가 근거 (2-3문장)", "suggestions": ["개선 제안1", "개선 제안2"]}
    """

    section_name = dspy.InputField(prefix="평가 대상 섹션: ", format=str)
    section_content = dspy.InputField(prefix="섹션 내용:\n", format=str)
    criteria = dspy.InputField(prefix="평가 기준:\n", format=str)
    evaluation = dspy.OutputField(prefix="평가 결과 (JSON):\n", format=str)


# ──────────────────────────────────────────────────────────────
# 4. 품질 검수 서비스
# ──────────────────────────────────────────────────────────────


class QualityInspector:
    """생성된 리포트를 품질 기준에 따라 LLM으로 평가합니다."""

    def __init__(self, lm: dspy.dsp.LM | None = None):
        self.lm = lm
        self.evaluator = dspy.Predict(EvaluateSection)

    def evaluate_report(self, article_text: str) -> QualityReport:
        """
        리포트 전문을 받아 섹션별로 평가합니다.

        Args:
            article_text: 생성된 리포트의 전체 마크다운 텍스트

        Returns:
            QualityReport: 전체 품질 평가 결과
        """
        sections = self._split_into_sections(article_text)
        section_grades: list[SectionGrade] = []

        for criteria in QUALITY_CRITERIA:
            # 해당 섹션 찾기 (퍼지 매칭)
            section_content = self._find_matching_section(criteria.section_name, sections)

            if not section_content:
                section_grades.append(
                    SectionGrade(
                        section_name=criteria.section_name,
                        grade="N/A",
                        reason="해당 섹션을 리포트에서 찾을 수 없습니다.",
                        suggestions=["해당 섹션을 추가하세요."],
                    )
                )
                continue

            # LLM 평가 실행
            grade = self._evaluate_section(criteria, section_content)
            section_grades.append(grade)

        # 전체 등급 계산
        overall_grade = self._calculate_overall_grade(section_grades)
        total_evaluated = sum(1 for g in section_grades if g.grade != "N/A")

        summary = self._generate_summary(section_grades, overall_grade)

        return QualityReport(
            overall_grade=overall_grade,
            section_grades=section_grades,
            summary=summary,
            total_sections_evaluated=total_evaluated,
        )

    def _split_into_sections(self, text: str) -> dict[str, str]:
        """마크다운 텍스트를 헤딩 기준으로 섹션으로 분리합니다."""
        sections: dict[str, str] = {}
        current_heading = ""
        current_content: list[str] = []

        for line in text.split("\n"):
            heading_match = re.match(r"^(#{1,3})\s+(.+)", line)
            if heading_match:
                # 이전 섹션 저장
                if current_heading:
                    sections[current_heading] = "\n".join(current_content).strip()

                current_heading = heading_match.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        # 마지막 섹션 저장
        if current_heading:
            sections[current_heading] = "\n".join(current_content).strip()

        return sections

    def _find_matching_section(self, criteria_name: str, sections: dict[str, str]) -> str | None:
        """품질 기준 섹션명과 리포트 섹션의 퍼지 매칭"""
        # 키워드 매핑
        keywords_map: dict[str, list[str]] = {
            "기업소개": ["기업소개", "기업 소개", "회사 소개", "회사소개", "소개"],
            "기업개요": ["기업개요", "기업 개요", "회사 개요", "회사개요", "개요"],
            "재무제표": ["재무", "재무제표", "재무 제표", "매출", "영업이익"],
            "주요사업(Company)": ["주요사업", "주요 사업", "사업분석", "company", "사업 소개"],
            "주요고객(Customer)": ["주요고객", "주요 고객", "고객", "customer", "타겟"],
            "경쟁사(Competitor)": ["경쟁사", "경쟁 사", "competitor", "경쟁"],
            "제품/서비스(Product)": ["제품", "서비스", "product", "제품/서비스"],
            "SWOT 분석": ["swot", "강점", "약점", "기회", "위협", "so전략", "wt전략"],
        }

        keywords = keywords_map.get(criteria_name, [criteria_name])

        # 전체 섹션에서 키워드 매칭
        matched_contents: list[str] = []
        for section_title, content in sections.items():
            title_lower = section_title.lower()
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    matched_contents.append(f"## {section_title}\n{content}")
                    break

        if matched_contents:
            return "\n\n".join(matched_contents)

        return None

    def _evaluate_section(self, criteria: SectionCriteria, content: str) -> SectionGrade:
        """LLM을 사용하여 단일 섹션을 평가합니다."""
        criteria_text = (
            f"섹션: {criteria.section_name}\n"
            f"설명: {criteria.description}\n"
            f"평가 기준 유형: {', '.join(criteria.criteria_types)}\n\n"
            f"[A등급 기준]\n{criteria.grade_a}\n\n"
            f"[B등급 기준]\n{criteria.grade_b}\n\n"
            f"[C등급 기준]\n{criteria.grade_c}"
        )

        # 내용이 너무 길면 앞부분만 사용 (토큰 절약)
        truncated_content = content[:3000] if len(content) > 3000 else content

        try:
            if self.lm:
                with dspy.settings.context(lm=self.lm):
                    result = self.evaluator(
                        section_name=criteria.section_name, section_content=truncated_content, criteria=criteria_text
                    )
            else:
                result = self.evaluator(
                    section_name=criteria.section_name, section_content=truncated_content, criteria=criteria_text
                )

            return self._parse_evaluation(criteria.section_name, result.evaluation)

        except Exception as e:
            logger.error(f"Section evaluation failed for {criteria.section_name}: {e}")
            return SectionGrade(
                section_name=criteria.section_name,
                grade="N/A",
                reason=f"평가 실행 중 오류 발생: {str(e)}",
                suggestions=[],
            )

    def _parse_evaluation(self, section_name: str, raw_output: str) -> SectionGrade:
        """LLM 출력을 파싱하여 SectionGrade로 변환합니다."""
        try:
            # JSON 블록 추출
            json_match = re.search(r"\{[^}]+\}", raw_output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                grade = data.get("grade", "N/A").upper()
                if grade not in ("A", "B", "C"):
                    grade = "N/A"

                return SectionGrade(
                    section_name=section_name,
                    grade=grade,
                    reason=data.get("reason", ""),
                    suggestions=data.get("suggestions", []),
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: 등급만이라도 추출
        grade = "N/A"
        for g in ["A", "B", "C"]:
            if g in raw_output.upper().split():
                grade = g
                break

        return SectionGrade(section_name=section_name, grade=grade, reason=raw_output[:200], suggestions=[])

    def _calculate_overall_grade(self, grades: list[SectionGrade]) -> str:
        """섹션별 등급을 종합하여 전체 등급을 산출합니다."""
        grade_scores = {"A": 3, "B": 2, "C": 1}
        scored = [(g.section_name, grade_scores.get(g.grade, 0)) for g in grades if g.grade != "N/A"]

        if not scored:
            return "N/A"

        avg_score = sum(s for _, s in scored) / len(scored)

        if avg_score >= 2.5:
            return "A"
        elif avg_score >= 1.5:
            return "B"
        else:
            return "C"

    def _generate_summary(self, grades: list[SectionGrade], overall: str) -> str:
        """평가 결과 요약문을 생성합니다."""
        evaluated = [g for g in grades if g.grade != "N/A"]
        missing = [g for g in grades if g.grade == "N/A"]

        grade_counts = {"A": 0, "B": 0, "C": 0}
        for g in evaluated:
            if g.grade in grade_counts:
                grade_counts[g.grade] += 1

        lines = [
            f"📊 전체 품질 등급: {overall}",
            f"   평가된 섹션: {len(evaluated)}개 / 전체 {len(grades)}개",
            f"   A등급: {grade_counts['A']}개, B등급: {grade_counts['B']}개, C등급: {grade_counts['C']}개",
        ]

        if missing:
            lines.append(f"   미발견 섹션: {', '.join(g.section_name for g in missing)}")

        # C등급 섹션 하이라이트
        c_grades = [g for g in evaluated if g.grade == "C"]
        if c_grades:
            lines.append("\n[WARNING] 개선 필요 섹션:")
            for g in c_grades:
                lines.append(f"   - {g.section_name}: {g.reason}")

        return "\n".join(lines)


def evaluate_report_quality(article_text: str, lm: dspy.dsp.LM | None = None) -> dict[str, Any]:
    """
    편의 함수: 리포트 품질을 평가하고 결과를 딕셔너리로 반환합니다.

    Args:
        article_text: 마크다운 리포트 전문
        lm: 평가에 사용할 LM 인스턴스 (None이면 dspy 기본 설정 사용)

    Returns:
        dict with keys: overall_grade, section_grades, summary, total_sections_evaluated
    """
    inspector = QualityInspector(lm=lm)
    report = inspector.evaluate_report(article_text)

    return {
        "overall_grade": report.overall_grade,
        "section_grades": [
            {"section_name": g.section_name, "grade": g.grade, "reason": g.reason, "suggestions": g.suggestions}
            for g in report.section_grades
        ],
        "summary": report.summary,
        "total_sections_evaluated": report.total_sections_evaluated,
    }
