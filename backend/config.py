"""
Backend Configuration Module
Centralized configuration for topics, companies, and system settings
"""

# ============================================================
# Topic (분석 주제) Configuration
# ============================================================
# Key-Value 구조로 정의하여 확장성 확보
# - id: 주제의 고유 식별자 (프론트/백 통신용)
# - label: UI에 표시될 주제명
TOPICS = [
    {
        "id": "T01",
        "label": "기업 개요 및 주요 사업 내용",
        "description": "회사의 설립배경, 주요 사업영역, 조직구조 등"
    },
    {
        "id": "T02",
        "label": "최근 3개년 재무제표 및 재무 상태 분석",
        "description": "매출, 영업이익, 순이익, 자산, 부채 등 재무지표 분석"
    },
    {
        "id": "T03",
        "label": "산업 내 경쟁 우위 및 경쟁사 비교 (SWOT)",
        "description": "강점, 약점, 기회, 위협 분석 및 경쟁사 벤치마킹"
    },
    {
        "id": "T04",
        "label": "주요 제품 및 서비스 시장 점유율 분석",
        "description": "제품별 매출 구성, 시장 점유율, 고객 분석"
    },
    {
        "id": "T05",
        "label": "R&D 투자 현황 및 기술 경쟁력",
        "description": "연구개발비, 보유 특허, 기술 트렌드"
    },
    {
        "id": "T06",
        "label": "ESG (환경, 사회, 지배구조) 평가",
        "description": "지속가능성, 사회책임, 투명성 등"
    },
    {
        "id": "custom",
        "label": "직접 입력",
        "description": "사용자 정의 분석 주제"
    }
]

# ============================================================
# Topic Helper Functions
# ============================================================

def get_topic_label_by_id(topic_id: str) -> str:
    """
    Topic ID로 label을 조회합니다.
    
    Args:
        topic_id: TOPICS 리스트의 id 값
        
    Returns:
        해당하는 label 또는 None
    """
    for topic in TOPICS:
        if topic["id"] == topic_id:
            return topic["label"]
    return None


def is_custom_topic(topic_id: str) -> bool:
    """
    사용자 정의 주제(custom)인지 확인합니다.
    """
    return topic_id == "custom"


def get_predefined_topics():
    """
    미리 정의된 주제 목록만 반환합니다. (custom 제외)
    """
    return [t for t in TOPICS if t["id"] != "custom"]


# ============================================================
# API Response Format
# ============================================================

def format_topic_list():
    """
    Frontend용 주제 리스트 포맷입니다.
    GET /api/topics 엔드포인트에서 사용됩니다.
    """
    return [
        {
            "id": topic["id"],
            "label": topic["label"],
            "description": topic.get("description", ""),
        }
        for topic in TOPICS
    ]
