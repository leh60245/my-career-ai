"""
Correction Service (자소서 첨삭 — Evaluator 역할)

Context-Aware Multi-Agent 논문의 'Evaluator' 역할을 수행한다.
단순 문법 교정이 아닌, **기업 인재상**과 **직무 역량**이라는 맥락(Context)에 비추어
논리적 근거가 부족한 점을 지적하는 코칭 엔진.

출력 구조:
    1. feedback_points: 3-Point 논리 피드백 [{category, issue, suggestion}, ...]
    2. revised_content: 첨삭된 완성본 (대필 아닌 코칭 — 사용자 원문 기반 개선)
    3. score: 항목별 점수 {logic, job_fit, expression, structure}
"""

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import ResumeItemType
from backend.src.common.llm.client import LLMClient
from backend.src.common.repositories.base_repository import EntityNotFound
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.services.talent_service import TalentService
from backend.src.resume.repositories import (
    ResumeDraftRepository,
    ResumeFeedbackRepository,
    ResumeItemRepository,
    ResumeQuestionRepository,
)
from backend.src.resume.schemas import CorrectionResponse


logger = logging.getLogger(__name__)


# ============================================================
# LLM 응답 스키마 (내부용)
# ============================================================
class _FeedbackPoint(BaseModel):
    """개별 피드백 항목."""

    category: str = Field(..., description="피드백 카테고리 ('논리적 근거 부족', '직무적합성 약화', '구조적 개선' 등)")
    issue: str = Field(..., description="구체적 문제 지적 (원문의 해당 부분을 인용하며 설명)")
    suggestion: str = Field(..., description="개선 방향 제시 (대필이 아닌 코칭 — 사용자가 스스로 수정하도록 유도)")


class _ScoreOutput(BaseModel):
    """항목별 점수 (100점 만점)."""

    logic: int = Field(..., ge=0, le=100, description="논리성 (주장-근거 연결)")
    job_fit: int = Field(..., ge=0, le=100, description="직무적합성 (기업·직무 맥락 부합도)")
    expression: int = Field(..., ge=0, le=100, description="표현력 (구체성, 몰입도)")
    structure: int = Field(..., ge=0, le=100, description="구조 (STAR 흐름, 비중 배분)")


class _LLMCorrectionOutput(BaseModel):
    """LLM이 생성하는 첨삭 결과 구조체."""

    feedback_points: list[_FeedbackPoint] = Field(
        ..., min_length=1, max_length=5, description="3-Point 피드백 (최소 1개, 최대 5개)"
    )
    revised_content: str = Field(
        ..., description="첨삭이 반영된 개선본 (사용자 원문을 기반으로 수정, 없는 사실을 추가하지 않음)"
    )
    score: _ScoreOutput = Field(..., description="항목별 100점 만점 점수")


# ============================================================
# 문항 유형별 평가 기준
# ============================================================
_ITEM_TYPE_EVALUATION_CRITERIA: dict[ResumeItemType, str] = {
    ResumeItemType.MOTIVATION: (
        "【지원동기 평가 기준】\n"
        "- 기업 비전·사업 방향과 지원자 내러티브의 연결이 자연스러운가?\n"
        "- '왜 이 기업이어야 하는가?'에 대한 논리적 근거가 있는가?\n"
        "- 단순 '관심 있어서'가 아닌 구체적 사업/프로젝트/가치 매칭이 있는가?\n"
        "- 입사 후 포부가 직무의 실제 업무와 부합하는가?"
    ),
    ResumeItemType.COMPETENCY: (
        "【직무역량 평가 기준】\n"
        "- 제시된 역량이 해당 직무의 핵심 KPI 달성에 직접 기여하는가?\n"
        "- 성과가 수치로 입증되는가? (구체적 숫자, 비율, 기간)\n"
        "- 업무 도구/방법론에 대한 실질적 이해가 드러나는가?\n"
        "- '했다'가 아닌 '어떻게 했는가'의 과정이 서술되어 있는가?"
    ),
    ResumeItemType.CHALLENGE: (
        "【도전/성취 평가 기준】\n"
        "- 목표가 '자기주도적'으로 설정된 것인가, 남이 정해준 것인가?\n"
        "- 중간의 허들/역경이 구체적으로 서술되어 있는가?\n"
        "- Action에서 '왜 그 방법을 선택했는가?' 논리가 있는가?\n"
        "- 결과가 단순 완수가 아닌 성장/변화로 연결되는가?\n"
        "- 이 경험의 재현 가능성이 느껴지는가?"
    ),
    ResumeItemType.COLLABORATION: (
        "【협력/소통 평가 기준】\n"
        "- 이해관계자가 '누구'인지 구체적으로 명시되어 있는가?\n"
        "- 갈등/충돌 지점이 명확히 서술되어 있는가?\n"
        "- 해결 과정에서 데이터 기반 설득 / 경청 / 제도적 접근이 있는가?\n"
        "- '독불장군'이 아닌 '팀원으로서의 역할'이 드러나는가?\n"
        "- 성과가 팀에 귀속되는가 (vs 개인 자랑)?"
    ),
    ResumeItemType.VALUES: (
        "【가치관/인성 평가 기준】\n"
        "- 가치가 '말'이 아닌 '행동'으로 증명되는가?\n"
        "- 기업의 핵심 가치와 자연스럽게 연결되는가?\n"
        "- 추상적 미사여구 대신 구체적 에피소드가 있는가?\n"
        "- 조직 융화력이 느껴지는가? (독단적·소통 부재 아닌지)"
    ),
    ResumeItemType.SOCIAL_ISSUE: (
        "【사회이슈 평가 기준】\n"
        "- 이슈에 대한 분석이 다각적인가? (찬반 양면, 이해관계자별 시각)\n"
        "- 근거가 있는 주장인가? (연구, 데이터, 사례 인용)\n"
        "- 기업의 사업/산업과의 연관성이 드러나는가?\n"
        "- 주관적 감정이 아닌 논리적 논증 구조를 갖추었는가?"
    ),
}


# ============================================================
# System Prompt Template
# ============================================================
_SYSTEM_PROMPT = """당신은 **Context-Aware Evaluator** — 자소서 첨삭 전문가입니다.

━━━━ 역할 정의 ━━━━

당신의 역할은 '대필(Ghostwriting)'이 아닌 '코칭(Coaching)'입니다.
사용자의 자소서를 **기업 인재상**과 **직무 역량**이라는 두 축의 맥락(Context)에 비추어
**논리적 근거가 부족한 점을 정확히 지적**하고, 개선 방향을 제시하는 것입니다.

━━━━ 평가 원칙 (엄수) ━━━━

【원칙 1: 맥락(Context) 기반 평가】
- 문법·맞춤법이 아닌 '논리'를 평가하라.
- 모든 피드백은 반드시 '이 기업', '이 직무'의 맥락 내에서 이루어져야 한다.
- "일반적으로 좋은 글"이 아닌, "이 기업에 합격하기 위한 글"로 평가하라.

【원칙 2: 근거 없는 추가 금지 (No Hallucination)】
- 사용자가 작성하지 않은 경험, 사실, 수치를 절대 추가하지 마라.
- revised_content에서 새로운 에피소드를 '창작'하지 마라.
- 사용자의 원문에 존재하는 소재만으로 논리적 구조를 개선하라.

【원칙 3: Action 차별화 집중 평가】
- 자소서의 핵심은 Action(행동)이다.
- 아래 3요소를 기준으로 Action의 질을 평가하라:
  * 주도성: 남이 시킨 일인가, 본인이 찾아서 한 일인가?
  * 논리성: 왜 그 행동을 했는가? 근거가 있는가?
  * 재현 가능성: 이 사람이 우리 회사에서도 동일한 행동을 할 것인가?

【원칙 4: 기업 인재상 매칭 평가】
- 기업이 공식적으로 밝힌 핵심 가치(core_values)에 비추어:
  * 지원자의 경험이 해당 가치를 'demonstrate'하는가?
  * 특정 가치와 충돌하는 서술은 없는가?
  * 빠뜨리고 있는 핵심 가치 연결 지점이 있는가?

━━━━ 출력 형식 (JSON) ━━━━

1. **feedback_points** (3-Point 피드백, 리스트):
   각 항목은 {category, issue, suggestion} 구조.
   - category: 피드백 분류 (예: "논리적 근거 부족", "직무적합성 약화", "구조적 개선", "인재상 불일치", "Action 주도성 미흡")
   - issue: 원문의 해당 부분을 인용하며 구체적으로 무엇이 문제인지 설명
   - suggestion: 대필이 아닌 코칭 방향 제시 (사용자가 스스로 수정할 수 있도록 유도)
   최소 3개, 가장 중요한 순서로 정렬.

2. **revised_content** (첨삭 완성본):
   - 사용자 원문을 기반으로 구조와 논리를 개선한 버전.
   - 없는 사실을 추가하지 마라.
   - 문장 수준의 표현 개선 + 논리적 흐름 재배치 + STAR 구조화에 집중.

3. **score** (항목별 100점 만점 점수):
   - logic: 논리성 (주장-근거 연결의 탄탄함)
   - job_fit: 직무적합성 (기업·직무 맥락 부합도)
   - expression: 표현력 (구체성, 생동감, 몰입도)
   - structure: 구조 (STAR 흐름, 각 단계 비중 배분)

━━━━ 절대 원칙 ━━━━
- 대필 금지: 사용자가 작성하지 않은 에피소드/사실/수치를 절대 추가하지 마라.
- 맞춤법 교정은 부가적이다. 핵심은 논리와 맥락이다.
- 한국어로 응답하라."""


def _build_user_prompt(
    *,
    company_name: str | None,
    job_name: str | None,
    job_keywords: list[str] | None,
    item_type: ResumeItemType,
    item_content: str,
    max_length: int | None,
    draft_content: str,
    talent_context: dict[str, Any],
    evaluation_criteria: str,
) -> str:
    """
    첨삭용 사용자 프롬프트를 조립한다.

    Args:
        company_name: 기업명
        job_name: 직무명
        job_keywords: 직무 키워드 리스트
        item_type: 문항 유형
        item_content: 문항 지문
        max_length: 글자수 제한
        draft_content: 사용자 작성 초안
        talent_context: 인재상 컨텍스트
        evaluation_criteria: 문항 유형별 평가 기준

    Returns:
        조립된 사용자 프롬프트 문자열
    """
    sections: list[str] = []

    # ── 기업 맥락 (Evaluator의 평가 기준) ──
    sections.append("══════ 평가 맥락: 기업 ══════")
    sections.append(f"기업명: {company_name or '미지정'}")
    if talent_context.get("core_values"):
        values_str = ", ".join(talent_context["core_values"])
        sections.append(f"핵심 가치: {values_str}")
        sections.append(f"→ 평가 시, 지원자의 경험이 [{values_str}] 중 어떤 가치를 demonstrate하는지 확인하세요.")
    if talent_context.get("description"):
        sections.append(f"인재상 요약: {talent_context['description']}")

    # ── 직무 맥락 ──
    sections.append("\n══════ 평가 맥락: 직무 ══════")
    sections.append(f"직무명: {job_name or '미지정'}")
    if job_keywords:
        sections.append(f"핵심 역량 키워드: {', '.join(job_keywords)}")
        sections.append("→ 지원자의 Action이 위 키워드가 요구하는 역량을 보여주는지 평가하세요.")

    # ── 문항 정보 ──
    sections.append("\n══════ 문항 정보 ══════")
    sections.append(f"문항 유형: {item_type.value}")
    sections.append(f"문항 지문: {item_content}")
    if max_length:
        sections.append(f"글자수 제한: {max_length}자")

    # ── 문항 유형별 평가 기준 ──
    sections.append(f"\n{evaluation_criteria}")

    # ── 사용자 작성 초안 (평가 대상) ──
    sections.append("\n══════ [평가 대상] 사용자 작성 초안 ══════")
    sections.append(draft_content)

    sections.append(
        "\n위 초안을 기업·직무 맥락에 비추어 평가하고, "
        "feedback_points(3-Point 피드백), revised_content(첨삭본), score(점수)를 JSON으로 생성하세요."
    )

    return "\n".join(sections)


# ============================================================
# Correction Service
# ============================================================
class CorrectionService:
    """
    자소서 첨삭 서비스 (Evaluator 역할).

    사용자의 초안을 기업 인재상 × 직무 역량 맥락에 비추어 평가하고,
    논리적 근거 부족 지점을 지적하는 코칭 엔진.

    흐름:
        1. ResumeDraft 조회 → ResumeItem/Question 조회 (맥락 확보)
        2. Company 인재상 조회 (TalentService)
        3. JobCategory 키워드 조회
        4. 문항 유형별 평가 기준 적용
        5. LLM 호출 → 3-Point 피드백 + 첨삭본 + 점수 생성
        6. ResumeFeedback에 저장
    """

    def __init__(
        self,
        question_repo: ResumeQuestionRepository,
        item_repo: ResumeItemRepository,
        draft_repo: ResumeDraftRepository,
        feedback_repo: ResumeFeedbackRepository,
        company_repo: CompanyRepository,
        talent_service: TalentService,
        session: AsyncSession,
    ) -> None:
        self.question_repo = question_repo
        self.item_repo = item_repo
        self.draft_repo = draft_repo
        self.feedback_repo = feedback_repo
        self.company_repo = company_repo
        self.talent_service = talent_service
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> "CorrectionService":
        """AsyncSession으로부터 서비스 인스턴스를 생성한다."""
        return cls(
            question_repo=ResumeQuestionRepository(session),
            item_repo=ResumeItemRepository(session),
            draft_repo=ResumeDraftRepository(session),
            feedback_repo=ResumeFeedbackRepository(session),
            company_repo=CompanyRepository(session),
            talent_service=TalentService.from_session(session),
            session=session,
        )

    async def evaluate_draft(self, draft_id: int, user_id: int) -> CorrectionResponse:
        """
        초안을 Context-Aware 관점에서 평가하고 피드백을 생성한다.

        Args:
            draft_id: 초안 PK (ResumeDraft ID)
            user_id: 사용자 PK (권한 검증용)

        Returns:
            CorrectionResponse (피드백 + 첨삭본 + 점수)

        Raises:
            EntityNotFound: 초안/문항이 존재하지 않는 경우
            PermissionError: 본인 자소서가 아닌 경우
            LLMClientError: LLM 호출 실패
        """
        # ─── 1. 데이터 체인 조회: Draft → Item → Question ───
        draft = await self.draft_repo.get(draft_id)
        if not draft:
            raise EntityNotFound(f"ResumeDraft(id={draft_id}) 이(가) 존재하지 않습니다.")

        item = await self.item_repo.get(draft.item_id)
        if not item:
            raise EntityNotFound(f"ResumeItem(id={draft.item_id}) 이(가) 존재하지 않습니다.")

        question = await self.question_repo.get(item.question_id)
        if not question:
            raise EntityNotFound(f"ResumeQuestion(id={item.question_id}) 이(가) 존재하지 않습니다.")

        if question.user_id != user_id:
            raise PermissionError("본인의 자소서만 첨삭을 요청할 수 있습니다.")

        # ─── 2. 기업 컨텍스트 수집 ───
        company_name: str | None = None
        talent_context: dict[str, Any] = {"core_values": [], "description": ""}

        if question.company_id:
            company = await self.company_repo.get(question.company_id)
            if company:
                company_name = company.company_name
                talent_context = await self.talent_service.get_talent_context(company_name)

        # ─── 3. 직무 컨텍스트 수집 ───
        job_name: str | None = question.job_text
        job_keywords: list[str] | None = None

        if question.job_category_id:
            from sqlalchemy import select

            from backend.src.common.models.job import JobCategory

            stmt = select(JobCategory).where(JobCategory.id == question.job_category_id)
            result = await self._session.execute(stmt)
            job_cat = result.scalar_one_or_none()
            if job_cat:
                job_name = job_name or job_cat.name
                job_keywords = job_cat.keywords

        # ─── 4. 문항 유형별 평가 기준 ───
        evaluation_criteria = _ITEM_TYPE_EVALUATION_CRITERIA.get(
            item.type, "【평가 기준】\n- 논리적 근거 + 구체성 + 기업 맥락 부합도를 종합 평가하라."
        )

        # ─── 5. 프롬프트 조립 & LLM 호출 ───
        user_prompt = _build_user_prompt(
            company_name=company_name,
            job_name=job_name,
            job_keywords=job_keywords,
            item_type=item.type,
            item_content=item.content,
            max_length=item.max_length,
            draft_content=draft.content,
            talent_context=talent_context,
            evaluation_criteria=evaluation_criteria,
        )

        llm_client = LLMClient()
        llm_result: _LLMCorrectionOutput = await llm_client.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=_LLMCorrectionOutput,
            temperature=0.4,
            max_tokens=4096,
        )  # type: ignore[assignment]

        # ─── 6. 결과 저장 (ResumeFeedback) ───
        feedback_data = {
            "draft_id": draft_id,
            "ai_model": llm_client.model,
            "guide_json": None,
            "correction_content": llm_result.revised_content,
            "feedback_points": [fp.model_dump() for fp in llm_result.feedback_points],
            "score": llm_result.score.model_dump(),
        }
        await self.feedback_repo.create(feedback_data)

        logger.info(
            f" 첨삭 완료: draft_id={draft_id}, "
            f"company={company_name}, job={job_name}, "
            f"score={{logic={llm_result.score.logic}, job_fit={llm_result.score.job_fit}}}"
        )

        return CorrectionResponse(
            feedback_points=[fp.model_dump() for fp in llm_result.feedback_points],
            revised_content=llm_result.revised_content,
            score=llm_result.score.model_dump(),
        )
