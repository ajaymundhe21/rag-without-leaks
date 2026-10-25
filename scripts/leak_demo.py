"""The leak from the start of the video, and the fix, on the same data.

    python -m scripts.leak_demo
"""
from app.db import tenant_tx
from app.embed import embed_one
from app.identity import login

Q = "How many weeks of maternity leave do I get?"
tenant, groups = login("emp-1")
v = embed_one(Q)

with tenant_tx(tenant) as conn:
    print(f'"{Q}"  asked by emp-1, groups {groups}\n')

    print("1. First version: closest chunks, nobody checks who is asking")
    rows = conn.execute("SELECT doc_id, page, readers FROM chunks ORDER BY embedding <=> %s LIMIT 10", (v,)).fetchall()
    for doc, page, readers in rows[:3]:
        print(f"   {doc} p{page}  readers={readers}")

    kept = [r for r in rows if set(r[2]) & set(groups)]
    print(f"\n2. Post-filter: take the top 10, then remove what emp-1 cannot open")
    print(f"   {10 - len(kept)} of 10 removed, {len(kept)} left. The board page was already in memory.")

    print("\n3. Pre-filter: the person's groups go inside the query")
    rows = conn.execute("""SELECT doc_id, page FROM chunks
                           WHERE tenant_id = %s AND readers && %s
                           ORDER BY embedding <=> %s LIMIT 5""", (tenant, groups, v)).fetchall()
    print("   " + ", ".join(f"{d} p{p}" for d, p in rows))
    restricted = sum(1 for d, _ in rows if not d.startswith(("hr/", "it-kb/")))
    print(f"   restricted rows: {restricted}")
