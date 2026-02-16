"""
Guide Service (자소서 작성 가이드)

Context-Aware Multi-Agent 논문의 철학을 반영한 자소서 코칭 엔진.
단순 템플릿이 아닌, 기업 아이덴티티 × 직무 역할 × 역량 심리 분석을 결합한
맥락 기반 가이드를 생성한다.

출력 5단:
    1. 질문 의도 분석 (3-Sub Logic)
    2. 핵심 키워드
    3. 소재 선정 가이드
    4. 작성 포인트 (STAR + Action 차별화)
    5. 주의사항
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
from backend.src.resume.repositories import ResumeItemRepository, ResumeQuestionRepository
from backend.src.resume.schemas import GuideResponse


logger = logging.getLogger(__name__)


# ============================================================
# LLM 응답 스키마 (내부용)
# ============================================================
class _LLMGuideOutput(BaseModel):
    """LLM이 생성하는 작성 가이드 구조체."""

    question_intent: str = Field(
        ..., description="질문 의도 분석 (기업 아이덴티티 매칭 + 직무 역할 정의 + 역량 기반 분석을 통합한 해석)"
    )
    keywords: list[str] = Field(
        default_factory=list, description="핵심 키워드 6~10개 (기업 가치 + 직무 역량 + 문항 평가 의도에서 도출)"
    )
    material_guide: str = Field(
        ..., description="소재 선정 가이드 (기업 사업 특성 × 직무 업무 방식을 결합한 경험 추천)"
    )
    writing_points: str = Field(..., description="작성 포인트 (STAR 기법 비중 배분 + Action 차별화 전략 포함)")
    cautions: str = Field(..., description="주의사항 (직무적합성 불일치, 질문 의도 이탈, 조직 융화력 관점)")


# ============================================================
# 문항 유형별 평가 역량 매핑
# ============================================================
_ITEM_TYPE_COMPETENCY_MAP: dict[ResumeItemType, dict[str, str]] = {
    ResumeItemType.MOTIVATION: {
        "psychology": "내재적 동기(Intrinsic Motivation)와 목표 일관성(Goal Congruence)",
        "core_question": "이 지원자의 입사 동기가 기업의 방향성과 진정으로 일치하는가?",
        "evaluator_focus": "지원자의 커리어 내러티브가 기업의 비전/미션과 자연스럽게 연결되는지 확인",
    },
    ResumeItemType.COMPETENCY: {
        "psychology": "자기효능감(Self-Efficacy)과 전이 가능한 전문성(Transferable Expertise)",
        "core_question": "이 지원자가 보유한 역량이 해당 직무의 핵심 과제를 해결할 수 있는가?",
        "evaluator_focus": "구체적 성과 수치와 업무 도구/방법론에 대한 이해도를 확인",
    },
    ResumeItemType.CHALLENGE: {
        "psychology": "그릿(Grit) — 장기적 목표를 향한 끈기와 열정",
        "core_question": "중간에 포기할 만한 강력한 허들이 있었음에도 끝까지 밀어붙였는가?",
        "evaluator_focus": "목표 수준의 자기주도성, 역경 속 문제 해결 과정, 결과의 성장 연결",
    },
    ResumeItemType.COLLABORATION: {
        "psychology": "사회적 지능(Social Intelligence)과 이해관계 조정 능력",
        "core_question": "이해관계가 다른 사람들 사이에서 어떤 역할을 수행했는가?",
        "evaluator_focus": "단순 친절이 아닌 갈등 조정, 데이터 기반 설득, 프로세스 개선 능력 확인",
    },
    ResumeItemType.VALUES: {
        "psychology": "도덕적 정체성(Moral Identity)과 가치 내재화",
        "core_question": "이 지원자의 가치관이 조직 문화에 부합하며 팀에 긍정적 영향을 줄 수 있는가?",
        "evaluator_focus": "추상적 신념이 아닌 행동으로 증명된 가치, 조직 적합성 확인",
    },
    ResumeItemType.SOCIAL_ISSUE: {
        "psychology": "시스템 사고(Systems Thinking)와 비판적 분석력",
        "core_question": "복잡한 사회 현상을 다각적으로 분석하고, 기업 맥락에 연결할 수 있는가?",
        "evaluator_focus": "주관적 의견이 아닌 근거 기반 논리, 기업 사업과의 연관성 확인",
    },
}


# ============================================================
# System Prompt Template
# ============================================================
_SYSTEM_PROMPT = """당신은 **Context-Aware 자소서 코칭 전문가**입니다.
단순한 자소서 템플릿을 제공하는 것이 아니라, 아래 3가지 분석 프레임워크를 결합하여
지원자에게 **기업 맞춤형 작성 가이드**를 제공하는 것이 당신의 역할입니다.

━━━━ 분석 프레임워크 (필수 적용) ━━━━

【1. 기업 아이덴티티 매칭 로직】
- 기업의 비전, 미션, CEO 메시지, 사업 포지셔닝에서 추출한 '핵심 정체성'을 질문 의도와 결합.
- 핵심 질문: "이 기업이 업종 내에서 어떤 포지셔닝을 취하고 있는가?"
- 예시: 아모레퍼시픽은 단순 화장품 판매가 아닌 '뉴 뷰티(New Beauty)'를 정의하는 기업이므로,
  '목표 달성' 문항에서도 "기존 관습을 깨는 새로운 시도였는가?"를 프레이밍해야 함.

【2. 직무 역할/과제 정의 로직】
- 해당 직무의 KPI를 달성하기 위한 '궁극적 숙제'와 '필수 성격적 형질'을 파악.
- 핵심 질문: "이 직무의 KPI를 달성하기 위해 가장 필요한 성격적 형질은 무엇인가?"
- 예시: 마케팅 직무 → 시장 선도(First Mover)를 위한 '주도적 목표 설정'과 '승부욕' 필수.

【3. 역량 기반 분석 로직】
- 문항이 측정하고자 하는 심리적 특성/역량을 추출하여 평가 기준을 도출.
- 핵심 질문: "이 문항이 측정하고자 하는 단 하나의 심리적 지표는 무엇인가?"
- 예시: 도전/완수 문항 → '그릿(Grit)' = 장기적 목표를 향한 끈기와 열정.

━━━━ 출력 형식 (JSON) ━━━━

반드시 아래 5개 필드를 모두 채워 JSON으로 응답하세요:

1. **question_intent** (질문 의도 분석):
   위 3가지 프레임워크를 모두 적용한 통합 분석. 기업이 '진짜' 확인하고 싶은 것이 무엇인지 밝혀라.

2. **keywords** (핵심 키워드 리스트, 6~10개):
   - 기업 사업/특성 키워드 + 기업 핵심가치/비전 키워드 + 문항 평가 역량 키워드를 혼합.

3. **material_guide** (소재 선정 가이드):
   - '좋은 경험'의 나열이 아닌, 기업의 사업 특성 × 직무 업무 방식을 결합한 구체적 소재 추천.
   - 어떤 경험이 이 기업·직무 맥락에서 "베스트"인지 3가지 방향을 제시하라.

4. **writing_points** (작성 포인트):
   - STAR(Situation-Task-Action-Result) 기법을 기본 프레임으로 하되, 각 단계별 비중(%) 제시.
   - **Action 차별화 3요소**를 반드시 포함:
     * 주도성: 남이 시켜서 한 일이 아닌, 본인이 찾아서 한 일
     * 논리성: "왜 그 행동을 했는가?"에 대한 근거
     * 재현 가능성: "우리 회사에 와서도 똑같이 행동할 사람인가?"
   - 기업 특성과 직무에 따라 STAR 각 단계의 강조점이 달라져야 함.

5. **cautions** (주의사항):
   - 직무적합성 불일치: 소재나 표현이 해당 직무 고유의 색깔을 흐리는 경우
   - 질문 의도 이탈: 기업이 확인하려는 본질에서 벗어나는 내용
   - 조직 융화력: 함께 일하기 힘든 사람처럼 보이는 표현 (독단적, 소통 부재)
   각 항목마다 이 기업·직무에 특화된 구체적 경고를 제시하라.

━━━━ 절대 원칙 ━━━━
- 대필(Ghostwriting) 금지. 실제 자소서 본문을 작성하지 마라. 가이드만 제시하라.
- 추상적 조언 금지. 모든 가이드는 '이 기업', '이 직무', '이 문항'에 특화되어야 한다.
- 한국어로 응답하라."""


def _build_user_prompt(
    *,
    company_name: str | None,
    job_name: str | None,
    job_keywords: list[str] | None,
    item_type: ResumeItemType,
    item_content: str,
    max_length: int | None,
    talent_context: dict[str, Any],
    competency_info: dict[str, str],
) -> str:
    """
    사용자 프롬프트를 조립한다.

    Args:
        company_name: 기업명
        job_name: 직무명
        job_keywords: 직무 키워드 리스트
        item_type: 문항 유형
        item_content: 문항 지문
        max_length: 글자수 제한
        talent_context: 인재상 컨텍스트 (core_values, description)
        competency_info: 문항 유형별 심리/역량 분석 힌트

    Returns:
        조립된 사용자 프롬프트 문자열
    """
    sections: list[str] = []

    # ── 기업 정보 ──
    sections.append("══════ 기업 정보 ══════")
    sections.append(f"기업명: {company_name or '미지정'}")
    if talent_context.get("core_values"):
        sections.append(f"핵심 가치: {', '.join(talent_context['core_values'])}")
    if talent_context.get("description"):
        sections.append(f"인재상 요약: {talent_context['description']}")
    if not talent_context.get("core_values") and not talent_context.get("description"):
        sections.append("(인재상 데이터 없음 — 기업 일반 정보 기반으로 분석하세요)")

    # ── 직무 정보 ──
    sections.append("\n══════ 직무 정보 ══════")
    sections.append(f"직무명: {job_name or '미지정'}")
    if job_keywords:
        sections.append(f"핵심 역량 키워드: {', '.join(job_keywords)}")

    # ── 문항 정보 ──
    sections.append("\n══════ 문항 정보 ══════")
    sections.append(f"문항 유형: {item_type.value}")
    sections.append(f"문항 지문: {item_content}")
    if max_length:
        sections.append(f"글자수 제한: {max_length}자")

    # ── 역량 분석 힌트 (프레임워크 3번 보조) ──
    sections.append("\n══════ 역량 분석 힌트 (참고용) ══════")
    sections.append(f"심리적 지표: {competency_info.get('psychology', 'N/A')}")
    sections.append(f"핵심 확인 질문: {competency_info.get('core_question', 'N/A')}")
    sections.append(f"평가자 관점: {competency_info.get('evaluator_focus', 'N/A')}")

    sections.append("\n위 정보를 바탕으로 Context-Aware 작성 가이드(5개 섹션)를 JSON으로 생성하세요.")

    return "\n".join(sections)


# ============================================================
# Guide Service
# ============================================================
class GuideService:
    """
    자소서 작성 가이드 서비스.

    Context-Aware Multi-Agent 프레임워크를 적용하여,
    기업·직무·문항의 맥락을 결합한 정교한 코칭 가이드를 생성한다.

    흐름:
        1. ResumeItem 조회 → ResumeQuestion 조회 (기업/직무 맥락 확보)
        2. Company 인재상 조회 (TalentService: DB-first, Search-fallback)
        3. JobCategory 키워드 조회
        4. 문항 유형별 역량 매핑 적용
        5. LLM 호출 → 5-Section 가이드 생성
        6. ResumeFeedback에 guide_json으로 저장
    """

    def __init__(
        self,
        question_repo: ResumeQuestionRepository,
        item_repo: ResumeItemRepository,
        company_repo: CompanyRepository,
        talent_service: TalentService,
        session: AsyncSession,
    ) -> None:
        self.question_repo = question_repo
        self.item_repo = item_repo
        self.company_repo = company_repo
        self.talent_service = talent_service
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> "GuideService":
        """AsyncSession으로부터 서비스 인스턴스를 생성한다."""
        return cls(
            question_repo=ResumeQuestionRepository(session),
            item_repo=ResumeItemRepository(session),
            company_repo=CompanyRepository(session),
            talent_service=TalentService.from_session(session),
            session=session,
        )

    async def generate_guide(self, item_id: int, user_id: int) -> GuideResponse:
        """
        특정 문항에 대한 Context-Aware 작성 가이드를 생성한다.

        Args:
            item_id: 문항 PK (ResumeItem ID)
            user_id: 사용자 PK (권한 검증용)

        Returns:
            GuideResponse (5-Section 가이드)

        Raises:
            EntityNotFound: 문항이 존재하지 않는 경우
            PermissionError: 본인 문항이 아닌 경우
            LLMClientError: LLM 호출 실패
        """
        # 1. 문항 및 세트 조회
        item = await self.item_repo.get(item_id)
        if not item:
            raise EntityNotFound(f"ResumeItem(id={item_id}) 이(가) 존재하지 않습니다.")

        question = await self.question_repo.get(item.question_id)
        if not question:
            raise EntityNotFound(f"ResumeQuestion(id={item.question_id}) 이(가) 존재하지 않습니다.")

        if question.user_id != user_id:
            raise PermissionError("본인의 자소서 문항만 가이드를 요청할 수 있습니다.")

        # 2. 기업 컨텍스트 수집
        company_name: str | None = None
        talent_context: dict[str, Any] = {"core_values": [], "description": ""}

        if question.company_id:
            company = await self.company_repo.get(question.company_id)
            if company:
                company_name = company.company_name
                talent_context = await self.talent_service.get_talent_context(company_name)

        # 3. 직무 컨텍스트 수집
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

        # 4. 문항 유형별 역량 매핑
        competency_info = _ITEM_TYPE_COMPETENCY_MAP.get(
            item.type,
            {
                "psychology": "종합적 역량",
                "core_question": "이 지원자가 조직에 기여할 수 있는 핵심 가치는?",
                "evaluator_focus": "전반적인 자질과 잠재력 확인",
            },
        )

        # 5. 프롬프트 조립 & LLM 호출
        user_prompt = _build_user_prompt(
            company_name=company_name,
            job_name=job_name,
            job_keywords=job_keywords,
            item_type=item.type,
            item_content=item.content,
            max_length=item.max_length,
            talent_context=talent_context,
            competency_info=competency_info,
        )

        llm_client = LLMClient()
        llm_result: _LLMGuideOutput = await llm_client.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=_LLMGuideOutput,
            temperature=0.5,
            max_tokens=4096,
        )  # type: ignore[assignment]

        logger.info(f" 작성 가이드 생성 완료: item_id={item_id}, company={company_name}, job={job_name}")

        return GuideResponse(
            question_intent=llm_result.question_intent,
            keywords=llm_result.keywords,
            material_guide=llm_result.material_guide,
            writing_points=llm_result.writing_points,
            cautions=llm_result.cautions,
        )
