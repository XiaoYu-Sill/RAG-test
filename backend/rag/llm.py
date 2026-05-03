import json
import logging
from typing import List, Dict, Any, Generator

from zhipuai import ZhipuAI

from config import ZHIPU_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个基于检索增强生成的高铁事故应急处置文档问答助手。
请根据以下检索到的上下文信息回答用户的问题。
在回答中，请引用相关的来源，格式为[来源X]，其中X是来源编号。
如果上下文中没有相关信息，请诚实地说明。"""


def _build_context(chunks: List[Dict[str, Any]]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk.get("source", "未知")
        page = chunk.get("page", "N/A")
        content = chunk.get("content", "")
        parts.append(f"[来源{i}] 文档：{source}，第{page}页\n{content}")
    return "\n\n".join(parts)


def _build_messages(question: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    context = _build_context(chunks)
    user_content = (
        f"上下文信息：\n{context}\n\n"
        f"用户问题：{question}\n\n"
        "请给出详细、准确的回答，并在回答末尾列出所引用的来源。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


class LLMClient:
    def __init__(self):
        self.client = ZhipuAI(api_key=ZHIPU_API_KEY)

    def stream_chat(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
    ) -> Generator[str, None, None]:
        """Yield SSE-formatted data strings."""
        if not chunks:
            # No context found
            yield _sse("chunk", {"content": "抱歉，在已上传的文档中未找到与您问题相关的内容。请先上传相关文档，或调整您的问题。"})
            yield _sse("done", {})
            return

        messages = _build_messages(question, chunks)

        # Send sources first
        sources_payload = [
            {
                "source": c.get("source", ""),
                "page": c.get("page", ""),
                "content": c.get("content", "")[:300],
                "score": round(c.get("score", 0), 4),
            }
            for c in chunks
        ]
        yield _sse("sources", {"sources": sources_payload})

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                stream=True,
                max_tokens=2048,
                temperature=0.7,
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield _sse("chunk", {"content": delta.content})
        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
            yield _sse("error", {"message": str(e)})

        yield _sse("done", {})


def _sse(event_type: str, data: dict) -> str:
    payload = {"type": event_type}
    payload.update(data)
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
