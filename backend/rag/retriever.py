import logging
from typing import List, Dict, Any

from config import TOP_K
from rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def retrieve(self, query: str, k: int = TOP_K) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant chunks for the given query."""
        results = self.vector_store.similarity_search(query, k=k)
        logger.info(f"Retrieved {len(results)} chunks for query: {query[:50]}...")
        return results
