"""
ChromaDB setup + embedding function using HuggingFace Inference Providers API.
No self-hosted model — embeddings are generated via a hosted API call,
so no GPU/CPU load on our own server.

Note: The embedding function itself is fully synchronous because ChromaDB's
EmbeddingFunction interface is synchronous. Callers running in an async
context (FastAPI routes, MCP tools) should wrap collection.query()/add()
calls in asyncio.to_thread() to avoid blocking the event loop.
"""

import time
from typing import List

import chromadb
import numpy as np
from huggingface_hub import InferenceClient
from chromadb import Documents, EmbeddingFunction, Embeddings

from app.config import settings
from app.utils.logger import logger

# --- HuggingFace Inference client (hosted, free tier) ---
_hf_client = InferenceClient(
    provider="hf-inference",
    api_key=settings.hf_api_key,
)

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5


class HFEmbeddingFunction(EmbeddingFunction):
    """
    Custom ChromaDB embedding function that calls the HuggingFace
    Inference API instead of running a model locally. Fully synchronous.
    """

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed_single_with_retry(text) for text in input]

    def _embed_single_with_retry(self, text: str) -> List[float]:
        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                result = _hf_client.feature_extraction(
                    text, model=settings.hf_embedding_model
                )
                return _normalize_embedding_output(result)
            except Exception as e:
                logger.warning(f"HF embedding attempt {attempt} failed: {e}")
                last_error = e
                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        logger.error(f"HF embedding failed after all retries: {last_error}")
        raise last_error


def _normalize_embedding_output(result) -> List[float]:
    """
    Some HF models return a single flat vector (sentence-level),
    others return token-level embeddings (list of lists).
    This ensures we always end up with a single flat vector via mean pooling.
    """
    arr = np.array(result)
    if arr.ndim == 1:
        return arr.tolist()
    elif arr.ndim == 2:
        return arr.mean(axis=0).tolist()
    else:
        raise ValueError(f"Unexpected embedding shape: {arr.shape}")


# --- ChromaDB client (persistent, self-hosted on same VPS) ---
_chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

_embedding_function = HFEmbeddingFunction()


def get_knowledge_collection():
    """
    Returns the ChromaDB collection used for org knowledge / RAG.
    Creates it if it doesn't exist yet.
    """
    return _chroma_client.get_or_create_collection(
        name=settings.chroma_collection_name,
        embedding_function=_embedding_function,
    )
