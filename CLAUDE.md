클로드 코드가 실수를 할 때마다 규칙을 추가하는 파일
- 목표: 작업을 진행하며 코딩 스타일과 아키텍처 규칙을 자체적으로 학습하고 개선해 스스로 오류를 수정하도록 함

---

## 오류 기록

### [2026-01-08] Task 001: 모듈 경로 충돌 오류

**오류 상황:**
- DEV_GUIDELINES.md에서 명시한 `storm/utils/postgres_connector.py` 경로 대신 `knowledge_storm/utils/postgres_connector.py`를 생성하려 함
- 그러나 `knowledge_storm/utils.py` 파일이 이미 존재하는 상태에서 `knowledge_storm/utils/` 폴더를 생성
- Python이 폴더를 모듈로 인식하여 기존 `utils.py`의 클래스들(`ArticleTextProcessing` 등)을 임포트할 수 없게 됨

**원인:**
- Python에서 `package/module.py`와 `package/module/` 폴더가 동시에 존재할 경우, 폴더가 우선권을 가짐
- 기존 코드베이스의 여러 파일들이 `from .utils import ArticleTextProcessing` 형태로 임포트하고 있었음

**해결 방안:**
- `knowledge_storm/utils/` 폴더 이름을 `knowledge_storm/db/`로 변경
- PostgresConnector는 `knowledge_storm.db.PostgresConnector`로 임포트

**교훈 (규칙 추가):**
1. **새 모듈 생성 전 기존 모듈명 확인 필수**: 같은 이름의 `.py` 파일이 존재하는지 반드시 확인할 것
2. **기존 임포트 패턴 분석**: `grep_search`로 해당 모듈을 임포트하는 코드를 먼저 검색할 것
3. **폴더 생성 시 대안 이름 고려**: `utils/` 대신 목적에 맞는 이름 사용 (예: `db/`, `connectors/`, `adapters/`)

---

## 완료된 작업

### [2026-01-08] Task 001: PostgresConnector 구현 ✓
- **파일**: `knowledge_storm/db/postgres_connector.py`
- **기능**: PostgreSQL DB 벡터 유사도 검색, Context Look-back 로직
- **임포트**: `from knowledge_storm.db import PostgresConnector`

### [2026-01-08] Task 002: PostgresRM 구현 ✓
- **파일**: `knowledge_storm/rm.py` (클래스 추가)
- **기능**: STORM 엔진 호환 `dspy.Retrieve` 래퍼 클래스
- **임포트**: `from knowledge_storm.rm import PostgresRM`
- **주요 메서드**:
  - `forward(query_or_queries, exclude_urls=[], k=None)` → `dspy.Prediction` 반환
  - `get_usage_and_reset()` → 사용량 추적
  - `close()` → 연결 종료
- **특징**: `min_score` 임계값 미만 결과에 대한 경고 로그 (하이브리드 검색 준비)

### [2026-01-08] Task 003: Enterprise STORM Runner 구현 ✓
- **파일**: `examples/run_enterprise_storm.py` (신규 생성)
- **기능**: PostgresRM을 사용한 기업 분석 리포트 일괄 생성
- **실행**: `python examples/run_enterprise_storm.py [options]`
- **주요 기능**:
  - 5개 기본 분석 주제 배치 처리 (ANALYSIS_TARGETS)
  - PostgresRM(k=10, min_score=0.5) 기본 설정
  - 진행 상황 로그 출력 `[1/5] Processing: '...'`
  - 토픽별 출력 디렉토리 자동 생성 (덮어쓰기 방지)
  - CLI 옵션: `--topics`, `--search-top-k`, `--min-score`, `--max-conv-turn` 등

