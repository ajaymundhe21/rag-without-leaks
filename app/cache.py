"""Saved answers in Redis. The key holds the company, the question and the person's groups,
so an answer built for the board is never handed to an employee."""
import hashlib, json
import redis
from .config import REDIS_URL, CACHE_SECONDS

_r = None


def r():
    global _r
    if _r is None:
        _r = redis.Redis.from_url(REDIS_URL)
    return _r


def key(tenant_id: int, question: str, groups: list[str]) -> str:
    q = hashlib.sha1(" ".join(question.lower().split()).encode()).hexdigest()
    return f"ans:{tenant_id}:{q}:{','.join(sorted(groups))}"


def get(k: str):
    v = r().get(k)
    return json.loads(v) if v else None


def put(k: str, tenant_id: int, value: dict) -> None:
    pipe = r().pipeline()
    pipe.set(k, json.dumps(value), ex=CACHE_SECONDS)
    for s in value["sources"]:  # remember which documents this answer used
        dep = f"dep:{tenant_id}:{s['doc_id']}"
        pipe.sadd(dep, k)
        pipe.expire(dep, CACHE_SECONDS)
    pipe.execute()


def forget_document(tenant_id: int, doc_id: str) -> None:
    """A page or its permission changed: clear every saved answer that used it."""
    dep = f"dep:{tenant_id}:{doc_id}"
    keys = r().smembers(dep)
    if keys:
        r().delete(*keys)
    r().delete(dep)
