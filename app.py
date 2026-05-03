from __future__ import annotations

import json
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag import RAGPipeline
from rag.ingestion import SUPPORTED_EXTENSIONS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

pipeline = RAGPipeline(DATA_DIR)


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pipeline.initialize()
    yield


app = FastAPI(title="RAG Doc QA", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=10)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
def upload_file(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    target_path = _unique_upload_path(Path(file.filename).name)
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    count = pipeline.index_file(target_path)
    return {"filename": target_path.name, "indexed_chunks": count}


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    sources = pipeline.search(request.question, request.top_k)
    prompt_sources = pipeline.serialize_sources(sources)

    def event_stream():
        yield _sse_event("sources", prompt_sources)
        for token in pipeline.stream_answer(request.question, sources):
            yield _sse_event("token", json.dumps({"token": token}, ensure_ascii=False))
        yield _sse_event("done", json.dumps({"status": "ok"}, ensure_ascii=False))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/files/{file_name}")
def serve_file(file_name: str) -> FileResponse:
    file_path = pipeline.file_registry.get(file_name)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)


def _unique_upload_path(filename: str) -> Path:
    safe_name = Path(filename).name
    target = UPLOAD_DIR / safe_name
    if not target.exists():
        return target
    timestamp = int(time.time())
    return UPLOAD_DIR / f"{target.stem}-{timestamp}{target.suffix}"


def _sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
