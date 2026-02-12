# 프로젝트: My Career AI

FastAPI(Async), React + Vite, PostgreSQL(pgvector)를 기반으로 구축된 **AI 기반 기업 분석 보고서 생성 시스템**입니다. Stanford의 STORM 프레임워크를 기업 환경에 맞게 확장하여 RAG 및 LLM(Ollama/Gemini/GPT) 에이전트를 활용합니다.

## 코드 스타일 (Code Style)

### Backend (Python/FastAPI)

* **비동기(Async) 필수**: DB 입출력(`asyncpg`) 및 외부 API 호출 시 반드시 `async/await` 구문을 사용해야 합니다. 동기(Blocking) 코드는 서버 성능을 저하시키므로 금지합니다.
* **Type Hinting**: Pydantic V2를 활용하여 모든 함수 인자와 반환값에 명시적인 타입 힌트를 적용하세요.
* **Layered Architecture 준수**:
* `Controller` (`main.py`, routers)는 비즈니스 로직을 직접 포함하지 않고 `Service`를 호출합니다.
* `Service`는 비즈니스 로직을 담당하며 DB 접근 시 반드시 `Repository`를 경유합니다.
* `Repository`는 순수하게 DB 쿼리(CRUD)만 담당합니다.

### Frontend (React/Vite)

* **Functional Components**: 클래스형 컴포넌트 대신 Hooks를 사용하는 함수형 컴포넌트로 작성하세요.
* **UI 라이브러리**: Material UI(MUI) v5를 기본 디자인 시스템으로 사용합니다. 커스텀 스타일링이 필요한 경우 `@emotion/styled`를 사용하세요.
* **Linter**: ESLint 규칙을 준수하며, `console.log`는 프로덕션 빌드에 포함되지 않도록 주의하세요.

## 명령어 (Commands)

### Backend

* **서버 실행 (개발)**: `python -m uvicorn main:app --reload --port 8000 --reload-dir backend --reload-dir src`
* **서버 실행 (운영)**: `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4`
* **DB 마이그레이션**: `alembic upgrade head` (스키마 변경 시 필수)
* **테스트**: `pytest` (비동기 테스트는 `pytest-asyncio` 플러그인 활용)

### Frontend

* **개발 서버**: `npm run dev` (Vite 실행)
* **빌드**: `npm run build`

### Infrastructure

* **전체 실행**: `docker-compose up -d` (PostgreSQL, Ollama, Portainer 실행)
* **Ollama 모델 Pull**: 실행 중인 컨테이너 내에서 `ollama pull [모델명]` 실행 필요

## 아키텍처 (Architecture)

### 디렉토리 구조

* `/backend`: FastAPI 진입점 (`main.py`) 및 백그라운드 작업 관리 (`storm_service.py`)
* `/src`: 핵심 애플리케이션 로직
* `/src/services`: 비즈니스 로직 계층
* `/src/repositories`: 데이터 액세스 계층 (SQLAlchemy)
* `/src/models` & `/src/schemas`: SQLAlchemy 모델 및 Pydantic 스키마
* `/src/engine`: STORM 파이프라인 엔진 코어

* `/knowledge_storm`: Co-STORM 및 STORM Wiki 관련 모듈 (LLM 에이전트 로직)
* `/frontend/react-app`: React 클라이언트 애플리케이션

###

* `/frontend/demo_light`:

### 데이터베이스

* **PostgreSQL 15**: `pgvector` 확장을 사용하여 벡터 임베딩 저장 및 검색 지원
* **SQLAlchemy 2.0+**: AsyncSession을 사용한 비동기 ORM 패턴 적용

## 중요 사항 (Important Notes)

* **환경 변수 관리**: `.env` 파일에 API 키(OpenAI, Google, DART 등)와 DB 접속 정보를 관리하고, 절대 저장소에 커밋하지 마세요.
* **GPU 가속**: 로컬 LLM(Ollama) 사용 시 `docker-compose.yml`에 정의된 대로 NVIDIA GPU 리소스 예약 설정이 필요합니다. (CUDA 드라이버 확인 필수)
* **경로 설정**: `docker-compose.yml`의 볼륨 경로(`D:/DockerData/...`)는 윈도우 환경 기준으로 설정되어 있습니다. 배포 환경에 맞춰 경로를 수정하세요.
* **의존성**: Python 패키지 추가 시 `requirements.txt`를 갱신해야 하며, 특히 `asyncpg`, `sqlalchemy`, `pydantic` 버전 호환성에 유의하세요.
* **API 응답**: 백그라운드 리포트 생성 작업은 `job_id`를 즉시 반환하고, 프론트엔드에서 `/api/status/{job_id}`를 통해 폴링(Polling)하는 구조입니다.
* **knwoledge_storm 관리**: knwoledge_storm 폴더 내 파일 변경은 최소한으로 해주세요. 만약 기능적으로 수정을 진행해야 한다면 상속이나 import 로 가능한지 우선 판단해주세요.
