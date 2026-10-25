"""The chat box's backend.

    uvicorn app.api:app --reload
    curl -X POST localhost:8000/ask -H 'X-User: emp-1' -H 'Content-Type: application/json' \
         -d '{"question": "How many weeks of maternity leave do I get?"}'
"""
import time
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from . import answer, cache, identity
from .config import ANSWER_CHUNKS, DEMO_FIRST_VERSION
from .db import tenant_tx
from .search import search, search_first_version

app = FastAPI(title="Search over company documents")


class Ask(BaseModel):
    question: str
    first_version: bool = False   # demo: no permission filter


def _who(x_user: str):
    try:
        return identity.login(x_user)
    except KeyError:
        raise HTTPException(401, "unknown user")


def _audit(tenant_id: int, user: str, groups: list[str], chunks: list[dict]) -> None:
    with tenant_tx(tenant_id) as conn:
        conn.execute("INSERT INTO audit_log (tenant_id, user_id, groups, chunk_ids) VALUES (%s, %s, %s, %s)",
                     (tenant_id, user, groups, [c["id"] for c in chunks]))


def _mark(sources: list[dict], groups: list[str]) -> list[dict]:
    """Tell the page which sources this person may open, so it can show a lock."""
    return [{**s, "can_open": bool(set(s["readers"]) & set(groups))} for s in sources]


@app.post("/ask")
def ask(body: Ask, x_user: str = Header(...)):
    t0 = time.perf_counter()
    tenant_id, groups = _who(x_user)
    if body.first_version:
        if not DEMO_FIRST_VERSION:
            raise HTTPException(403, "first version demo is turned off")
        chunks = search_first_version(tenant_id, body.question)[:ANSWER_CHUNKS]
        return {"answer": answer.write(body.question, chunks), "sources": _mark(answer.sources(chunks), groups), "cached": False,
                "first_version": True, "took_ms": round((time.perf_counter() - t0) * 1000, 2)}
    k = cache.key(tenant_id, body.question, groups)
    if (hit := cache.get(k)) is not None:
        return {**hit, "cached": True, "took_ms": round((time.perf_counter() - t0) * 1000, 2)}
    chunks = search(tenant_id, groups, body.question)[:ANSWER_CHUNKS]
    if not chunks:
        return {"answer": "I could not find this in the documents you can open.", "sources": [], "cached": False}
    _audit(tenant_id, x_user, groups, chunks)
    result = {"answer": answer.write(body.question, chunks), "sources": _mark(answer.sources(chunks), groups)}
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


@app.get("/doc")
def doc(doc_id: str, page: int, x_user: str = Header(...)):
    """The document viewer checks permission too. A link must not open a page the person cannot read."""
    tenant_id, groups = _who(x_user)
    with tenant_tx(tenant_id) as conn:
        row = conn.execute("SELECT text, readers FROM chunks WHERE tenant_id = %s AND doc_id = %s AND page = %s LIMIT 1",
                           (tenant_id, doc_id, page)).fetchone()
    if row is None:
        raise HTTPException(404, "no such page")
    if not set(row[1]) & set(groups):
        raise HTTPException(403, "You do not have access to this page.")
    title, _, rest = row[0].partition(" · ")
    heading, _, body = rest.partition(". ")
    return {"doc_id": doc_id, "page": page, "title": title, "heading": heading, "text": body, "readers": row[1]}


@app.get("/users")
def users():
    data = identity._data()
    return [{"id": u, "tenant": v["tenant"], "groups": v["groups"]} for u, v in data["users"].items()]


@app.get("/config")
def config():
    return {"first_version_demo": DEMO_FIRST_VERSION}


@app.get("/")
def page():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    return {"ok": True}
