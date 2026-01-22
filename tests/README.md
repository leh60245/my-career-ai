# Test Suite for Enterprise STORM

이 디렉토리는 STORM 파이프라인의 전체 테스트 스위트를 포함합니다.

## 📋 목차

- [테스트 구조](#테스트-구조)
- [설치 및 설정](#설치-및-설정)
- [테스트 실행](#테스트-실행)
- [테스트 작성 가이드](#테스트-작성-가이드)
- [문제 해결](#문제-해결)

---

## 🏗️ 테스트 구조

```
tests/
├── conftest.py                 # 공통 Fixture (DB 세션, 테스트 데이터)
├── integration/                # 실제 DB 연결이 필요한 통합 테스트
│   ├── test_db_connection.py   # DB 연결 및 스키마 검증
│   └── test_repositories.py    # Repository CRUD 및 관계 매핑 테스트
└── unit/                       # Mock을 사용한 단위 테스트
    └── test_generation_service.py  # Service Layer 로직 테스트
```

### 테스트 유형

| 유형 | 위치 | DB 필요 | 속도 | 목적 |
|------|------|---------|------|------|
| **단위 테스트** | `tests/unit/` | ❌ | 빠름 | 로직 검증 (Mock 사용) |
| **통합 테스트** | `tests/integration/` | ✅ | 느림 | DB 연동 검증 |

---

## 🚀 설치 및 설정

### 1. 필수 패키지 설치

```bash
# 테스트 의존성 설치
pip install pytest pytest-asyncio pytest-mock pytest-cov

# 또는 requirements.txt가 있다면
pip install -r requirements.txt
```

### 2. 환경 변수 확인

테스트는 실제 데이터베이스에 연결하므로, `.env` 파일 또는 환경 변수가 올바르게 설정되어야 합니다:

```bash
# .env 파일 예시
DB_HOST=localhost
DB_PORT=5432
DB_NAME=enterprise_storm_db
DB_USER=your_username
DB_PASSWORD=your_password
```

⚠️ **주의**: 통합 테스트는 실제 DB에 연결하므로, 운영 DB가 아닌 개발/테스트 DB를 사용하세요!

---

## 🧪 테스트 실행

### 기본 실행

```bash
# 프로젝트 루트에서 모든 테스트 실행
pytest tests/ -v

# 특정 디렉토리만 실행
pytest tests/unit/ -v           # 단위 테스트만
pytest tests/integration/ -v    # 통합 테스트만

# 특정 파일만 실행
pytest tests/integration/test_db_connection.py -v

# 특정 테스트 함수만 실행
pytest tests/unit/test_generation_service.py::TestGenerationServiceInitialization::test_service_requires_both_repositories -v
```

### 마커 기반 실행

```bash
# 단위 테스트만 실행 (빠름)
pytest -m unit -v

# 통합 테스트만 실행 (DB 필요)
pytest -m integration -v

# 느린 테스트 제외
pytest -m "not slow" -v
```

### 코드 커버리지 측정

```bash
# 커버리지와 함께 테스트 실행
pytest tests/ --cov=src --cov-report=html

# HTML 리포트는 htmlcov/index.html에 생성됨
```

### 상세 출력 옵션

```bash
# 더 자세한 출력
pytest tests/ -vv

# 실패한 테스트만 재실행
pytest tests/ --lf

# 첫 번째 실패에서 중단
pytest tests/ -x

# 로그 출력 활성화
pytest tests/ --log-cli-level=DEBUG
```

---

## 📝 테스트 작성 가이드

### 통합 테스트 작성 예시

```python
# tests/integration/test_my_feature.py
import pytest
from src.database.repositories import MyRepository

@pytest.mark.asyncio
@pytest.mark.integration
async def test_my_feature(db_session):
    """
    내 기능을 테스트합니다.
    
    db_session은 conftest.py에서 자동 제공됩니다.
    """
    repo = MyRepository(db_session)
    
    # 테스트 데이터 생성
    result = await repo.create({"name": "Test"})
    
    # 검증
    assert result.id is not None
    assert result.name == "Test"
```

### 단위 테스트 작성 예시

```python
# tests/unit/test_my_service.py
import pytest
from unittest.mock import AsyncMock
from src.services import MyService

@pytest.mark.asyncio
@pytest.mark.unit
async def test_my_service_logic():
    """
    서비스 로직을 Mock을 사용해 테스트합니다.
    """
    # Mock 리포지토리 생성
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = {"id": 1, "name": "Test"}
    
    # 서비스 생성 및 테스트
    service = MyService(mock_repo)
    result = await service.process_data(1)
    
    # 검증
    assert result["name"] == "Test"
    mock_repo.get_by_id.assert_called_once_with(1)
```

### Fixture 사용

`conftest.py`에서 제공하는 Fixture들:

| Fixture | 설명 | Scope |
|---------|------|-------|
| `event_loop` | 비동기 이벤트 루프 | session |
| `db_engine` | 데이터베이스 엔진 | session |
| `db_session` | DB 세션 (자동 롤백) | function |
| `test_company_data` | 테스트용 회사 데이터 | function |
| `test_company` | 생성된 테스트 회사 인스턴스 | function |

---

## 🔧 문제 해결

### 일반적인 오류

#### 1. `ImportError: No module named 'src'`

**원인**: Python이 프로젝트 루트를 찾지 못함

**해결**:

```bash
# 프로젝트 루트에서 실행
cd c:\Users\remote\Project\enterprise-storm
pytest tests/ -v

# 또는 PYTHONPATH 설정
set PYTHONPATH=%cd%
pytest tests/ -v
```

#### 2. `asyncio.exceptions.TimeoutError`

**원인**: 비동기 테스트 타임아웃

**해결**: `pytest.ini`에서 타임아웃 증가

```ini
[pytest]
asyncio_default_fixture_loop_scope = session
```

#### 3. `sqlalchemy.exc.ProgrammingError: relation "Companies" does not exist`

**원인**: 테이블 이름 대소문자 불일치

**확인 사항**:

- 모델의 `__tablename__`이 실제 DB 테이블 이름과 일치하는지 확인
- PostgreSQL은 대소문자를 구분하므로 정확한 이름 사용

#### 4. `fixture 'db_session' not found`

**원인**: `conftest.py`가 인식되지 않음

**해결**:

- `tests/__init__.py` 파일이 존재하는지 확인
- pytest 실행 위치가 프로젝트 루트인지 확인

#### 5. 테스트 데이터가 DB에 남아있음

**원인**: 세션이 롤백되지 않음

**해결**: `conftest.py`의 `db_session` fixture가 올바르게 설정되었는지 확인

---

## 📊 테스트 커버리지 목표

| 모듈 | 목표 커버리지 |
|------|--------------|
| `src/database/models/` | 80%+ |
| `src/database/repositories/` | 90%+ |
| `src/services/` | 85%+ |
| `src/common/` | 70%+ |

---

## 🎯 핵심 테스트 체크리스트

### DB 연결 테스트

- ✅ 엔진 초기화
- ✅ 테이블 존재 확인
- ✅ 기본 쿼리 실행
- ✅ 트랜잭션 커밋/롤백

### Repository 테스트

- ✅ CRUD 작업
- ✅ 관계(Relationship) 로딩
- ✅ 외래 키 제약 조건
- ✅ 예외 처리

### Service 테스트

- ✅ 메서드 시그니처
- ✅ 필수 필드 검증
- ✅ 비즈니스 로직
- ✅ 에러 핸들링

---

## 🚀 CI/CD 통합

### GitHub Actions 예시

```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      
      - name: Run tests
        env:
          DB_HOST: localhost
          DB_PORT: 5432
          DB_NAME: test_db
          DB_USER: postgres
          DB_PASSWORD: testpass
        run: |
          pytest tests/ -v --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## 📚 참고 자료

- [Pytest 공식 문서](https://docs.pytest.org/)
- [pytest-asyncio 문서](https://pytest-asyncio.readthedocs.io/)
- [SQLAlchemy Testing 가이드](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#session-frequently-asked-questions)

---

## 💡 팁

1. **테스트 격리**: 각 테스트는 독립적이어야 합니다. 다른 테스트의 결과에 의존하지 마세요.

2. **의미 있는 이름**: 테스트 함수명은 무엇을 테스트하는지 명확히 표현해야 합니다.

   ```python
   # ❌ 나쁜 예
   def test_company()
   
   # ✅ 좋은 예
   def test_create_company_with_valid_data()
   ```

3. **AAA 패턴**: Arrange(준비) - Act(실행) - Assert(검증) 구조를 따르세요.

4. **빠른 피드백**: 단위 테스트를 먼저 실행하고, 통과하면 통합 테스트를 실행하세요.

5. **Mock 활용**: DB 없이 로직만 테스트할 수 있으면 단위 테스트로 작성하세요.

---

**작성일**: 2026-01-21  
**작성자**: Enterprise Architecture Team  
**문의**: [프로젝트 Issue 트래커]
