import logging

from rapidfuzz import fuzz, process


logger = logging.getLogger(__name__)


class CompanyEntityResolver:
    """
    기업명 정규화 및 ID 매핑 클래스
    """

    # 1. 하드코딩된 동의어 사전 (약어 -> 정식 명칭)
    SYNONYM_MAP = {
        # 대기업 약어
        "삼전": "삼성전자",
        "하이닉스": "SK하이닉스",
        "현차": "현대자동차",
        "기아차": "기아",
        "엘지전자": "LG전자",
        "엘전": "LG전자",
        "엘지화학": "LG화학",
        "포스코": "POSCO홀딩스",
        "한전": "한국전력",
        # 영문/한글 혼용
        "samsung": "삼성전자",
        "sk hynix": "SK하이닉스",
        "hynix": "SK하이닉스",
        "lg energy": "LG에너지솔루션",
        "lgensol": "LG에너지솔루션",
        "엔솔": "LG에너지솔루션",
        "naver": "NAVER",
        "kakao": "카카오",
        # 금융권
        "국민은행": "KB금융",
        "신한은행": "신한지주",
        "우리은행": "우리금융지주",
    }

    def __init__(self):
        self.name_to_id: dict[str, int] = {}
        self.company_names: list[str] = []

        logger.info("CompanyEntityResolver initialized (Empty). Waiting for data update.")

    def update_company_map(self, company_map: dict[str, int]) -> None:
        """
        [Server Startup] DB에서 가져온 {name: id} 맵으로 초기화
        """
        self.name_to_id = company_map
        self.company_names = list(company_map.keys())
        logger.info(f"EntityResolver updated with {len(self.company_names)} companies.")

    def resolve_to_id(self, query: str, threshold: float = 80.0) -> tuple[int | None, str | None]:
        """
        Query -> (Company ID, Canonical Name) 변환

        Returns:
            (id, name) tuple. If not found, returns (None, None).
        """
        if not query or not self.name_to_id:
            return None, None

        clean_query = query.strip()

        # 1. Exact Match (완전 일치 - 가장 빠름 O(1))
        if clean_query in self.name_to_id:
            return self.name_to_id[clean_query], clean_query

        # 2. Synonym Match (동의어 사전 - O(1))
        # 띄어쓰기 제거 및 소문자 변환 후 확인
        normalized_key = clean_query.replace(" ", "").lower()
        if normalized_key in self.SYNONYM_MAP:
            canonical = self.SYNONYM_MAP[normalized_key]
            # 동의어가 실제 DB 목록에 있는지 확인 (ID 조회)
            if canonical in self.name_to_id:
                return self.name_to_id[canonical], canonical

        # 3. Fuzzy Match (유사도 검색 - O(N))
        # score_cutoff: 80점 미만은 과감하게 버림 (안전 제일)
        match = process.extractOne(clean_query, self.company_names, scorer=fuzz.WRatio, score_cutoff=threshold)

        if match:
            # match format: (found_string, score, index)
            best_match, score, _ = match
            logger.debug(f"Entity Resolution (Fuzzy): '{query}' -> '{best_match}' (Score: {score:.2f})")
            return self.name_to_id[best_match], best_match

        # 4. 매칭 실패
        return None, None
