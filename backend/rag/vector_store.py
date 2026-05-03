import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional

from config import ZHIPU_API_KEY, EMBEDDING_MODEL, VECTOR_STORE_PATH

logger = logging.getLogger(__name__)

INDEX_FILE = os.path.join(VECTOR_STORE_PATH, "faiss.index")
METADATA_FILE = os.path.join(VECTOR_STORE_PATH, "metadata.json")


class VectorStore:
    def __init__(self):
        self._index = None
        self._metadata: List[Dict[str, Any]] = []
        self._client = None
        self._dim: Optional[int] = None
        os.makedirs(VECTOR_STORE_PATH, exist_ok=True)

    def _get_client(self):
        if self._client is None:
            from zhipuai import ZhipuAI
            self._client = ZhipuAI(api_key=ZHIPU_API_KEY)
        return self._client

    def _embed(self, texts: List[str]) -> np.ndarray:
        """Get embeddings from ZhipuAI for a list of texts."""
        client = self._get_client()
        embeddings = []
        # ZhipuAI embedding API supports batch or single; call per text for reliability
        for text in texts:
            text = text[:2048]  # truncate to safe length
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
            embeddings.append(resp.data[0].embedding)
        return np.array(embeddings, dtype=np.float32)

    def _get_index(self, dim: int):
        """Lazily create or return the FAISS index."""
        import faiss
        if self._index is None:
            self._index = faiss.IndexFlatIP(dim)  # inner product (cosine after normalization)
        return self._index

    def _normalize(self, vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return vecs / norms

    def add_documents(self, chunks: List[Dict[str, Any]]) -> None:
        """Add document chunks to the vector store."""
        if not chunks:
            return
        texts = [c["text"] for c in chunks]
        logger.info(f"Embedding {len(texts)} chunks...")
        vecs = self._embed(texts)
        vecs = self._normalize(vecs)
        dim = vecs.shape[1]
        index = self._get_index(dim)
        self._dim = dim
        start_id = len(self._metadata)
        index.add(vecs)
        for i, chunk in enumerate(chunks):
            self._metadata.append({
                "id": start_id + i,
                "text": chunk["text"],
                "source": chunk["metadata"]["source"],
                "page": chunk["metadata"]["page"],
                "chunk_id": chunk["metadata"]["chunk_id"],
            })
        logger.info(f"Added {len(chunks)} chunks. Total: {len(self._metadata)}")
        self.save()

    def similarity_search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for top-k similar chunks."""
        if self._index is None or self._index.ntotal == 0:
            return []
        q_vec = self._embed([query])
        q_vec = self._normalize(q_vec)
        k = min(k, self._index.ntotal)
        scores, indices = self._index.search(q_vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            results.append({
                "content": meta["text"],
                "source": meta["source"],
                "page": meta["page"],
                "chunk_id": meta["chunk_id"],
                "score": float(score),
            })
        return results

    def save(self) -> None:
        """Persist the FAISS index and metadata to disk."""
        import faiss
        if self._index is not None and self._index.ntotal > 0:
            faiss.write_index(self._index, INDEX_FILE)
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"dim": self._dim, "metadata": self._metadata}, f, ensure_ascii=False, indent=2)
            logger.info(f"Vector store saved to {VECTOR_STORE_PATH}")

    def load(self) -> bool:
        """Load persisted vector store from disk. Returns True if loaded."""
        import faiss
        if os.path.exists(INDEX_FILE) and os.path.exists(METADATA_FILE):
            try:
                self._index = faiss.read_index(INDEX_FILE)
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._dim = data.get("dim")
                self._metadata = data.get("metadata", [])
                logger.info(f"Vector store loaded: {len(self._metadata)} chunks")
                return True
            except Exception as e:
                logger.error(f"Failed to load vector store: {e}")
        return False

    def delete_by_source(self, filename: str) -> int:
        """Remove all chunks belonging to a given source file."""
        # FAISS IndexFlatIP doesn't support deletion natively; rebuild index
        import faiss
        original_count = len(self._metadata)
        self._metadata = [m for m in self._metadata if m["source"] != filename]
        removed = original_count - len(self._metadata)
        if removed == 0:
            return 0
        # Rebuild index
        if self._metadata and self._dim:
            texts = [m["text"] for m in self._metadata]
            vecs = self._embed(texts)
            vecs = self._normalize(vecs)
            self._index = faiss.IndexFlatIP(self._dim)
            self._index.add(vecs)
            # Re-assign sequential IDs
            for i, m in enumerate(self._metadata):
                m["id"] = i
        else:
            self._index = None
            self._dim = None
        self.save()
        logger.info(f"Deleted {removed} chunks for source '{filename}'")
        return removed

    def list_sources(self) -> List[str]:
        """Return list of unique source filenames in the store."""
        return list({m["source"] for m in self._metadata})

    @property
    def total_chunks(self) -> int:
        return len(self._metadata)
