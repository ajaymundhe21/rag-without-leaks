"""Lines 1 to 4: read a file, cut it, embed it, and write its rows.

    python -m app.ingest data/docs --tenant 1
"""
import argparse, json
from pathlib import Path
from .db import tenant_tx
from .embed import embed
from .extract import read_file
from . import cache


def folder_readers(path: Path, root: Path) -> list[str]:
    """Most pages have no permission of their own. Walk up to the nearest folder that has one."""
    d = path.parent
    while True:
        acl = d / "_acl.json"
        if acl.exists():
            return json.loads(acl.read_text())["readers"]
        if d == root or d == d.parent:
            raise ValueError(f"no _acl.json above {path}; refusing to index a file with unknown readers")
        d = d.parent


def write_document(tenant_id: int, doc_id: str, readers: list[str], pieces: list[tuple[int, str]]) -> int:
    """Replace every chunk of one document. Safe to run twice, and safe if it dies halfway."""
    vecs = embed([t for _, t in pieces]) if pieces else []
    with tenant_tx(tenant_id) as conn:
        # Two writers on the same document wait for each other instead of both inserting.
        conn.execute("SELECT pg_advisory_xact_lock(%s, hashtext(%s))", (tenant_id, doc_id))
        conn.execute("DELETE FROM chunks WHERE tenant_id = %s AND doc_id = %s", (tenant_id, doc_id))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (tenant_id, readers, doc_id, page, text, embedding) VALUES (%s, %s, %s, %s, %s, %s)",
                [(tenant_id, readers, doc_id, page, text, v) for (page, text), v in zip(pieces, vecs)])
    # Delete and insert commit together. Then every saved answer that used this document is cleared.
    cache.forget_document(tenant_id, doc_id)
    return len(pieces)


def refresh_group_sizes(tenant_id: int) -> None:
    with tenant_tx(tenant_id) as conn:
        conn.execute("DELETE FROM group_sizes WHERE tenant_id = %s", (tenant_id,))
        conn.execute("""INSERT INTO group_sizes (tenant_id, grp, n)
                        SELECT %s, g, count(*) FROM chunks, unnest(readers) g WHERE tenant_id = %s GROUP BY g""",
                     (tenant_id, tenant_id))


def ingest_folder(root: Path, tenant_id: int) -> int:
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".pdf"):
            doc_id = str(path.relative_to(root).with_suffix(""))
            total += write_document(tenant_id, doc_id, folder_readers(path, root), read_file(path))
    refresh_group_sizes(tenant_id)
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--tenant", type=int, required=True)
    a = ap.parse_args()
    print(f"tenant {a.tenant}: {ingest_folder(a.folder, a.tenant)} chunks written")
