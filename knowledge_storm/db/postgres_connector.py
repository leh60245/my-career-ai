"""
PostgreSQL Vector Search Connector for Enterprise STORM

이 모듈은 PostgreSQL DB의 Source_Materials 테이블에서
pgvector를 활용한 벡터 유사도 검색을 수행합니다.

Database Schema (Source_Materials):
    - id (PK): Integer
    - report_id (FK): Integer (Analysis_Reports 참조)
    - chunk_type: VARCHAR ('text' 또는 'table')
    - section_path: TEXT (섹션 경로)
    - sequence_order: INTEGER (문서 내 등장 순서)
    - raw_content: TEXT (본문 또는 Markdown 표)
    - embedding: vector(768) (pgvector)

Author: Enterprise STORM Team
"""

import os
import logging
from typing import List, Dict

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PostgresConnector:
    """
    PostgreSQL 벡터 검색 커넥터

    DART 보고서 데이터가 저장된 PostgreSQL DB에서
    벡터 유사도 검색을 수행하고 STORM 호환 포맷으로 결과를 반환합니다.

    Attributes:
        conn: psycopg2 데이터베이스 연결 객체
        model: SentenceTransformer 임베딩 모델

    Example:
        >>> connector = PostgresConnector()
        >>> results = connector.search("삼성전자 매출 현황", top_k=5)
        >>> for r in results:
        ...     print(r['title'], r['score'])
    """

    def __init__(self):
        """
        PostgresConnector 초기화

        환경변수에서 DB 접속 정보를 로드하고 연결을 설정합니다.
        sentence_transformers 모델(paraphrase-multilingual-mpnet-base-v2)을 로드합니다.

        Required Environment Variables:
            - PG_HOST: PostgreSQL 호스트 주소
            - PG_PORT: PostgreSQL 포트 (기본값: 5432)
            - PG_USER: 데이터베이스 사용자명
            - PG_PASSWORD: 데이터베이스 비밀번호
            - PG_DATABASE: 데이터베이스 이름

        Raises:
            RuntimeError: DB 연결 정보가 누락되었거나 연결에 실패한 경우
        """
        # 환경변수에서 DB 접속 정보 로드
        self.host = os.environ.get("PG_HOST")
        self.port = os.environ.get("PG_PORT", "5432")
        self.user = os.environ.get("PG_USER")
        self.password = os.environ.get("PG_PASSWORD")
        self.database = os.environ.get("PG_DATABASE")

        # 필수 환경변수 검증
        missing_vars = []
        if not self.host:
            missing_vars.append("PG_HOST")
        if not self.user:
            missing_vars.append("PG_USER")
        if not self.password:
            missing_vars.append("PG_PASSWORD")
        if not self.database:
            missing_vars.append("PG_DATABASE")

        if missing_vars:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing_vars)}. "
                "Please set them in secrets.toml or as environment variables."
            )

        # DB 연결 설정
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
            logger.info(f"Successfully connected to PostgreSQL database: {self.database}")
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to connect to PostgreSQL: {e}")

        # 임베딩 모델 로드 (paraphrase-multilingual-mpnet-base-v2)
        # 768차원 벡터 생성, 다국어 지원
        try:
            self.model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
            logger.info("Successfully loaded SentenceTransformer model")
        except Exception as e:
            raise RuntimeError(f"Failed to load SentenceTransformer model: {e}")

    def _embed_query(self, query: str) -> np.ndarray:
        """
        쿼리 문자열을 벡터로 변환

        Args:
            query: 검색 쿼리 문자열

        Returns:
            768차원 numpy 배열
        """
        embedding = self.model.encode(query, convert_to_numpy=True)
        return embedding

    def _fetch_context_for_tables(
        self,
        table_rows: List[Dict]
    ) -> Dict[tuple, str]:
        """
        테이블 타입 행들에 대해 직전 텍스트(Context Look-back)를 조회

        Args:
            table_rows: chunk_type='table'인 검색 결과 행들

        Returns:
            {(report_id, sequence_order): context_text} 형태의 딕셔너리
        """
        if not table_rows:
            return {}

        context_map = {}

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            for row in table_rows:
                report_id = row['report_id']
                prev_seq = row['sequence_order'] - 1

                if prev_seq < 0:
                    continue

                # 직전 텍스트 조회 (sequence_order - 1)
                cur.execute("""
                    SELECT raw_content, section_path, chunk_type
                    FROM Source_Materials
                    WHERE report_id = %s AND sequence_order = %s
                """, (report_id, prev_seq))

                prev_row = cur.fetchone()
                if prev_row:
                    context_map[(report_id, row['sequence_order'])] = prev_row['raw_content']

        return context_map

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        벡터 유사도 검색 수행

        입력된 쿼리를 벡터화하여 PostgreSQL의 Source_Materials 테이블에서
        가장 유사한 문서들을 검색합니다.

        chunk_type이 'table'인 경우 Context Look-back 로직을 적용하여
        직전 텍스트를 raw_content 앞에 결합합니다.

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 최대 결과 수 (기본값: 5)

        Returns:
            STORM 호환 포맷의 검색 결과 리스트
            [
                {
                    "content": "검색된 본문 내용",
                    "title": "섹션 경로 (section_path)",
                    "url": "dart_report_{report_id}",
                    "score": 0.85  # 코사인 유사도 (1 - distance)
                },
                ...
            ]

        Raises:
            psycopg2.Error: 데이터베이스 쿼리 실행 실패 시
        """
        # 쿼리 임베딩 생성
        query_embedding = self._embed_query(query)

        # numpy 배열을 PostgreSQL vector 형식 문자열로 변환
        embedding_str = "[" + ",".join(map(str, query_embedding.tolist())) + "]"

        results = []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 벡터 유사도 검색 SQL 실행
                # pgvector의 <=> 연산자: 코사인 거리 (0에 가까울수록 유사)
                cur.execute("""
                    SELECT 
                        raw_content, 
                        section_path, 
                        chunk_type, 
                        report_id, 
                        sequence_order,
                        (embedding <=> %s::vector) as distance
                    FROM Source_Materials
                    ORDER BY distance ASC
                    LIMIT %s
                """, (embedding_str, top_k))

                rows = cur.fetchall()

                if not rows:
                    logger.warning(f"No results found for query: {query}")
                    return []

                # Context Look-back: table 타입 행들에 대해 직전 텍스트 조회
                table_rows = [row for row in rows if row['chunk_type'] == 'table']
                context_map = self._fetch_context_for_tables(table_rows)

                # 결과 가공 및 STORM 포맷 변환
                for row in rows:
                    content = row['raw_content']

                    # chunk_type이 'table'인 경우 Context Look-back 적용
                    if row['chunk_type'] == 'table':
                        context_key = (row['report_id'], row['sequence_order'])
                        if context_key in context_map:
                            # 직전 텍스트를 표 앞에 결합
                            prev_text = context_map[context_key]
                            content = f"[문맥: {prev_text}]\n\n[표 데이터]\n{content}"
                        else:
                            # 직전 텍스트가 없으면 section_path를 문맥으로 사용
                            content = f"[섹션: {row['section_path']}]\n\n[표 데이터]\n{content}"

                    # 코사인 거리를 유사도 점수로 변환 (1 - distance)
                    # distance가 0이면 score=1 (완전 일치)
                    score = 1 - float(row['distance'])

                    results.append({
                        "content": content,
                        "title": row['section_path'],
                        "url": f"dart_report_{row['report_id']}",
                        "score": score
                    })

                logger.info(f"Found {len(results)} results for query: {query}")

        except psycopg2.Error as e:
            logger.error(f"Database query failed: {e}")
            raise

        return results

    def close(self):
        """데이터베이스 연결 종료"""
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed")

    def __enter__(self):
        """Context manager 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료 시 연결 해제"""
        self.close()
        return False


# 테스트 코드
if __name__ == "__main__":
    import sys
    import toml
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    def load_api_key(toml_file_path):
        """secrets.toml에서 환경변수 로드 (테스트용 로컬 함수)"""
        try:
            with open(toml_file_path, "r") as file:
                data = toml.load(file)
            for key, value in data.items():
                os.environ[key] = str(value)
        except FileNotFoundError:
            print(f"File not found: {toml_file_path}", file=sys.stderr)
        except toml.TomlDecodeError:
            print(f"Error decoding TOML file: {toml_file_path}", file=sys.stderr)

    # secrets.toml에서 환경변수 로드
    secrets_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "secrets.toml"
    )

    if os.path.exists(secrets_path):
        load_api_key(secrets_path)
        print(f"✓ Loaded secrets from: {secrets_path}")
    else:
        print(f"⚠ secrets.toml not found at: {secrets_path}")
        print("  Please create secrets.toml with PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE")
        sys.exit(1)

    try:
        # PostgresConnector 인스턴스 생성
        print("\n[1] Initializing PostgresConnector...")
        connector = PostgresConnector()
        print("✓ PostgresConnector initialized successfully")

        # 테스트 검색 수행
        test_query = "삼성전자 매출 현황"
        print(f"\n[2] Searching for: '{test_query}'")

        results = connector.search(test_query, top_k=3)

        if results:
            print(f"✓ Found {len(results)} results:\n")
            for i, result in enumerate(results, 1):
                print(f"--- Result {i} ---")
                print(f"  Title: {result['title']}")
                print(f"  URL: {result['url']}")
                print(f"  Score: {result['score']:.4f}")
                print(f"  Content (first 200 chars): {result['content'][:200]}...")
                print()
        else:
            print("⚠ No results found")

        # 연결 종료
        connector.close()
        print("[3] PostgresConnector test completed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

