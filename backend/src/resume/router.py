"""
Resume 도메인 API 라우터

자소서 세트 CRUD, 작성 가이드 생성, 첨삭 요청, 초안 관리 등
자소서 코칭 도메인의 모든 HTTP 엔드포인트를 관리한다.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.common.llm.client import LLMClientError
from backend.src.common.repositories.base_repository import EntityNotFound
from backend.src.resume.repositories import (
    ResumeDraftRepository,
    ResumeFeedbackRepository,
    ResumeItemRepository,
    ResumeQuestionRepository,
)
from backend.src.resume.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    DraftHistoryItem,
    DraftHistoryResponse,
    GuideRequest,
    GuideResponse,
    ResumeDraftCreate,
    ResumeDraftResponse,
    ResumeFeedbackResponse,
    ResumeQuestionCreate,
    ResumeQuestionListItem,
    ResumeQuestionResponse,
)
from backend.src.resume.services.correction_service import CorrectionService
from backend.src.resume.services.guide_service import GuideService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resume", tags=["resume"])


# ============================================================
# Dependencies
# ============================================================
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제공."""
    db_engine = AsyncDatabaseEngine()
    async with db_engine.get_session() as session:
        yield session


async def get_guide_service(session: AsyncSession = Depends(get_session)) -> GuideService:
    """GuideService 팩토리."""
    return GuideService.from_session(session)


async def get_correction_service(session: AsyncSession = Depends(get_session)) -> CorrectionService:
    """CorrectionService 팩토리."""
    return CorrectionService.from_session(session)


# ============================================================
# 자소서 세트 (ResumeQuestion) CRUD
# ============================================================
@router.get("/questions", response_model=list[ResumeQuestionListItem], summary="자소서 세트 목록 조회")
async def list_questions(
    user_id: int, include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[ResumeQuestionListItem]:
    """
    사용자의 자소서 세트 목록을 반환한다.

    TODO: user_id는 향후 JWT 토큰에서 추출하도록 변경.
    """
    repo = ResumeQuestionRepository(session)
    questions = await repo.get_by_user_id(user_id, include_archived=include_archived)
    return [ResumeQuestionListItem.model_validate(q) for q in questions]


@router.get(
    "/questions/{question_id}", response_model=ResumeQuestionResponse, summary="자소서 세트 상세 조회 (문항 포함)"
)
async def get_question(question_id: int, session: AsyncSession = Depends(get_session)) -> ResumeQuestionResponse:
    """자소서 세트와 문항(items)을 함께 반환한다."""
    repo = ResumeQuestionRepository(session)
    question = await repo.get_with_items(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="자소서 세트를 찾을 수 없습니다.")
    return ResumeQuestionResponse.model_validate(question)


@router.post("/questions", response_model=ResumeQuestionResponse, status_code=201, summary="자소서 세트 생성")
async def create_question(
    user_id: int, body: ResumeQuestionCreate, session: AsyncSession = Depends(get_session)
) -> ResumeQuestionResponse:
    """
    자소서 세트와 문항(items)을 한 번에 생성한다.

    TODO: user_id는 향후 JWT 토큰에서 추출하도록 변경.
    """
    question_repo = ResumeQuestionRepository(session)
    item_repo = ResumeItemRepository(session)

    # 세트 생성
    question = await question_repo.create(
        {
            "user_id": user_id,
            "company_id": body.company_id,
            "job_category_id": body.job_category_id,
            "job_text": body.job_text,
            "title": body.title,
            "target_season": body.target_season,
            "applicant_type": body.applicant_type,
        }
    )

    # 문항 생성
    for item_data in body.items:
        await item_repo.create(
            {
                "question_id": question.id,
                "type": item_data.type,
                "content": item_data.content,
                "max_length": item_data.max_length,
                "order_index": item_data.order_index,
            }
        )

    await session.commit()

    # 문항 포함하여 다시 조회
    result = await question_repo.get_with_items(question.id)
    return ResumeQuestionResponse.model_validate(result)


# ============================================================
# 작성 가이드 (Guide)
# ============================================================
@router.post("/guide", response_model=GuideResponse, summary="Context-Aware 작성 가이드 생성")
async def generate_guide(body: GuideRequest, service: GuideService = Depends(get_guide_service)) -> GuideResponse:
    """
    특정 문항에 대한 Context-Aware 작성 가이드를 생성한다.

    기업 아이덴티티 × 직무 역할 × 역량 심리 분석을 결합하여
    5-Section 맞춤 가이드를 반환한다.
    """
    try:
        return await service.generate_guide(item_id=body.item_id, user_id=body.user_id)
    except EntityNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    except LLMClientError as e:
        logger.error(f"작성 가이드 LLM 오류: {e}")
        raise HTTPException(status_code=502, detail="AI 서비스 호출에 실패했습니다.") from e


# ============================================================
# 첨삭 (Correction)
# ============================================================
@router.post("/correction", response_model=CorrectionResponse, summary="Context-Aware 첨삭 (Evaluator)")
async def evaluate_correction(
    body: CorrectionRequest, service: CorrectionService = Depends(get_correction_service)
) -> CorrectionResponse:
    """
    초안을 기업 인재상 × 직무 역량 맥락에 비추어 평가한다.

    3-Point 피드백 + 첨삭 완성본 + 항목별 점수를 반환한다.
    대필이 아닌 코칭 — 없는 사실을 추가하지 않는다.
    """
    try:
        return await service.evaluate_draft(draft_id=body.draft_id, user_id=body.user_id)
    except EntityNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    except LLMClientError as e:
        logger.error(f"첨삭 LLM 오류: {e}")
        raise HTTPException(status_code=502, detail="AI 서비스 호출에 실패했습니다.") from e


# ============================================================
# 초안 (Draft) 관리
# ============================================================
@router.post(
    "/items/{item_id}/drafts", response_model=ResumeDraftResponse, status_code=201, summary="초안 새 버전 생성"
)
async def create_draft(
    item_id: int, body: ResumeDraftCreate, session: AsyncSession = Depends(get_session)
) -> ResumeDraftResponse:
    """문항에 새 초안 버전을 생성한다. 기존 활성 버전은 비활성화된다."""
    draft_repo = ResumeDraftRepository(session)
    new_draft = await draft_repo.create_new_version(item_id, body.content)
    await session.commit()
    return ResumeDraftResponse.model_validate(new_draft)


@router.get("/items/{item_id}/drafts", response_model=DraftHistoryResponse, summary="초안 히스토리 조회 (피드백 포함)")
async def get_draft_history(item_id: int, session: AsyncSession = Depends(get_session)) -> DraftHistoryResponse:
    """문항의 모든 초안과 관련 피드백을 시간순으로 반환한다."""
    draft_repo = ResumeDraftRepository(session)
    feedback_repo = ResumeFeedbackRepository(session)

    drafts = await draft_repo.get_by_item_id(item_id)

    history: list[DraftHistoryItem] = []
    for draft in drafts:
        feedbacks = await feedback_repo.get_by_draft_id(draft.id)
        history.append(
            DraftHistoryItem(
                draft=ResumeDraftResponse.model_validate(draft),
                feedbacks=[ResumeFeedbackResponse.model_validate(f) for f in feedbacks],
            )
        )

    return DraftHistoryResponse(item_id=item_id, history=history)
