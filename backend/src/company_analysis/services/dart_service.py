import contextlib
import logging
import re
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import dart_fss as dart
import pandas as pd
from bs4 import BeautifulSoup
from src.common.config import CHUNK_CONFIG, DART_CONFIG, TARGET_SECTIONS


logger = logging.getLogger(__name__)


class DartService:
    """
    DART 전자공시 시스템 연동 서비스
    역할: 1. API 통신, 2. HTML 다운로드, 3. 파싱 (HTML -> Structured Dict)
    """

    def __init__(self):
        self.api_key = DART_CONFIG.get("api_key")
        if not self.api_key:
            logger.warning("⚠️ DART_API_KEY is missing.")
        else:
            dart.set_api_key(api_key=self.api_key)

        self._corp_list = None

    # ==================== 1. Optimized Core Data Access ====================

    @property
    def corp_list(self):
        if self._corp_list is None:
            logger.info("🔄 Loading DART Corp List (Heavy Operation)...")
            try:
                self._corp_list = dart.get_corp_list()
                logger.info(f"✅ Loaded {len(self._corp_list)} corporations.")
            except Exception as e:
                logger.error(f"Failed to load corp list: {e}")
                self._corp_list = None
        return self._corp_list

    def get_corp_by_code(self, corp_code: str) -> Any | None:
        """
        [O(1) Search] 고유번호(corp_code)로 Corp 객체 찾기
        """
        if not self.corp_list:
            return None
        return self.corp_list.find_by_corp_code(corp_code)

    def get_corp_by_stock_code(self, stock_code: str) -> Any | None:
        """
        [O(1) Search] 종목코드(stock_code)로 Corp 객체 찾기
        라이브러리 내부 해시맵(_stock_codes) 활용
        """
        if not self.corp_list:
            return None
        return self.corp_list.find_by_stock_code(stock_code)

    # ==================== 2. API Fetch Logic ====================

    def search_all_reports(self, bgn_de: str | None = None, end_de: str | None = None) -> list[Any]:
        """
        기간 내 제출된 모든 사업보고서를 검색 (Efficient Mode)
        """
        if not end_de:
            end_de = datetime.now().strftime("%Y%m%d")

        # 3개월 제한 로직 (Safety Clamp)
        if not bgn_de:
            bgn_dt = datetime.strptime(end_de, "%Y%m%d") - timedelta(days=90)
            bgn_de = bgn_dt.strftime("%Y%m%d")

        logger.info(f"🔍 Searching all reports: {bgn_de} ~ {end_de}")

        all_reports = []
        page_no = 1

        while True:
            try:
                report_type = DART_CONFIG.get("report_type_code", "a001")
                if isinstance(report_type, str):
                    report_type = [report_type]

                # dart.search 모듈 함수 사용 (전체 검색용)
                res = dart.search(
                    bgn_de=bgn_de,
                    end_de=end_de,
                    pblntf_detail_ty=report_type,
                    last_reprt_at="Y",  # [필수] 최종본만
                    page_no=page_no,
                    page_count=100,
                )

                # SearchResults 객체의 리스트 추출
                current_list = getattr(res, "report_list", []) if hasattr(res, "report_list") else res
                if not current_list:
                    break

                all_reports.extend(current_list)

                total_page = getattr(res, "total_page", 1)
                if page_no >= total_page:
                    break
                page_no += 1
                time.sleep(0.5)  # Rate Limit 준수

            except Exception as e:
                logger.error(f"Search failed at page {page_no}: {e}")
                break

        return all_reports

    def get_corps_with_reports(self, bgn_de: str | None = None) -> list[Any]:
        """
        최근 보고서가 있는 기업의 'Corp 객체' 리스트 반환
        """
        all_reports = self.search_all_reports(bgn_de=bgn_de)
        if not all_reports:
            return []

        unique_codes = {r.corp_code for r in all_reports if hasattr(r, "corp_code")}

        targets = []
        for code in unique_codes:
            corp = self.get_corp_by_code(code)
            if corp:
                targets.append(corp)

        return targets

    def get_annual_report(self, corp_code: str, days: int = 365) -> Any:
        """특정 기업의 최신 사업보고서 1건 조회"""
        try:
            end_de = datetime.now().strftime("%Y%m%d")
            start_dt = datetime.now() - timedelta(days=days)
            bgn_de = start_dt.strftime("%Y%m%d")

            report_type = DART_CONFIG.get("report_type_code", "a001")
            if isinstance(report_type, str):
                report_type = [report_type]

            search_results = dart.search(
                corp_code=corp_code,
                bgn_de=bgn_de,
                end_de=end_de,
                pblntf_detail_ty=report_type,
                last_reprt_at="Y",
            )
            return search_results[0] if search_results else None

        except Exception as e:
            logger.error(f"Failed to search report for {corp_code}: {e}")
            return None

    def extract_company_info(self, corp_obj) -> dict:
        """
        기업 기본 정보 추출 (DB 저장용)
        """
        return {
            "corp_code": getattr(corp_obj, "corp_code", None),
            "company_name": getattr(corp_obj, "corp_name", None),
            "stock_code": getattr(corp_obj, "stock_code", None),
            # dart-fss Corp 객체는 sector, product 속성을 가짐
            "sector": getattr(corp_obj, "sector", None),
            "product": getattr(corp_obj, "product", None),
            # industry_code는 보통 corp_info 상세 조회(API Call)를 해야 나오므로
            # 리스트 조회 단계에서는 None으로 둠 (나중에 필요하면 채움)
            "industry_code": None,
        }

    def extract_report_metadata(self, report, corp_obj) -> dict[str, Any]:
        """
        기업 보고서 메타데이터 추출 (DB 저장용)
        """
        return {
            "title": getattr(report, "report_nm", "No Title"),
            "rcept_no": getattr(report, "rcept_no", None),
            "rcept_dt": getattr(report, "rcept_dt", None),
            # Corp 객체 기준 정보도 일부 포함
            "corp_code": getattr(corp_obj, "corp_code", None),
            "corp_name": getattr(corp_obj, "corp_name", None),
            "stock_code": getattr(corp_obj, "stock_code", None),
            "report_type": "annual",
        }

    # ==================== 3. Parsing Logic (HTML -> Chunks) ====================

    def parse_report_sections(self, report) -> list[dict[str, Any]]:
        """HTML 파싱 메인 로직"""
        all_raw_chunks = []
        global_sequence = 0

        if not report:
            return []

        rcept_no = getattr(report, "rcept_no", getattr(report, "rcp_no", "Unknown"))
        logger.info(f"   📂 Parsing Report: {getattr(report, 'report_nm', 'No Title')} ({rcept_no})")

        # 섹션별 순회
        # DART API 특성상 '첨부' 문서에서 본문을 찾아야 할 수도 있음
        # dart-fss는 extract_text()나 pages 속성을 제공함

        try:
            # pages가 로드되지 않았다면 로드 시도
            if not hasattr(report, "pages") or not report.pages:
                with contextlib.suppress(BaseException):
                    report.extract_pages()

            for section_name in TARGET_SECTIONS:
                # 섹션 이름으로 페이지 찾기 (예: "사업의 내용", "II. 사업의 내용" 등)
                found_pages = []

                # 1. Exact Match 시도
                if hasattr(report, "pages"):
                    for page in report.pages:
                        if section_name in page.title:
                            found_pages.append(page)

                # 2. sub_docs 검색 시도 (legacy method)
                if not found_pages and hasattr(report, "sub_docs"):
                    for title, url in report.sub_docs.items():
                        if section_name in title:
                            # 이 경우 별도 처리가 필요하지만 dart-fss 최신 버전은 pages로 통합됨
                            pass

                if not found_pages:
                    continue

                logger.info(f"   📖 Found Section '{section_name}' ({len(found_pages)} pages)")

                for page in found_pages:
                    html_content = page.html
                    if not html_content:
                        continue

                    soup = BeautifulSoup(html_content, "html.parser")
                    # 섹션 헤더 등 불필요한 태그 제거 로직 추가 가능

                    chunks = self._parse_html_to_chunks(soup, section_name, global_sequence)
                    if chunks:
                        global_sequence += len(chunks)
                        all_raw_chunks.extend(chunks)

        except Exception as e:
            logger.error(f"Parsing Error: {e}")

        return all_raw_chunks

    def _parse_html_to_chunks(self, soup, section_path: str, start_seq: int) -> list[dict[str, Any]]:
        """HTML DOM 순회 및 청크 생성"""
        blocks = []
        current_seq = start_seq
        text_buffer = []

        def flush_buffer():
            nonlocal current_seq
            if not text_buffer:
                return

            # [1] _clean_text 사용 (텍스트 정제)
            raw_text = "\n".join(text_buffer)
            clean_content = self._clean_text(raw_text)  # <-- 호출

            if not clean_content:
                text_buffer.clear()
                return

            # [2] _chunk_text 사용 (텍스트 분할)
            # 텍스트가 길면 여러 개의 청크로 쪼개짐
            chunks = self._chunk_text(clean_content)  # <-- 호출

            for chunk in chunks:
                blocks.append(
                    {
                        "chunk_type": "text",
                        "raw_content": chunk,
                        "section_path": section_path,
                        "sequence_order": current_seq,
                        "meta_info": {},
                    }
                )
                current_seq += 1

            text_buffer.clear()

        # ... (DOM 순회 로직) ...
        for elem in soup.recursiveChildGenerator():
            if isinstance(elem, str):
                text_content = elem.strip()
                if text_content:
                    text_buffer.append(text_content)

            elif elem.name == "table":
                flush_buffer()

                md, meta = self._table_to_markdown(elem)
                if md:
                    blocks.append(
                        {
                            "chunk_type": "table",
                            "raw_content": md,
                            "section_path": section_path,
                            "sequence_order": current_seq,
                            "table_metadata": meta,
                            "meta_info": {},
                        }
                    )
                    current_seq += 1
            elif elem.name in ["br", "p", "div", "li", "tr"]:
                text_buffer.append("\n")

        flush_buffer()
        return blocks

    # ==================== 4. Helper Methods ====================

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.replace("\xa0", " ").replace("\r", "").strip()

    def _chunk_text(self, text: str) -> list[str]:
        chunk_size = CHUNK_CONFIG.get("max_chunk_size", 1000)
        overlap = CHUNK_CONFIG.get("overlap", 100)
        min_size = CHUNK_CONFIG.get("min_chunk_size", 50)

        if len(text) <= chunk_size:
            return [text] if len(text) >= min_size else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                for sep in ["\n\n", "\n", ". "]:
                    last_sep = text[start:end].rfind(sep)
                    if last_sep > chunk_size // 2:
                        end = start + last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if len(chunk) >= min_size:
                chunks.append(chunk)

            start = end - overlap
        return chunks

    def _table_to_markdown(self, table_element) -> tuple[str, dict]:
        try:
            dfs = pd.read_html(StringIO(str(table_element)), flavor="bs4")
            if not dfs:
                return "", {}
            df = dfs[0].fillna("")

            meta = {
                "rows": len(df),
                "cols": len(df.columns),
                "columns": [str(c) for c in df.columns],
            }
            caption = table_element.find("caption")
            if caption:
                meta["title"] = caption.get_text(strip=True)

            return df.to_markdown(index=False), meta
        except Exception as e:
            text = table_element.get_text(separator=" ", strip=True)
            return f"[표 데이터]\n{text}", {"error": str(e)}
