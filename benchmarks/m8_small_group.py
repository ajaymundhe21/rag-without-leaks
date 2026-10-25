"""Small group on 1,000,000 chunks (run m6_real_scale.py first; it builds real1m).
One row in 200 is readable by 'legal'. Compares HNSW, HNSW + iterative scan, and an exact search
over a small index on only the legal rows."""
import json, time, numpy as np, psycopg
from pgvector.psycopg import register_vector
from wordllama import WordLlama
wl = WordLlama.load(disable_download=True)
c = psycopg.connect("host=localhost port=5433 user=postgres", autocommit=True); register_vector(c); x = c.execute
x("drop index if exists real1m_legal")
x("analyze real1m"); x("set max_parallel_workers_per_gather = 0")
Qs = ["How many weeks of maternity leave do I get?","How many days can I work remotely?","When does my salary come?","What do I do if I lose my laptop?",
      "Is there a bus from the metro station?","What does error E4017 mean?","When do backups run?","How fast must support reply?",
      "What is the API rate limit?","When does the contract renew?","Is security training mandatory?","When is the bonus paid?",
      "How much can I spend on courses?","Can I accept a gift from a vendor?","What is the notice period?","Who approves my leave?",
      "Where is the new office opening?","How are refunds approved?","When do on-call engineers hand over?","What is the sales target?"]
qv = wl.embed(Qs); qv = (qv / np.linalg.norm(qv, axis=1, keepdims=True)).astype(np.float32)
SQL = "select id from real1m where readers && array['legal'] order by embedding <=> %s limit 50"
def run(setup):
    ts, out = [], []
    for q in qv:
        with c.transaction():
            for s in setup: x(s)
            t = time.perf_counter(); out.append([i for (i,) in x(SQL, (q,)).fetchall()]); ts.append((time.perf_counter()-t)*1000)
    return out, round(float(np.median(ts)), 1)
# HNSW runs first, while no small index exists, so the planner uses the vector index.
plain, plain_ms = run(["set local hnsw.ef_search = 40"])
itr, itr_ms = run(["set local hnsw.ef_search = 40", "set local hnsw.iterative_scan = relaxed_order"])
# Then a small index on only the legal rows, and an exact search over them.
x("create index real1m_legal on real1m (id) where readers && array['legal']"); x("analyze real1m")
exact, exact_ms = run(["set local enable_indexscan = off"])
x("set enable_indexscan = off")
plan = [r[0] for r in x("explain " + SQL, (qv[0],)).fetchall()]
x("reset enable_indexscan")
def recall(a): return round(float(np.mean([len(set(r) & set(e)) / 50 for r, e in zip(a, exact)])), 3)
res = {"exact_via_small_index_ms": exact_ms, "exact_rows": float(np.mean([len(r) for r in exact])),
       "hnsw_rows": float(np.mean([len(r) for r in plain])), "hnsw_ms": plain_ms,
       "iterative_rows": float(np.mean([len(r) for r in itr])), "iterative_ms": itr_ms, "iterative_recall_vs_exact": recall(itr), "exact_plan": plan}
json.dump(res, open("results/m8_small_group_rerun.json", "w"), indent=1); print(json.dumps(res, indent=1))
