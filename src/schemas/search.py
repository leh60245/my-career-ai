from typing import NotRequired, TypedDict


class SearchResult(TypedDict):
    """
    검색 및 리랭킹 결과 표준 데이터 구조
    (VectorSearchService <-> RerankerService 간 데이터 교환용)
    """

    content: str
    title: str
    url: str
    score: float

    # Optional Internal Metadata
    _company_name: NotRequired[str]
    _intent: NotRequired[str]
    _matched_entities: NotRequired[list[str]]
    source: NotRequired[str]  # 'vector' or 'reranked'
