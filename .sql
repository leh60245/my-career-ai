-- 1. 확장 기능 활성화 (Vector 검색 지원)
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================
-- 2. 테이블 생성 (Tables)
-- ==========================================

-- [1] 기업 정보 테이블 (Companies)
-- 기업의 고유 식별 정보와 기본 메타데이터를 저장합니다.
CREATE TABLE "Companies" (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL UNIQUE, -- 기업명 (중복 불가)
    corp_code VARCHAR(20),                     -- DART 고유 번호
    stock_code VARCHAR(20),                    -- 상장 종목 코드
    industry VARCHAR(100),                     -- 업종 정보
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- [2] 분석 리포트 테이블 (Analysis_Reports)
-- 특정 시점의 사업보고서 헤더 정보를 저장합니다. Companies 테이블과 1:N 관계입니다.
CREATE TABLE "Analysis_Reports" (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL,               -- FK: Companies.id
    title VARCHAR(500),                        -- 보고서 제목 (예: 사업보고서 (2023.12))
    rcept_no VARCHAR(20) UNIQUE,               -- 접수번호 (DART API 식별자)
    rcept_dt VARCHAR(10),                      -- 접수일자 (YYYYMMDD)
    report_type VARCHAR(50) DEFAULT 'annual',  -- 보고서 유형
    basic_info JSONB,                          -- 기타 메타데이터 (JSON)
    status VARCHAR(50) DEFAULT 'Raw_Loaded',   -- 처리 상태
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- [3] 원천 데이터 테이블 (Source_Materials)
-- 보고서의 실제 내용(텍스트/테이블)을 순차적 블록으로 저장합니다. Analysis_Reports와 1:N 관계입니다.
CREATE TABLE "Source_Materials" (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL,                -- FK: Analysis_Reports.id
    chunk_type VARCHAR(20) NOT NULL DEFAULT 'text', -- 데이터 타입 ('text' 또는 'table')
    section_path TEXT,                         -- 문서 내 경로 (예: II. 사업의 내용 > 1. 개요)
    sequence_order INTEGER,                    -- 문서 내 등장 순서 (정렬 기준)
    raw_content TEXT,                          -- 본문 텍스트 또는 Markdown 변환된 테이블
    table_metadata JSONB,                      -- 테이블 관련 메타데이터
    embedding vector(768),                     -- 768차원 임베딩 벡터 (pgvector)
    metadata JSONB,                            -- 추가 정보 (문맥 주입 여부 등)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. 관계 설정 (Foreign Keys)
-- ==========================================

-- Analysis_Reports -> Companies (N:1)
ALTER TABLE "Analysis_Reports"
    ADD CONSTRAINT fk_reports_company
    FOREIGN KEY (company_id)
    REFERENCES "Companies" (id)
    ON DELETE CASCADE;

-- Source_Materials -> Analysis_Reports (N:1)
ALTER TABLE "Source_Materials"
    ADD CONSTRAINT fk_materials_report
    FOREIGN KEY (report_id)
    REFERENCES "Analysis_Reports" (id)
    ON DELETE CASCADE;

-- ==========================================
-- 4. 인덱스 생성 (Indexes)
-- ==========================================

-- 검색 성능 향상을 위한 B-Tree 인덱스
CREATE INDEX idx_companies_corp_code ON "Companies"(corp_code);
CREATE INDEX idx_source_materials_report_sequence ON "Source_Materials"(report_id, sequence_order);
CREATE INDEX idx_source_materials_chunk_type ON "Source_Materials"(report_id, chunk_type);

-- ==========================================
-- 5. 주석 (Comments - ERD 가독성 향상)
-- ==========================================

COMMENT ON TABLE "Companies" IS '상장 기업 기본 정보';
COMMENT ON TABLE "Analysis_Reports" IS 'DART 사업보고서 헤더 및 메타데이터';
COMMENT ON TABLE "Source_Materials" IS '보고서 내 텍스트 및 테이블 데이터 블록 (RAG 원천)';

COMMENT ON COLUMN "Source_Materials".chunk_type IS 'text: 일반 텍스트, table: 마크다운 표';
COMMENT ON COLUMN "Source_Materials".sequence_order IS '문서 복원 및 문맥 파악을 위한 순서';
COMMENT ON COLUMN "Source_Materials".embedding IS 'HuggingFace 모델 기반 768차원 벡터';