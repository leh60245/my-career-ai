# My Career AI — Copilot Instructions

## Architecture Overview

Modular Monolith: FastAPI backend + React frontend. Three domains under `backend/src/`:

| Domain | Path | Role |
|--------|------|------|
| **Common** | `backend/src/common/` | Shared kernel — Base model, enums, config, DB connection, BaseRepository |
| **User** | `backend/src/user/` | Auth, profiles, B2B/B2G affiliation-based access |
| **Company** | `backend/src/company/` | Corporate analysis via Stanford STORM (RAG), talent profiles |
| **Resume** | `backend/src/resume/` | Cover letter coaching (NOT ghostwriting) — 4-tier: Question→Item→Draft→Feedback |

**Layering**: Controller (`main.py`) → Service → Repository → Model. Services are injected via `Depends()` + factory classmethod `from_session(cls, session)`.

## Backend Conventions (Python)

- **Async only** — all DB I/O and LLM calls must use `async/await`. No blocking code.
- **SQLAlchemy 2.0 mapped style** — `Mapped[T]` + `mapped_column()`. Models inherit `Base` from `src.common.models.base`.
- **Mixins**: Use `TimestampMixin` (created_at + updated_at) or `CreatedAtMixin` (created_at only).
- **Imports**: Absolute paths required (`from backend.src.common.database.connection import get_db`).
- **Cross-domain**: Never import another domain's models directly. Use service calls or ID references.
- **Type hints**: Required on all function signatures. Use Pydantic V2 models (with `from_attributes = True`).
- **Docstrings**: Google Style, written in Korean.
- **Enums**: Defined in `src/common/enums.py`. Backend uses `StrEnum`.

### Adding a New Model — 3 Required Steps

1. Create the model file (inherit `Base` + appropriate mixin)
2. Add import to `backend/src/common/database/migrations/env.py` (Alembic autogenerate won't detect it otherwise)
3. Add import to `connection.py`'s `ensure_schema()` section

### Repository Pattern

```python
# Inherit BaseRepository[T] with Generic pattern
class MyRepository(BaseRepository[MyModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(MyModel, session)
```

Custom exceptions: `EntityNotFound`, `DuplicateEntity`, `RepositoryError` from `src.common.repositories.base_repository`.

### Service Pattern

```python
class MyService:
    def __init__(self, repo: MyRepository):
        self.repo = repo

    @classmethod
    def from_session(cls, session: AsyncSession) -> "MyService":
        return cls(MyRepository(session))
```

## Frontend Conventions (React)

- Stack: React 18 + Vite + MUI v5. No React Router — view switching via state.
- Use functional components with hooks. No class components.
- Prefer named exports (`export const X = ...`), avoid `export default`.
- Styling: MUI `sx` prop or `@emotion/styled`. No separate CSS files.
- API client: `frontend/react-app/src/services/apiService.js` (axios, baseURL `localhost:8000`).

## Commands

```bash
# Backend (cd backend first, activate conda env 'enterprise-storm')
conda activate enterprise-storm
python -m uvicorn main:app --reload --port 8000 --reload-dir src
alembic upgrade head                              # apply migrations
alembic revision --autogenerate -m "description"  # generate migration

# Frontend (cd frontend/react-app)
npm run dev     # dev server
npm run build   # production build

# Infrastructure
docker-compose up -d   # PostgreSQL (pgvector:pg15) + Ollama (GPU)
```

## Key Gotchas

- **DB singleton**: `AsyncDatabaseEngine` is a singleton — instantiate at module level, call `initialize()` in lifespan.
- **StormService** manages its own sessions (runs in BackgroundTasks, outside FastAPI DI lifecycle).
- **Job status polling**: in-memory `JOBS` dict (real-time progress) checked first, DB as fallback.
- **Embedding dimension**: `SourceMaterial.embedding` is `Vector(768)` — must match `EMBEDDING_CONFIG['dimension']` in `config.py`.
- **ReportJob PK alias**: Python attribute `id` maps to DB column `job_id` via `mapped_column("job_id", ...)`.
- **Ruff**: `line-length = 160`, `target-version = "py311"`. Config in `pyproject.toml`.
- **Sensitive files**: Never commit `.env`, `functional_specification_documents/`, or `wishlist.md`.
