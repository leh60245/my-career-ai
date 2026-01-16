---
applyTo: "src/ingestion/**/*.py"
---

# Data Ingestion Guidelines

When working on `src/ingestion/`:

## 1. One-Way Data Flow
- This module's ONLY job is to write to PostgreSQL.
- It should NOT depend on `knowledge_storm` logic.
- All DB operations MUST use `DBManager` context manager pattern.

## 2. Error Handling - NO SILENT FAILURES ⚠️
**CRITICAL**: Loop 처리 중 에러는 즉시 전파되어야 합니다.

```python
# ❌ WRONG - Silent Failure
for item in items:
    if process_item(item):  # 실패 시 조용히 스킵
        count += 1

# ✅ CORRECT - Fail Fast
for item in items:
    success = process_item(item)
    if not success:
        raise Exception(f"Failed to process item: {item}")
    count += 1
```

### Key Methods with Strict Error Handling:
- `DBManager.insert_materials_batch()`: 블록 저장 실패 시 즉시 예외 발생
- `DBManager.insert_source_material()`: DB 에러 시 False 반환 후 상위에서 체크
- `DataPipeline._process_single_corp()`: 예외 발생 시 try-except로 로깅 후 False 반환

## 3. DB Schema - FK Enforcement
**모든 테이블은 정규화된 관계를 유지해야 합니다.**

### Generated_Reports Table Schema:
```sql
CREATE TABLE "Generated_Reports" (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,  -- 하위 호환성 유지
    company_id INTEGER REFERENCES "Companies"(id) ON DELETE CASCADE,  -- ✅ NEW
    topic TEXT NOT NULL,
    report_content TEXT,
    toc_text TEXT,
    references_data JSONB,
    conversation_log JSONB,
    meta_info JSONB,
    model_name VARCHAR(50) DEFAULT 'gpt-4o',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Insert Pattern (company_id 자동 조회):
```python
def insert_generated_report(self, company_name, ..., company_id=None):
    # company_id가 없으면 company_name으로 조회
    if company_id is None:
        company = self.get_company_by_name(company_name)
        if company:
            company_id = company['id']
    
    # INSERT with both company_name (legacy) and company_id (FK)
    sql = """
        INSERT INTO "Generated_Reports" 
        (company_name, company_id, topic, ...) 
        VALUES (%s, %s, %s, ...)
    """
    cursor.execute(sql, (company_name, company_id, topic, ...))
```

## 4. Metadata Enforcement
**Every chunk MUST have these metadata fields:**
- `company_name` (str): MANDATORY for entity filtering in RAG
- `corp_code` (str): RECOMMENDED for traceability
- `rcept_no` (str): RECOMMENDED for source linking
- `source` (str): Always "dart"

Example:
```python
common_metadata = {
    "source": "dart",
    "company_name": corp_name,  # 필수!
    "corp_code": corp_code,
    "rcept_no": report_info.get('rcept_no')
}
```

## 5. Transaction Management
```python
# ✅ CORRECT - Context Manager Auto-Commit
with DBManager() as db:
    company_id = db.insert_company(name, corp_code, stock_code)
    report_id = db.insert_report(company_id, report_meta)
    count = db.insert_materials_batch(report_id, blocks, metadata=common_metadata)
    # Auto-commit on __exit__ if no exception
    # Auto-rollback on __exit__ if exception occurred
```

## 6. Testing Requirements
After ANY ingestion logic change, you MUST run these tests:

```bash
# Step 1: Run test mode (3 companies)
python -m scripts.run_ingestion --test

# Step 2: Verify data integrity
python -m verify.verify_fix_ingest_loop

# Step 3: Check DB stats
python -m scripts.run_ingestion --stats
```

**Expected Output:**
- 3 companies (삼성전자, SK하이닉스, NAVER)
- 6,851+ blocks in Source_Materials
- All 3 reports must have blocks (NO report with 0 blocks)
- 0 failures (100% success rate)

## 7. Common Pitfalls (Learned Lessons)

### ❌ Silent Failure Example (Fixed in 2026-01-16):
```python
# BEFORE (BUG):
def insert_materials_batch(self, report_id, blocks):
    count = 0
    for block in blocks:
        if self.insert_source_material(...):  # 실패 시 조용히 스킵
            count += 1
    return count  # 로그는 "저장 완료"인데 실제로는 일부만 저장됨

# AFTER (FIXED):
def insert_materials_batch(self, report_id, blocks):
    count = 0
    for block in blocks:
        success = self.insert_source_material(...)
        if not success:
            raise Exception(f"블록 저장 실패 (report_id={report_id})")
        count += 1
    return count
```

### ❌ String-based Company Matching (Fixed in 2026-01-16):
```python
# BEFORE (BUG):
INSERT INTO "Generated_Reports" (company_name, ...) VALUES ('삼성전자', ...)
# 문제: 조인 시 문자열 매칭으로 느림, 오타 시 orphan data 발생

# AFTER (FIXED):
# 1. Companies 테이블에서 company_id 조회
company_id = db.insert_company(name, corp_code, stock_code)

# 2. FK로 연결
INSERT INTO "Generated_Reports" (company_name, company_id, ...) 
VALUES ('삼성전자', 1, ...)
```

## 8. DB Schema Migration Guidelines
When you modify `DBManager.init_db()`, existing DBs need migration:

```bash
# Option 1: Reset DB (dev environment)
python -m scripts.run_ingestion --test  # --test includes --reset-db

# Option 2: Manual migration (production)
# Create migration script in scripts/migrate_*.py
# See example: scripts/run_migration.py
```

## 9. Performance Considerations
- **Batch Insert**: Use `insert_materials_batch()` instead of individual inserts
- **Index Usage**: Companies.corp_code, Source_Materials.(report_id, sequence_order)
- **Connection Timeout**: Always set `connect_timeout=5` to prevent server hang
- **Commit Frequency**: Commit per report (not per block) for better throughput
