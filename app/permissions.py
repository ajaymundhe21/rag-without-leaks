"""Someone changed who can open a folder. Update only the readers column; do not cut or embed again.

    python -m app.permissions --tenant 1 --folder board --readers board,exec
"""
import argparse
from .db import tenant_tx
from .ingest import refresh_group_sizes
from . import cache


def set_folder_readers(tenant_id: int, folder: str, readers: list[str]) -> int:
    with tenant_tx(tenant_id) as conn:
        docs = [r[0] for r in conn.execute(
            "UPDATE chunks SET readers = %s, updated_at = now() WHERE tenant_id = %s AND doc_id LIKE %s RETURNING doc_id",
            (readers, tenant_id, folder.rstrip("/") + "/%")).fetchall()]
    for d in set(docs):
        cache.forget_document(tenant_id, d)  # someone who just lost access must not get the old answer
    refresh_group_sizes(tenant_id)
    return len(docs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", type=int, required=True)
    ap.add_argument("--folder", required=True)
    ap.add_argument("--readers", required=True)
    a = ap.parse_args()
    print(f"{set_folder_readers(a.tenant, a.folder, a.readers.split(','))} chunks updated")
