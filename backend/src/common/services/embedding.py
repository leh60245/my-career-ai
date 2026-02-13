import asyncio
import inspect
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from openai import AsyncOpenAI


try:
    from ..config import EMBEDDING_CONFIG
except ImportError:
    EMBEDDING_CONFIG = {
        "provider": "openai",
        "openai_model": "text-embedding-3-small",
        "hf_model": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        "dimension": 1536,
        "batch_size": 32,
        "max_length": 512,
    }

logger = logging.getLogger(__name__)


def get_optimal_device() -> str:
    """Return the best available accelerator."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class BaseEmbedder(ABC):
    """임베딩 생성기 추상 기본 클래스"""

    @abstractmethod
    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        [Async] 텍스트 리스트에 대한 임베딩 벡터 반환
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """임베딩 차원 수 반환"""
        pass

    async def aclose(self) -> None:
        """Optional async close hook for underlying clients."""
        return


class OpenAIEmbedder(BaseEmbedder):
    """
    OpenAI API 기반 비동기 임베딩 생성기 (AsyncOpenAI)
    """

    def __init__(self, model_name: str | None = None, api_key: str | None = None):
        self.model_name = model_name or EMBEDDING_CONFIG.get("openai_model", "text-embedding-3-small")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        # 1536 for text-embedding-3-small, 3072 for large
        self._dimension = 1536 if "small" in self.model_name else 3072
        if "dimension" in EMBEDDING_CONFIG:
            self._dimension = EMBEDDING_CONFIG["dimension"]

        if not self.api_key:
            logger.warning("⚠️ OPENAI_API_KEY is missing. Embeddings will fail.")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.info(f"✅ OpenAI Async Embedder initialized: {self.model_name}")

    def get_dimension(self) -> int:
        return self._dimension

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts or not self.client:
            return []

        try:
            # 공백/Newlines 정리 (임베딩 품질 향상)
            sanitized_texts = [text.replace("\n", " ") for text in texts]

            # Async API 호출
            response = await self.client.embeddings.create(input=sanitized_texts, model=self.model_name)

            # OpenAI는 입력 순서를 보장함
            return [data.embedding for data in response.data]

        except Exception as e:
            logger.error(f"Failed to generate embeddings (OpenAI): {e}")
            return []

    async def aclose(self) -> None:
        if not self.client:
            return
        close_fn = getattr(self.client, "aclose", None) or getattr(self.client, "close", None)
        if not close_fn:
            return
        result = close_fn()
        if inspect.isawaitable(result):
            await result


class HuggingFaceEmbedder(BaseEmbedder):
    """
    HuggingFace 로컬 모델 기반 임베딩 생성기
    CPU/GPU 연산이 무거우므로 ThreadPoolExecutor에서 실행하여 이벤트 루프 차단 방지
    """

    def __init__(self, model_name: str | None = None, device: str | None = None, batch_size: int | None = None):
        self.model_name = model_name or EMBEDDING_CONFIG.get("hf_model", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
        self.batch_size = batch_size or EMBEDDING_CONFIG.get("batch_size", 32)
        self.device = device or get_optimal_device()

        logger.info(f"🔄 Loading HuggingFace model: {self.model_name} on {self.device.upper()}")

        # Lazy Import
        from transformers import AutoModel, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()

        self._dimension = self.model.config.hidden_size
        logger.info(f"✅ HuggingFace Model loaded (dim: {self._dimension})")

    def get_dimension(self) -> int:
        return self._dimension

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        """[Sync] 실제 연산 수행 (Blocking)"""
        import torch

        all_embeddings = []
        # Batch Processing
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]

            encoded_input = self.tokenizer(batch, padding=True, truncation=True, max_length=512, return_tensors="pt")
            encoded_input = {k: v.to(self.device) for k, v in encoded_input.items()}

            with torch.no_grad():
                model_output = self.model(**encoded_input)

            # Mean Pooling
            token_embeddings = model_output[0]
            attention_mask = encoded_input["attention_mask"]

            input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            embeddings = sum_embeddings / sum_mask

            # Normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            all_embeddings.extend(embeddings.cpu().tolist())

        return all_embeddings

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """[Async Wrapper] ThreadPool에서 동기 메서드 실행"""
        if not texts:
            return []

        loop = asyncio.get_running_loop()
        try:
            # CPU Blocking 방지를 위해 별도 스레드에서 실행
            return await loop.run_in_executor(None, self._embed_sync, texts)
        except Exception as e:
            logger.error(f"Failed to generate embeddings (HF): {e}")
            return []


class Embedding:
    """
    통합 임베딩 서비스 (Singleton & Strategy Pattern)
    IngestionService 및 검색 서비스에서 공통으로 사용
    """

    _instance: Optional["Embedding"] = None
    _embedder: BaseEmbedder | None = None

    def __new__(cls, provider: str | None = None, **kwargs):
        target_provider = provider or EMBEDDING_CONFIG.get("provider", "openai")

        # 인스턴스가 없거나 프로바이더가 바뀌면 재생성
        if cls._instance is None or cls._instance._provider != target_provider:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False

        return cls._instance

    def __init__(self, provider: str | None = None, **kwargs):
        if getattr(self, "_initialized", False):
            return

        self._provider = provider or EMBEDDING_CONFIG.get("provider", "openai")
        logger.info(f"🚀 Initializing EmbeddingService with provider: {self._provider}")

        if self._provider == "openai":
            self._embedder = OpenAIEmbedder(**kwargs)
        elif self._provider == "huggingface":
            self._embedder = HuggingFaceEmbedder(**kwargs)
        else:
            raise ValueError(f"Unsupported provider: {self._provider}")

        self._initialized = True

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        [Standard Async Interface]
        텍스트 리스트를 입력받아 임베딩 벡터 리스트를 반환합니다.
        """
        if not self._embedder:
            logger.error("Embedder not initialized.")
            return []

        return await self._embedder.get_embeddings(texts)

    async def aclose(self) -> None:
        if self._embedder and hasattr(self._embedder, "aclose"):
            await self._embedder.aclose()

    @property
    def dimension(self) -> int:
        if not self._embedder:
            raise RuntimeError("Embedder not initialized.")
        return self._embedder.get_dimension()

    @classmethod
    def get_instance(cls) -> Optional["Embedding"]:
        return cls._instance
