from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


@dataclass
class VectorRecord:
    record_id: str
    text: str
    metadata: dict[str, Any]


class LocalVectorStore:
    def __init__(self, store_dir: Path, embedder: Any) -> None:
        self.store_dir = store_dir
        self.embedder = embedder
        self.records: list[VectorRecord] = []
        self.embeddings = np.empty((0, 0), dtype=np.float32)

    @property
    def embeddings_path(self) -> Path:
        return self.store_dir / "embeddings.npy"

    @property
    def records_path(self) -> Path:
        return self.store_dir / "records.json"

    def load(self) -> None:
        if not self.embeddings_path.exists() or not self.records_path.exists():
            return
        self.embeddings = np.load(self.embeddings_path)
        with self.records_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        self.records = [
            VectorRecord(
                record_id=item["record_id"],
                text=item["text"],
                metadata=item["metadata"],
            )
            for item in payload
        ]

    def save(self) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.embeddings_path, self.embeddings)
        payload = [
            {"record_id": record.record_id, "text": record.text, "metadata": record.metadata}
            for record in self.records
        ]
        with self.records_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def add_records(self, records: Iterable[VectorRecord]) -> None:
        new_records = list(records)
        if not new_records:
            return
        texts = [record.text for record in new_records]
        vectors = self.embedder.encode(texts, normalize_embeddings=True)
        vectors = np.asarray(vectors, dtype=np.float32)
        if self.embeddings.size == 0:
            self.embeddings = vectors
        else:
            self.embeddings = np.vstack([self.embeddings, vectors])
        self.records.extend(new_records)

    def search(self, query: str, top_k: int = 5) -> list[tuple[VectorRecord, float]]:
        if not self.records:
            return []
        query_vector = self.embedder.encode([query], normalize_embeddings=True)
        query_vector = np.asarray(query_vector, dtype=np.float32)[0]
        scores = self.embeddings @ query_vector
        top_indices = scores.argsort()[::-1][:top_k]
        return [(self.records[index], float(scores[index])) for index in top_indices]

    def clear(self) -> None:
        self.records = []
        self.embeddings = np.empty((0, 0), dtype=np.float32)
