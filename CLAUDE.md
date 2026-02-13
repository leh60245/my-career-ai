# Project: My Career AI (Human-Centric Career Agent)

구직자의 취업 준비 전 과정을 지원하는 AI 기반 취업 의사결정 및 코칭 서비스입니다.
Stanford STORM 기반의 기업 분석(RAG)과 'Context-Aware Multi-Agent' 논문을 응용한 자소서 코칭 시스템이 결합된 Modular Monolith 플랫폼입니다.

## 1. Architecture (Modular Monolith)

### Backend (`/backend`)

- **Core**: FastAPI (Async), SQLAlchemy 2.0+ (AsyncSession), Pydantic V2
- **Common (`/backend/src/common`)**: 전역에서 공유하는 커널
  - `database/`: DB 연결(`connection.py`) 및 마이그레이션(`migrations/`) **[인프라]**
  - `models/`: `Base` 모델 등 공통 엔티티 **[계층]**
  - `repositories/`: `BaseRepository` 등 공통 데이터 접근 로직 **[계층]**
  - `schemas/`: 공통 Pydantic 스키마 **[계층]**
  - `enums.py`: 전역 상수 (UserRole, AffiliationType 등)
  - `config.py`: 환경 변수 로드
  - `utils.py`: 공통 유틸리티

### Domains (`/backend/src/`)

1. **User Domain (`/user`)**
    - **역할**: 인증(Auth), 프로필 관리, 소속(Affiliation) 기반 권한 제어
    - **핵심 모델**: `User` (통합 계정), `JobSeekerProfile` (구직자), `ManagerProfile` (관리자), `Affiliation` (소속)
2. **Company Domain (`/company`)**
    - **역할**: 기업 심층 분석, 인재상 관리, RAG 리포트 생성
    - **핵심 모델**: `Company`, `CompanyTalent` (인재상), `AnalysisReport`
    - **엔진**: Enterprise STORM (Wiki-style retrieval)
3. **Resume Domain (`/resume`)**
    - **역할**: 자소서 작성 가이드 및 논리적 첨삭 (Ghostwriting 금지)
    - **핵심 모델**: `ResumeQuestion` (세트), `ResumeItem` (문항), `ResumeDraft` (버전관리), `ResumeFeedback` (AI 피드백)

### Frontend (`/frontend/react-app`)

- **Stack**: React 18, Vite, Material UI (MUI) v5
- **State**: React Context API + Custom Hooks

## 2. Coding Standards

### Python (Backend)

- **Async Only**: DB I/O 및 LLM 호출 시 반드시 `async/await` 사용 (Blocking 코드 금지).
- **Type Hinting**: 모든 함수 시그니처에 타입 명시 (Pydantic 모델 적극 활용).
- **Docstring**: Google Style 사용, 한글로 작성.
- **Import Rule**: 절대 경로 사용 권장 (e.g., `from src.common.database.connection import get_db`).
- **DDD Principle**: 타 도메인의 모델을 직접 Import 하지 말고, Service 계층을 통해 호출하거나 ID 참조(Loose Coupling)를 지향.

### JavaScript/React (Frontend)

- **Functional Components**: 클래스형 컴포넌트 금지, Hooks 사용.
- **Named Exports**: `export default` 지양, `export const Component = ...` 사용.
- **Styling**: MUI `sx` prop 또는 `@emotion/styled` 사용 (CSS 파일 별도 생성 지양).

## 3. Commands

### Backend

- `cd backend` 후 실행
- **서버 실행 (Dev)**: `python -m uvicorn main:app --reload --port 8000 --reload-dir src`
- **DB 마이그레이션 적용**: `alembic upgrade head`
- **새 마이그레이션 생성**: `alembic revision --autogenerate -m "메시지"`
- **테스트 실행**: `pytest` (비동기 테스트는 `pytest-asyncio` 사용)

### Frontend

- `cd frontend/react-app` 후 실행
- **개발 서버**: `npm run dev`
- **빌드**: `npm run build`
- **Lint**: `npm run lint`

### Infrastructure

- **전체 실행**: `docker-compose up -d` (PostgreSQL, Ollama 실행)

## 4. Important Notes

- **보안**: `.env` 파일과 `functional_specification_documents/`, `wishlist.md` 파일은 절대 커밋하지 마세요.
- **데이터 흐름**: `Resume` 서비스는 `Company` 도메인의 데이터를 참조하지만, `Company` 테이블을 직접 수정하지 않습니다 (Read-Only or Service Call).
- **확장성**: 사용자(User)는 `Affiliation`을 통해 B2B/B2G(대학, 공공기관)로 확장 가능하도록 설계되었습니다.
- **AI 원칙**: 자소서 서비스는 '대필'이 아닌 '코칭'에 집중합니다. (Context-Aware Multi-Agent Framework)
