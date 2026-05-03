from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from sentence_transformers import SentenceTransformer

from rag.ingestion import SUPPORTED_EXTENSIONS, build_records, load_documents, split_documents
from rag.vector_store import LocalVectorStore, VectorRecord

DEFAULT_MODEL = "glm-4-plus"


class RAGPipeline:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.upload_dir = data_dir / "uploads"
        self.store_dir = data_dir / "vector_store"
        self.embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.vector_store = LocalVectorStore(self.store_dir, self.embedder)
        self.file_registry: dict[str, Path] = {}

    def initialize(self) -> None:
        self.vector_store.load()
        self._refresh_registry()
        if not self.vector_store.records:
            self.build_index()

    def build_index(self) -> None:
        self.vector_store.records = []
        self.vector_store.embeddings = self.vector_store.embeddings[:0]
        for file_path in self._scan_files():
            self.index_file(file_path)
        self.vector_store.save()

    def index_file(self, file_path: Path) -> int:
        documents = load_documents(file_path)
        if not documents:
            return 0
        chunks = split_documents(documents)
        records = []
        for record_id, chunk in build_records(chunks):
            records.append(VectorRecord(record_id=record_id, text=chunk.page_content, metadata=chunk.metadata))
        self.vector_store.add_records(records)
        self.vector_store.save()
        self._refresh_registry()
        return len(records)

    def search(self, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        results = self.vector_store.search(question, top_k=top_k)
        sources: list[dict[str, Any]] = []
        for index, (record, score) in enumerate(results, start=1):
            metadata = dict(record.metadata)
            source_name = metadata.get("source_name", "unknown")
            source_path = self.file_registry.get(source_name, Path(metadata.get("source_path", "")))
            link = self._build_link(source_path, metadata)
            sources.append(
                {
                    "id": index,
                    "text": record.text,
                    "score": score,
                    "metadata": metadata,
                    "link": link,
                    "preview": self._build_preview(record.text),
                }
            )
        return sources

    def build_prompt(self, question: str, sources: Iterable[dict[str, Any]]) -> str:
        context_blocks = []
        for source in sources:
            metadata = source["metadata"]
            label = self._format_source_label(metadata)
            context_blocks.append(f"[{source['id']}] {label}\n{source['text']}")
        context = "\n\n".join(context_blocks)
        return (
            "你是一名高铁事故应急处置文档问答助手。请仅基于提供的上下文回答问题，"
            "不要编造。回答时为每条关键结论标注来源编号，如[[1]]。"
            "如果无法从上下文得到答案，请说明无法找到。\n\n"
            f"问题：{question}\n\n"
            f"上下文：\n{context}"
        )

    def stream_answer(self, question: str, sources: list[dict[str, Any]]) -> Iterable[str]:
        api_key = os.getenv("ZHIPUAI_API_KEY")
        if not api_key:
            fallback = self._fallback_answer(question, sources)
            for token in self._stream_text(fallback):
                yield token
            return

        try:
            from zhipuai import ZhipuAI
        except ImportError:
            fallback = self._fallback_answer(question, sources)
            for token in self._stream_text(fallback):
                yield token
            return

        prompt = self.build_prompt(question, sources)
        client = ZhipuAI(api_key=api_key)
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in response:
            choice = chunk.choices[0]
            delta = getattr(choice, "delta", None)
            content = getattr(delta, "content", None) if delta else None
            if content:
                yield content

    def _fallback_answer(self, question: str, sources: list[dict[str, Any]]) -> str:
        lines = [
            "未检测到 ZHIPUAI_API_KEY，以下为基于检索上下文的摘要提示。",
            f"问题：{question}",
            "可参考的相关文本：",
        ]
        for source in sources:
            label = self._format_source_label(source["metadata"])
            lines.append(f"- [[{source['id']}]] {label}：{source['text'][:200]}")
        return "\n".join(lines)

    def _stream_text(self, text: str) -> Iterable[str]:
        for token in text.split():
            yield token + " "
            time.sleep(0.01)

    def _scan_files(self) -> list[Path]:
        files: list[Path] = []
        for directory in [self.data_dir, self.upload_dir]:
            if not directory.exists():
                continue
            for file_path in directory.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(file_path)
        return files

    def _refresh_registry(self) -> None:
        registry: dict[str, Path] = {}
        for file_path in self._scan_files():
            registry[file_path.name] = file_path
        self.file_registry = registry

    def _build_link(self, file_path: Path, metadata: dict[str, Any]) -> str:
        if not file_path or not file_path.exists():
            return ""
        safe_name = quote(file_path.name)
        if metadata.get("source_type") == "pdf" and metadata.get("page"):
            return f"/files/{safe_name}#page={metadata['page']}"
        return f"/files/{safe_name}"

    def _format_source_label(self, metadata: dict[str, Any]) -> str:
        source = metadata.get("source_name", "未知文档")
        location = metadata.get("location", "未知位置")
        return f"{source} · {location}"

    def _build_preview(self, text: str) -> str:
        snippet = text.replace("\n", " ").strip()
        return snippet[:240] + ("..." if len(snippet) > 240 else "")

    def serialize_sources(self, sources: list[dict[str, Any]]) -> str:
        return json.dumps(sources, ensure_ascii=False)
