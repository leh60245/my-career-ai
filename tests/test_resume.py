"""
Resume 도메인 테스트

자소서 세트 CRUD, 문항 관리 등의 해피패스 및 예외 상황을 검증.
코칭(첨삭) 서비스는 LLM 의존성이 있어 API 레벨 테스트는 제외하고 DB 레이어만 검증.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.resume.models import ResumeItem, ResumeQuestion
from backend.src.resume.repositories import ResumeItemRepository, ResumeQuestionRepository
from backend.src.user.models import User


# ============================================================
# ResumeQuestion Repository 단위 테스트
# ============================================================
class TestResumeQuestionRepository:
    """ResumeQuestionRepository 데이터 접근 계층 테스트."""

    async def test_create_question_success(self, session: AsyncSession, job_seeker_user: User):
        """자소서 세트를 생성한다."""
        repo = ResumeQuestionRepository(session)
        question = await repo.create({
            "user_id": job_seeker_user.id,
            "title": "삼성전자 SW 직군 자소서",
            "applicant_type": "NEW",
            "is_archived": False,
        })

        assert question is not None
        assert question.id is not None
        assert question.user_id == job_seeker_user.id
        assert question.title == "삼성전자 SW 직군 자소서"
        assert question.is_archived is False

    async def test_get_by_user_id_excludes_archived(self, session: AsyncSession, job_seeker_user: User):
        """아카이브된 자소서는 기본적으로 목록에서 제외된다."""
        repo = ResumeQuestionRepository(session)

        # 정상 자소서
        await repo.create({"user_id": job_seeker_user.id, "title": "일반 자소서", "is_archived": False})
        # 아카이브된 자소서
        await repo.create({"user_id": job_seeker_user.id, "title": "아카이브 자소서", "is_archived": True})

        # 기본 조회 — 아카이브 제외
        questions = await repo.get_by_user_id(job_seeker_user.id, include_archived=False)
        titles = [q.title for q in questions]
        assert "일반 자소서" in titles
        assert "아카이브 자소서" not in titles

    async def test_get_by_user_id_includes_archived(self, session: AsyncSession, job_seeker_user: User):
        """include_archived=True 시 아카이브된 자소서도 포함된다."""
        repo = ResumeQuestionRepository(session)

        await repo.create({"user_id": job_seeker_user.id, "title": "일반 자소서2", "is_archived": False})
        await repo.create({"user_id": job_seeker_user.id, "title": "아카이브 자소서2", "is_archived": True})

        questions = await repo.get_by_user_id(job_seeker_user.id, include_archived=True)
        titles = [q.title for q in questions]
        assert "일반 자소서2" in titles
        assert "아카이브 자소서2" in titles

    async def test_get_by_user_id_empty(self, session: AsyncSession, job_seeker_user: User):
        """자소서가 없는 사용자는 빈 목록이 반환된다."""
        repo = ResumeQuestionRepository(session)
        questions = await repo.get_by_user_id(job_seeker_user.id)

        assert isinstance(questions, list | tuple)
        assert len(questions) == 0

    async def test_get_with_items(self, session: AsyncSession, job_seeker_user: User):
        """자소서 세트와 문항을 함께 조회한다."""
        q_repo = ResumeQuestionRepository(session)
        i_repo = ResumeItemRepository(session)

        question = await q_repo.create(
            {"user_id": job_seeker_user.id, "title": "문항 포함 자소서", "is_archived": False}
        )
        await i_repo.create({
            "question_id": question.id,
            "type": "MOTIVATION",
            "content": "지원 동기를 서술하시오.",
            "order_index": 0,
        })

        # items 포함 조회
        loaded = await q_repo.get_with_items(question.id)
        assert loaded is not None
        assert len(loaded.items) == 1
        assert loaded.items[0].type == "MOTIVATION"

    async def test_get_not_found_returns_none(self, session: AsyncSession):
        """존재하지 않는 자소서 조회 시 None을 반환한다."""
        repo = ResumeQuestionRepository(session)
        result = await repo.get_with_items(99999999)
        assert result is None


# ============================================================
# Resume API 엔드포인트 테스트
# ============================================================
class TestResumeAPI:
    """Resume API 통합 테스트."""

    async def test_list_questions_empty(self, client: AsyncClient, job_seeker_user: User):
        """GET /api/resume/questions — 자소서 없는 사용자는 빈 목록 반환."""
        response = await client.get("/api/resume/questions", params={"user_id": job_seeker_user.id})

        assert response.status_code == 200
        data = response.json()
        assert data == []

    async def test_create_question_success(self, client: AsyncClient, job_seeker_user: User):
        """POST /api/resume/questions — 자소서 세트 생성 성공."""
        response = await client.post(
            "/api/resume/questions",
            params={"user_id": job_seeker_user.id},
            json={
                "title": "카카오 개발직군 자소서",
                "applicant_type": "NEW",
                "items": [
                    {"type": "MOTIVATION", "content": "지원 동기를 서술하시오.", "order_index": 0},
                    {"type": "COMPETENCY", "content": "핵심 역량을 서술하시오.", "order_index": 1},
                ],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "카카오 개발직군 자소서"
        assert data["user_id"] == job_seeker_user.id
        assert len(data["items"]) == 2

    async def test_get_question_not_found(self, client: AsyncClient):
        """GET /api/resume/questions/{id} — 존재하지 않는 세트 조회 시 404."""
        response = await client.get("/api/resume/questions/99999999")

        assert response.status_code == 404

    async def test_create_question_missing_title(self, client: AsyncClient, job_seeker_user: User):
        """POST /api/resume/questions — 제목 없으면 422 반환."""
        response = await client.post(
            "/api/resume/questions",
            params={"user_id": job_seeker_user.id},
            json={"applicant_type": "NEW", "items": []},
        )

        assert response.status_code == 422

    async def test_list_questions_after_create(self, client: AsyncClient, job_seeker_user: User):
        """자소서 세트 생성 후 목록 조회 시 포함되어 있다."""
        # 생성
        await client.post(
            "/api/resume/questions",
            params={"user_id": job_seeker_user.id},
            json={"title": "네이버 자소서", "items": []},
        )

        # 목록 조회
        response = await client.get("/api/resume/questions", params={"user_id": job_seeker_user.id})
        assert response.status_code == 200
        data = response.json()
        titles = [q["title"] for q in data]
        assert "네이버 자소서" in titles
