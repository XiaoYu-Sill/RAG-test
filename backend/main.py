import os
import json
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(__file__))

from config import UPLOAD_DIR, VECTOR_STORE_PATH
from rag.document_processor import DocumentProcessor
from rag.vector_store import VectorStore
from rag.retriever import Retriever
from rag.llm import LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------
app = FastAPI(title="RAG Q&A System", version="1.0.0")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VECTOR_STORE_PATH, exist_ok=True)

DOCUMENTS_META_FILE = os.path.join(VECTOR_STORE_PATH, "documents.json")

# Global singletons
vector_store = VectorStore()
processor = DocumentProcessor()
retriever = Retriever(vector_store)
llm_client = LLMClient()


def load_documents_meta() -> dict:
    if os.path.exists(DOCUMENTS_META_FILE):
        with open(DOCUMENTS_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_documents_meta(meta: dict) -> None:
    with open(DOCUMENTS_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


@app.on_event("startup")
async def startup_event():
    """Load vector store from disk on startup."""
    loaded = vector_store.load()
    if loaded:
        logger.info(f"Loaded vector store with {vector_store.total_chunks} chunks")
    else:
        logger.info("Starting with empty vector store")


# ---------------------------------------------------------------------------
# Frontend serving — use StaticFiles for secure path handling
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# Mount /frontend as static files directory (Starlette handles path traversal internally)
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "total_chunks": vector_store.total_chunks,
        "sources": vector_store.list_sources(),
    }


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".csv", ".xlsx", ".pptx", ".txt", ".md"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    logger.info(f"Saved uploaded file: {save_path}")

    try:
        chunks = processor.load_document(save_path)
        vector_store.add_documents(chunks)
    except Exception as e:
        os.remove(save_path)
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

    # Track metadata
    meta = load_documents_meta()
    meta[file.filename] = {
        "filename": file.filename,
        "size": len(content),
        "chunks": len(chunks),
        "uploaded_at": datetime.now().isoformat(),
        "ext": ext,
    }
    save_documents_meta(meta)

    return {
        "message": "Document uploaded and indexed successfully",
        "filename": file.filename,
        "chunks": len(chunks),
    }


# ---------------------------------------------------------------------------
# Document listing & deletion
# ---------------------------------------------------------------------------
@app.get("/documents")
async def list_documents():
    meta = load_documents_meta()
    return {"documents": list(meta.values())}


@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    meta = load_documents_meta()
    if filename not in meta:
        raise HTTPException(status_code=404, detail="Document not found")

    # Use the server-stored filename (not the raw URL param) to build the file path,
    # breaking the taint chain from user input to file operations.
    stored_filename = meta[filename]["filename"]
    # Remove from vector store
    removed_chunks = vector_store.delete_by_source(stored_filename)

    # Remove physical file using the server-controlled stored filename
    file_path = os.path.join(UPLOAD_DIR, stored_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Update metadata
    del meta[filename]
    save_documents_meta(meta)

    return {"message": f"Deleted '{stored_filename}' and {removed_chunks} chunks from vector store"}


# ---------------------------------------------------------------------------
# Chat (RAG + streaming SSE)
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    top_k: Optional[int] = 5


@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    top_k = min(max(request.top_k or 5, 1), 10)

    def event_stream():
        try:
            chunks = retriever.retrieve(request.question, k=top_k)
            for sse_line in llm_client.stream_chat(request.question, chunks):
                yield sse_line
        except Exception as e:
            logger.error(f"Chat error: {e}")
            # Expose only a generic message to the client to avoid stack-trace leakage
            yield f"data: {json.dumps({'type': 'error', 'message': '处理请求时发生错误，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
