# 🚨 Critical Bug Fixes & Schema Improvements

## Overview
**Date**: 2026-01-16  
**Priority**: P0 (Critical)  
**Author**: Enterprise STORM Team

이 문서는 데이터 정합성과 스키마 무결성 관련 중요 수정 사항을 기록합니다.

## Fixed Issues

### 1. Silent Failure in Batch Insert (P0)

#### Problem
`DBManager.insert_materials_batch()` 메서드가 loop 처리 중 일부 블록 저장 실패 시 **조용히 스킵**하는 버그가 있었습니다.

```python
# 🔴 BEFORE (BUG):
def insert_materials_batch(self, report_id, blocks):
    count = 0
    for block in blocks:
        if self.insert_source_material(...):  # 실패 시 조용히 넘어감
            count += 1
    return count
# 결과: 콘솔에는 "2087개 블록 저장 완료"로 보이지만, 
#       실제 DB에는 1번 Report만 저장되고 2번부터는 0개
```

#### Impact
- Report ID 1번: 정상 저장
- Report ID 2번 이상: **0개 블록 저장** (데이터 유실)
- 사용자는 "등록 완료" 로그를 보고 정상이라고 착각

#### Fix
```python
# ✅ AFTER (FIXED):
def insert_materials_batch(self, report_id, blocks):
    count = 0
    for idx, block in enumerate(blocks):
        success = self.insert_source_material(...)
        if not success:
            error_msg = f"블록 저장 실패 (report_id={report_id}, block_idx={idx})"
            print(f"❌ {error_msg}")
            raise Exception(error_msg)  # 즉시 예외 전파
        count += 1
    return count
```

#### Files Changed
- `src/ingestion/db_manager.py` (Line 331-369)

#### Verification
```bash
python -m scripts.run_ingestion --test
python -m verify.verify_fix_ingest_loop
```

Expected Result:
```
✅ Report ID 1 (삼성전자): 2,087개 블록
✅ Report ID 2 (SK하이닉스): 2,259개 블록
✅ Report ID 3 (NAVER): 2,505개 블록
```

---

### 2. Schema Normalization - FK Addition (P0)

#### Problem
`Generated_Reports` 테이블이 `company_name` 문자열로만 기업을 식별하여:
- 조인 성능 저하 (인덱스 비효율)
- 데이터 무결성 미보장 (오타 시 orphan data)
- RDB의 장점 미활용

```sql
-- 🔴 BEFORE (문제):
CREATE TABLE "Generated_Reports" (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,  -- FK 없음!
    ...
);
```

#### Fix
```sql
-- ✅ AFTER (개선):
CREATE TABLE "Generated_Reports" (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,  -- 하위 호환성 유지
    company_id INTEGER REFERENCES "Companies"(id) ON DELETE CASCADE,  -- NEW!
    ...
);

CREATE INDEX idx_generated_reports_company_id 
ON "Generated_Reports"(company_id);
```

#### Files Changed
- `src/ingestion/db_manager.py` (Line 130-157): `init_db()` 스키마 수정
- `src/ingestion/db_manager.py` (Line 400-459): `insert_generated_report()` 시그니처 변경
- `scripts/run_storm.py` (Line 368-384): `save_report_to_db()` 로직 업데이트

#### Migration Strategy
```python
# db_manager.py의 insert_generated_report()
def insert_generated_report(self, company_name, ..., company_id=None):
    # company_id가 없으면 company_name으로 자동 조회
    if company_id is None:
        company = self.get_company_by_name(company_name)
        if company:
            company_id = company['id']
    
    # 양쪽 모두 저장 (하위 호환성)
    sql = """
        INSERT INTO "Generated_Reports" 
        (company_name, company_id, ...) 
        VALUES (%s, %s, ...)
    """
```

#### Verification
```bash
# DB 재생성 (테이블 DROP 후 새 스키마로 생성)
python -m scripts.run_ingestion --test

# 스키마 확인
python -m verify.verify_fix_ingest_loop
```

Expected Output:
```
✅ company_id 컬럼 존재 확인 (타입: integer)
✅ FK 제약조건 'fk_company' 존재
```

---

## Testing Checklist

모든 ingestion 코드 수정 후 다음을 실행해야 합니다:

```bash
# 1. Test Mode 실행 (3개 기업, DB 초기화 포함)
python -m scripts.run_ingestion --test

# 2. 검증 스크립트 실행
python -m verify.verify_fix_ingest_loop

# 3. DB 통계 확인
python -m scripts.run_ingestion --stats
```

**Pass Criteria:**
- [ ] 3개 기업 모두 Source_Materials에 블록 저장 (6,851개 이상)
- [ ] Report ID 2번, 3번도 블록 개수 > 0
- [ ] Generated_Reports 테이블에 company_id 컬럼 존재
- [ ] FK 제약조건 'fk_company' 존재
- [ ] 성공률 100% (실패 0개)

---

## Best Practices (Learned from This Bug)

### 1. Error Handling in Loops
**NEVER silently skip errors in batch operations.**

```python
# ❌ BAD
for item in items:
    if process(item):  # 실패 시 조용히 스킵
        count += 1

# ✅ GOOD
for item in items:
    if not process(item):
        raise Exception(f"Failed: {item}")
    count += 1
```

### 2. FK vs String Matching
**Always use FK for entity relationships.**

```python
# ❌ BAD
INSERT INTO reports (company_name) VALUES ('삼성전자')
SELECT * FROM reports WHERE company_name = '삼성전자'  # 느림, 오타 위험

# ✅ GOOD
INSERT INTO reports (company_id) VALUES (1)
SELECT * FROM reports r 
JOIN companies c ON r.company_id = c.id  # 빠름, 안전
```

### 3. DB Schema Migration
**When changing init_db(), always provide migration path.**

```python
# Option 1: Reset DB (dev/test)
python -m scripts.run_ingestion --test

# Option 2: Migration script (production)
# scripts/migrate_add_company_id_fk.py
```

### 4. Verification After Every Change
**No code change is complete without verification.**

```bash
# Always run these 3 commands:
1. python -m scripts.run_ingestion --test
2. python -m verify.verify_fix_ingest_loop
3. python -m scripts.run_ingestion --stats
```

---

## Related Documents
- [Data Ingestion Guidelines](.github/instructions/ingestion.instructions.md)
- [DB Schema Documentation](docs/FEAT-001-EntityBias-Report.md)
- [CLAUDE.md](CLAUDE.md) - Full error history and solutions

---

## Approval Log
- **Identified by**: Tech Leader (2026-01-16 14:30)
- **Fixed by**: AI Developer (2026-01-16 14:30-15:00)
- **Verified by**: Automated Test Suite (2026-01-16 15:00)
- **Status**: ✅ Deployed to `main` branch
