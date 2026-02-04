import asyncio
import logging
from collections.abc import Sequence

import torch
from sentence_transformers import CrossEncoder

from src.common import AI_CONFIG
from src.schemas import SearchResult

logger = logging.getLogger(__name__)


class RerankerService:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or AI_CONFIG.get("reranker_model", "BAAI/bge-reranker-v2-m3")
        self.device = self._get_optimal_device()
        logger.info(f"🔄 Loading Reranker model: {self.model_name} on {self.device}")

        # [설정] max_length 명시 (BGE-M3는 보통 8192까지 가능하지만, 메모리/속도를 위해 1024~2048 권장)
        self.model = CrossEncoder(model_name_or_path=self.model_name, device=self.device, max_length=2048)
        logger.info("✅ Reranker model loaded.")

    def _get_optimal_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    async def rerank(self, query: str, docs: Sequence[SearchResult], top_k: int = 10) -> Sequence[SearchResult]:
        """
        비동기 Reranking 메서드.
        Heavy Computation을 ThreadPool에서 실행하여 Event Loop Blocking을 방지함.
        """
        if not docs:
            return []

        # 1. 입력 쌍 생성
        pairs = [(query, doc.get("content", "")) for doc in docs]

        # 2. [핵심] Blocking 방지를 위해 별도 스레드에서 실행
        loop = asyncio.get_running_loop()

        try:
            # run_in_executor의 첫 인자가 None이면 기본 ThreadPoolExecutor 사용
            scores = await loop.run_in_executor(
                None,
                lambda: self.model.predict(
                    pairs,
                    batch_size=32,  # 배치 처리로 메모리 관리
                    show_progress_bar=False,
                    activation_fn=torch.nn.Sigmoid(),  # [중요] Logits -> 0~1 확률값 변환
                ),
            )
        except Exception as e:
            logger.error(f"Reranking failed: {e}. Returning original order.")
            # 실패 시 원본 그대로 반환 (서비스 중단 방지)
            return list(docs)[:top_k]

        # 3. 점수 매핑 및 정렬 (얕은 복사본 생성하여 원본 보존 권장)
        reranked_docs = []
        for _, doc in enumerate(docs):
            new_doc = doc.copy()
            reranked_docs.append(new_doc)

        # 점수 내림차순 정렬
        reranked_docs.sort(key=lambda x: x["score"], reverse=True)

        return reranked_docs[:top_k]
