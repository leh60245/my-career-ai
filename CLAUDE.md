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
