import inspect
import logging

from openai import AsyncOpenAI
from src.common.config import AI_CONFIG
from src.company_analysis.schemas.llm_query_analysis_result import LLMQueryAnalysisResult


logger = logging.getLogger(__name__)


class LLMQueryAnalyzer:
    def __init__(self):
        # 분석용 모델은 싸고 빠른 모델(gpt-4o-mini) 사용 권장
        self.client = AsyncOpenAI(api_key=AI_CONFIG["openai_api_key"])
        self.model = "gpt-4o-mini"

    async def aclose(self) -> None:
        """Close underlying async HTTP client to avoid shutdown loop errors."""
        if not self.client:
            return
        close_fn = getattr(self.client, "aclose", None) or getattr(self.client, "close", None)
        if not close_fn:
            return
        result = close_fn()
        if inspect.isawaitable(result):
            await result

    async def analyze(self, query: str) -> LLMQueryAnalysisResult:
        """
        LLM을 사용하여 사용자 질문을 분석하고 구조화된 데이터를 반환합니다.
        """
        system_prompt = """
        You are an expert Query Analyst for a financial RAG system.
        Analyze the user's question and extract structured information.

        - intent: 'factoid', 'analytical', 'comparison', or 'general'.
        - target_companies: Extract specific company names (Max 5).
        - search_topics: Classify the question into relevant report sections.
        - keywords: Extract key terms for search.

        [Guidelines for 'target_companies']
        1. Extract explicit company names.
        2. If the user mentions a group/sector (e.g., "Semiconductor leaders"), list the top relevant Korean companies (Max 5).
        3. **IMPORTANT**: Always output the **Official Korean Name** if the company is Korean (e.g., use "삼성전자", not "Samsung Electronics" or "SamJeon").
        4. If no company is mentioned, return an empty list.

        [Guidelines for 'search_topics']
        - "Revenue", "Profit", "Table" -> 'financial'
        - "CEO", "Executives", "Shareholders" -> 'management'
        - "Market share", "Products", "Competitors" -> 'business_overview'
        - "Lawsuit", "Regulation" -> 'risk'
        - "Environment", "Donation" -> 'esg'

        [Guidelines for 'is_competitor_query']
        - Set to True if the user asks for comparison, ranking, or competitors.
        """

        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
                response_format=LLMQueryAnalysisResult,
                temperature=0.0,
                max_tokens=500,
            )
            result = response.choices[0].message.parsed

            if result is None:
                raise ValueError("Structured output parsing failed (result is None)")

            logger.debug(
                f"🔍 Analyzed: Intent={result.intent}, "
                f"Topics={result.search_topics}, "
                f"Companies={result.target_companies}"
            )

            return result

        except Exception as e:
            logger.error(f"Query Analysis Failed: {e}")

            return LLMQueryAnalysisResult(
                intent="general",
                target_companies=[],
                is_competitor_query=False,
                search_topics=["general"],
                time_period=None,
                keywords=[query],
            )
