"""Line 6: find the closest chunks this person is allowed to open.

The permission check sits inside the query (readers && groups), so a chunk the person
cannot open never leaves the database. Searching first and removing later is too late.
"""
from .config import TOP_K, EF_SEARCH, SMALL_GROUP_ROWS
from .db import tenant_tx
from .embed import embed_one

WORD_SQL = """
SELECT id, doc_id, page, text, readers
FROM chunks, plainto_tsquery('english', %(q)s) query
WHERE tenant_id = %(t)s AND readers && %(g)s AND tsv @@ query
ORDER BY ts_rank(tsv, query) DESC
LIMIT %(k)s"""

MEANING_SQL = """
SELECT id, doc_id, page, text, readers, 1 - (embedding <=> %(v)s) AS score
FROM chunks
WHERE tenant_id = %(t)s AND readers && %(g)s
ORDER BY embedding <=> %(v)s
LIMIT %(k)s"""


def rrf(*lists, k=60):
    """Reciprocal rank fusion: add 1 / (60 + position) from each list. Only positions matter."""
    score, row = {}, {}
    for lst in lists:
        for pos, r in enumerate(lst, 1):
            score[r[0]] = score.get(r[0], 0) + 1 / (k + pos)
            row.setdefault(r[0], r)
    return [row[i] for i in sorted(score, key=lambda i: -score[i])]


def search(tenant_id: int, groups: list[str], question: str, k: int = TOP_K) -> list[dict]:
    v = embed_one(question)
    p = {"q": question, "v": v, "t": tenant_id, "g": groups, "k": k}
    with tenant_tx(tenant_id) as conn:
        words = conn.execute(WORD_SQL, p).fetchall()
        allowed = conn.execute("SELECT coalesce(sum(n), 0) FROM group_sizes WHERE tenant_id = %s AND grp = ANY(%s)",
                               (tenant_id, groups)).fetchone()[0]
        if allowed < SMALL_GROUP_ROWS:
            # Small group: the approximate index looks at a few nearby chunks, the filter drops most of them,
            # and too few rows come back. Reading this group's rows in full is exact and cheap.
            conn.execute("SET LOCAL enable_indexscan = off")
        else:
            conn.execute(f"SET LOCAL hnsw.ef_search = {int(EF_SEARCH)}")
        meaning = conn.execute(MEANING_SQL, p).fetchall()
    return _rows(rrf(meaning, words), {r[0]: r[5] for r in meaning})


def _rows(rows, best):
    return [{"id": r[0], "doc_id": r[1], "page": r[2], "text": r[3], "readers": list(r[4]),
             "meaning_score": round(float(best.get(r[0], 0)), 3)} for r in rows]


FIRST_VERSION_SQL = """
SELECT id, doc_id, page, text, readers, 1 - (embedding <=> %(v)s) AS score
FROM chunks
WHERE tenant_id = %(t)s
ORDER BY embedding <=> %(v)s
LIMIT %(k)s"""


def search_first_version(tenant_id: int, question: str, k: int = TOP_K) -> list[dict]:
    """Demo only: the closest chunks with no permission check. This is the leak."""
    p = {"v": embed_one(question), "t": tenant_id, "k": k}
    with tenant_tx(tenant_id) as conn:
        rows = conn.execute(FIRST_VERSION_SQL, p).fetchall()
    return _rows(rows, {r[0]: r[5] for r in rows})
