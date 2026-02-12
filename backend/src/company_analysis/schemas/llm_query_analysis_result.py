from typing import Literal

from pydantic import BaseModel, Field


class LLMQueryAnalysisResult(BaseModel):
    intent: Literal["factoid", "analytical", "comparison", "general"] = Field(
        ...,
        description="Query intent. Use 'factoid' for specific data points, 'analytical' for reasoning.",
    )

    target_companies: list[str] = Field(
        default_factory=list,
        description="Extract explicit company names. If asking about a sector (e.g., 'Semiconductor'), list top players. Max 5.",
    )

    is_competitor_query: bool = Field(
        False,
        description="True if comparison or ranking is needed (triggers broader search).",
    )

    search_topics: list[Literal["financial", "management", "business_overview", "risk", "esg", "general"]] = Field(
        default_factory=lambda: ["general"],
        description="Identify the relevant sections of the annual report. "
        "- financial: Revenue, profit, tables, financial statements. "
        "- management: Executives, board members, shareholders. "
        "- business_overview: Market share, industry analysis, products. "
        "- risk: Legal issues, risk factors. "
        "- esg: Environment, social, governance.",
    )

    time_period: str | None = Field(
        None, description="Specific time context (e.g., '2024 Q1', '2023'). Used for query expansion."
    )

    keywords: list[str] = Field(default_factory=list, description="Keywords for vector search ranking.")
