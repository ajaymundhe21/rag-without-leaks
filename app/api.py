"""The chat box's backend.

    uvicorn app.api:app --reload
    curl -X POST localhost:8000/ask -H 'X-User: emp-1' -H 'Content-Type: application/json' \
         -d '{"question": "How many weeks of maternity leave do I get?"}'
"""
import time
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from . import answer, cache, identity
from .config import ANSWER_CHUNKS
from .db import tenant_tx
from .search import search

app = FastAPI(title="Search over company documents")


class Ask(BaseModel):
    question: str


def _who(x_user: str):
    try:
        return identity.login(x_user)
    except KeyError:
        raise HTTPException(401, "unknown user")


def _audit(tenant_id: int, user: str, groups: list[str], chunks: list[dict]) -> None:
    with tenant_tx(tenant_id) as conn:
        conn.execute("INSERT INTO audit_log (tenant_id, user_id, groups, chunk_ids) VALUES (%s, %s, %s, %s)",
                     (tenant_id, user, groups, [c["id"] for c in chunks]))


@app.post("/ask")
def ask(body: Ask, x_user: str = Header(...)):
    t0 = time.perf_counter()
    tenant_id, groups = _who(x_user)
    k = cache.key(tenant_id, body.question, groups)
    if (hit := cache.get(k)) is not None:
        return {**hit, "cached": True, "took_ms": round((time.perf_counter() - t0) * 1000, 2)}
    chunks = search(tenant_id, groups, body.question)[:ANSWER_CHUNKS]
    if not chunks:
        return {"answer": "I could not find this in the documents you can open.", "sources": [], "cached": False}
    _audit(tenant_id, x_user, groups, chunks)
    result = {"answer": answer.write(body.question, chunks), "sources": answer.sources(chunks)}
    cache.put(k, tenant_id, result)
    return {**result, "cached": False, "took_ms": round((time.perf_counter() - t0) * 1000, 2)}


@app.post("/ask/stream")
def ask_stream(body: Ask, x_user: str = Header(...)):
    tenant_id, groups = _who(x_user)
    chunks = search(tenant_id, groups, body.question)[:ANSWER_CHUNKS]
    if not chunks:
        return StreamingResponse(iter(["data: I could not find this in the documents you can open.\n\n"]),
                                 media_type="text/event-stream")
    _audit(tenant_id, x_user, groups, chunks)
    return StreamingResponse((f"data: {piece}\n\n" for piece in answer.stream(body.question, chunks)),
                             media_type="text/event-stream")


@app.get("/health")
def health():
    return {"ok": True}
