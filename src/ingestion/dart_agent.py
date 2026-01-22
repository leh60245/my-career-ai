"""
DART 보고서 에이전트 모듈 (Refactored)

PHASE 3.5: Legacy Code Migration
- Removed legacy parsing logic (Advanced/Page-Sync versions)
- Standardized on 'Sequential Block Processing' used by Pipeline v3
- Cleaned up dependencies and type hints

DART API를 통해 사업보고서를 수집하고, RAG에 최적화된 형태로 파싱합니다.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import dart_fss as dart
import pandas as pd
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

# [통합 아키텍처] 설정 로드
from src.common.config import CHUNK_CONFIG, DART_CONFIG, TARGET_SECTIONS

logger = logging.getLogger(__name__)

# 레거시 호환 변수
DART_API_KEY = DART_CONFIG.get("api_key")
REPORT_SEARCH_CONFIG = {
    "bgn_de": DART_CONFIG.get(
        "search_start_date", (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    ),  # noqa: E501
    "pblntf_detail_ty": DART_CONFIG.get("report_type_code", "a001"),
    "page_count": DART_CONFIG.get("page_count", 100),
    "page_delay_sec": DART_CONFIG.get("page_delay_sec", 0.5),
    "max_search_days": DART_CONFIG.get("max_search_days", 90),
}

BEGIN_DATE_LIMIT = REPORT_SEARCH_CONFIG["bgn_de"]
END_DATE_LIMIT = datetime.now().strftime("%Y%m%d")


class DartReportAgent:
    """
    DART API 에이전트.
    사업보고서 검색 및 HTML 파싱(순차적 블록 추출)을 담당합니다.
    """

    def __init__(self):
        """에이전트 초기화 및 DART API 설정"""
        if not DART_API_KEY:
            logger.warning("⚠️ DART_API_KEY is missing in configuration.")
        else:
            dart.set_api_key(api_key=DART_API_KEY)

        self._corp_list = None

    @property
    def corp_list(self):
        """기업 리스트 (Lazy Loading)"""
        if self._corp_list is None:
            logger.info("🔄 Loading DART Corp List...")
            try:
                self._corp_list = dart.get_corp_list()
                logger.info(f"✅ Loaded {len(self._corp_list)} corporations.")
            except Exception as e:
                logger.error(f"Failed to load corp list: {e}")
                self._corp_list = []
        return self._corp_list

    # ==================== 기업 및 보고서 검색 ====================

    def get_corp_by_stock_code(self, stock_code: str):
        """종목코드로 기업 정보 조회"""
        for corp in self.corp_list:
            if corp.stock_code == stock_code:
                return corp
        return None

    def get_listed_corps(self) -> list:
        """상장 기업 필터링"""
        return [c for c in self.corp_list if c.stock_code]

    def get_annual_report(
        self, corp_code: str, bgn_de: str = BEGIN_DATE_LIMIT
    ) -> Any | None:
        """사업보고서 검색 (최신 1건)"""
        bgn_de = bgn_de or REPORT_SEARCH_CONFIG["bgn_de"]
        try:
            search_results = dart.search(
                corp_code=corp_code,
                bgn_de=bgn_de,
                pblntf_detail_ty=REPORT_SEARCH_CONFIG["pblntf_detail_ty"],
            )
            return search_results[0] if search_results else None
        except Exception as e:
            logger.error(f"Failed to search report for {corp_code}: {e}")
            return None

    def search_all_reports(
        self,
        bgn_de: str = BEGIN_DATE_LIMIT,
        end_de: str = END_DATE_LIMIT,
        corp_code: str = None,
    ) -> list[Any]:
        """
        기간 내 모든 사업보고서를 일괄 검색 (Efficient Mode용)
        """
        if end_de is None:
            end_de = datetime.now().strftime("%Y%m%d")
        if bgn_de is None:
            bgn_de = REPORT_SEARCH_CONFIG["bgn_de"]

        # 기간 제한 로직
        if corp_code is None:
            max_days = REPORT_SEARCH_CONFIG.get("max_search_days", 90)
            bgn_date = datetime.strptime(bgn_de, "%Y%m%d")
            end_date = datetime.strptime(end_de, "%Y%m%d")
            if (end_date - bgn_date).days > max_days:
                bgn_date = end_date - timedelta(days=max_days)
                bgn_de = bgn_date.strftime("%Y%m%d")
                logger.warning(
                    f"⚠️ Search period limited to {max_days} days: {bgn_de} ~ {end_de}"
                )

        all_reports = []
        page_no = 1
        page_count = REPORT_SEARCH_CONFIG.get("page_count", 100)

        logger.info(f"📋 Searching reports: {bgn_de} ~ {end_de}")

        while True:
            try:
                search_kwargs = {
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "pblntf_detail_ty": REPORT_SEARCH_CONFIG["pblntf_detail_ty"],
                    "page_count": page_count,
                    "page_no": page_no,
                }
                if corp_code:
                    search_kwargs["corp_code"] = corp_code

                res = dart.filings.search(**search_kwargs)
                report_list = getattr(res, "report_list", []) or []

                if not report_list:
                    break

                all_reports.extend(report_list)
                total_page = getattr(res, "total_page", 1) or 1

                if page_no >= total_page:
                    break
                page_no += 1
                time.sleep(REPORT_SEARCH_CONFIG.get("page_delay_sec", 0.5))

            except Exception as e:
                logger.error(f"Search failed at page {page_no}: {e}")
                break

        return all_reports

    def get_corps_with_reports(
        self, bgn_de: str = BEGIN_DATE_LIMIT, end_de: str = END_DATE_LIMIT
    ) -> list[tuple]:
        """
        보고서가 존재하는 기업 목록 반환 (중복 제거)
        Returns: [(CorpObject, ReportObject), ...]
        """
        all_reports = self.search_all_reports(bgn_de, end_de)
        if not all_reports:
            return []

        # 기업별 최신 보고서 선별
        corp_latest = {}
        for r in all_reports:
            code = getattr(r, "corp_code", None)
            dt = getattr(r, "rcept_dt", "")
            if code not in corp_latest or dt > getattr(
                corp_latest[code], "rcept_dt", ""
            ):
                corp_latest[code] = r

        results = []
        for r in corp_latest.values():
            corp = self.get_corp_by_corp_code(getattr(r, "corp_code", None))
            if corp:
                results.append((corp, r))

        return results

    def get_report_info(self, report) -> dict:
        """DB 저장을 위한 메타데이터 추출"""
        return {
            "title": report.report_nm,
            "rcept_no": report.rcept_no,
            "rcept_dt": report.rcept_dt,
            "corp_code": report.corp_code,
            "corp_name": report.corp_name,
            "report_type": "annual",
        }

    # ==================== 핵심 파싱 로직 (Sequential Block) ====================

    def extract_target_sections_sequential(self, report) -> list[dict]:
        """
        [Main Parsing Method]
        핵심 섹션들을 순차적 블록(Sequential Block) 방식으로 추출합니다.
        문서의 흐름(Header -> Text -> Table)을 유지합니다.
        """
        extracted = []
        global_sequence = 0

        for section_name in TARGET_SECTIONS:
            section_data = self._extract_section_sequential(report, section_name)
            if section_data:
                # 시퀀스 번호 재조정 (섹션 간 연속성 보장)
                blocks = section_data.get("blocks", [])
                for block in blocks:
                    block["sequence_order"] = global_sequence
                    global_sequence += 1

                extracted.append(section_data)
                logger.info(f"   ✅ Extracted '{section_name}': {len(blocks)} blocks")
            else:
                logger.debug(f"   ⚠️ Section '{section_name}' not found")

        return extracted

    def _extract_section_sequential(self, report, section_keyword: str) -> dict | None:
        try:
            result = report.find_all(includes=section_keyword)
            pages = result.get("pages", [])
            if not pages:
                return None

            all_blocks = []

            # 페이지별 순회
            for page in pages:
                soup = BeautifulSoup(page.html, "html.parser")
                page_title = getattr(page, "title", section_keyword)

                # 재귀적 파싱
                blocks = self._parse_sequential_blocks(
                    soup.body if soup.body else soup,
                    current_path=page_title,
                    start_sequence=0,  # 임시 시퀀스 (나중에 재조정됨)
                )
                all_blocks.extend(blocks)

            return {
                "chapter": section_keyword,
                "blocks": all_blocks,
                "page_count": len(pages),
            }
        except Exception as e:
            logger.error(f"Parsing failed for '{section_keyword}': {e}")
            return None

    def _parse_sequential_blocks(
        self, container, current_path: str, start_sequence: int
    ) -> list[dict]:
        """HTML 요소를 순회하며 텍스트/테이블 블록 생성"""
        blocks = []
        sequence = start_sequence
        text_buffer = []
        header_tags = ["h1", "h2", "h3", "h4", "h5", "h6"]

        def flush_text_buffer():
            nonlocal sequence
            if not text_buffer:
                return

            combined_text = self._clean_text("\n".join(text_buffer))
            if len(combined_text) >= CHUNK_CONFIG["min_chunk_size"]:
                # 청크 분할
                chunks = self.chunk_text(combined_text)
                for chunk in chunks:
                    blocks.append(
                        {
                            "chunk_type": "text",
                            "section_path": current_path,
                            "content": chunk,
                            "sequence_order": sequence,
                            "table_metadata": None,
                            "raw_content": chunk,  # for compatibility
                        }
                    )
                    sequence += 1
            text_buffer.clear()

        def process_element(element):
            nonlocal current_path, sequence

            if isinstance(element, NavigableString):
                text = str(element).strip()
                if text:
                    text_buffer.append(text)
                return

            if not isinstance(element, Tag):
                return
            tag = element.name

            # 1. Header: Flush & Update Path
            if tag in header_tags:
                flush_text_buffer()
                header_text = element.get_text(strip=True)
                if header_text:
                    current_path = self._update_path(current_path, header_text, tag)
                return

            # 2. Table: Flush & Parse
            if tag == "table":
                flush_text_buffer()
                md_table, meta = self.convert_table_to_markdown(element)
                if md_table:
                    blocks.append(
                        {
                            "chunk_type": "table",
                            "section_path": current_path,
                            "content": md_table,
                            "sequence_order": sequence,
                            "table_metadata": meta,
                            "raw_content": md_table,
                        }
                    )
                    sequence += 1
                return

            # 3. Block Elements: Append text
            if tag in ["p", "li", "span", "td", "th", "div"]:
                # Note: div/section are containers but sometimes contain direct text
                pass

            # 4. Recursion
            if tag in [
                "div",
                "section",
                "article",
                "body",
                "tr",
                "tbody",
                "thead",
                "p",
                "li",
            ]:
                for child in element.children:
                    process_element(child)
                return

            # Fallback
            text = element.get_text(strip=True)
            if text:
                text_buffer.append(text)

        for child in container.children:
            process_element(child)

        flush_text_buffer()
        return blocks

    # ==================== Helpers ====================

    def _update_path(self, current: str, header: str, tag: str) -> str:
        """헤더 레벨에 따라 섹션 경로 업데이트"""
        level = int(tag[1])
        parts = current.split(" > ") if current else []
        if level <= len(parts):
            parts = parts[: level - 1]
        parts.append(header)
        return " > ".join(parts)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.replace("\xa0", " ").replace("\r", "").strip()

    def chunk_text(self, text: str) -> list[str]:
        """텍스트 청킹"""
        chunk_size = CHUNK_CONFIG["max_chunk_size"]
        overlap = CHUNK_CONFIG["overlap"]
        min_size = CHUNK_CONFIG["min_chunk_size"]

        if len(text) <= chunk_size:
            return [text] if len(text) >= min_size else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            # 문장 경계 보정
            if end < len(text):
                for sep in ["\n\n", "\n", ". "]:
                    last_sep = text[start:end].rfind(sep)
                    if last_sep > chunk_size // 2:
                        end = start + last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if len(chunk) >= min_size:
                chunks.append(chunk)
            elif chunks:  # 너무 작으면 이전 청크에 병합
                chunks[-1] += " " + chunk

            start = end - overlap
        return chunks

    def convert_table_to_markdown(self, table_element) -> tuple[str, dict]:
        """HTML 테이블 -> Markdown 변환"""
        try:
            dfs = pd.read_html(StringIO(str(table_element)), flavor="bs4")
            if not dfs:
                return "", {}
            df = dfs[0].fillna("")

            # 메타데이터
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

    # Legacy Compatibility Methods (Optional)
    def get_corp_by_corp_code(self, corp_code: str):
        for c in self.corp_list:
            if c.corp_code == corp_code:
                return c
        return None
