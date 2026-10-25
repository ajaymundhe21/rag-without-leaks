"""Measure 6: 1M chunks with REAL embeddings of varied company-like text, HNSW recall/latency,
strict filter, and the ACL-update cost with and without the readers GIN index / fillfactor."""
import json, time, random, numpy as np, psycopg
from pgvector.psycopg import register_vector
from wordllama import WordLlama
from data import HANDBOOK, ERROR_TOPICS
wl = WordLlama.load(disable_download=True)
random.seed(3)
depts = ["HR","Finance","Legal","IT","Sales","Marketing","Engineering","Facilities","Security","Support","Product","Procurement"]
kinds = ["policy","meeting notes","runbook","FAQ","design doc","report","announcement","checklist","contract","guide"]
topics = [b for _,_,b in HANDBOOK] + [f for _,f in ERROR_TOPICS] + [
 "The quarterly sales target for the north region is up by ten percent.", "Vendor invoices must be approved before the fifth of the month.",
 "The deployment pipeline runs tests on every merge to main.", "Customer refunds above five thousand need a second approval.",
 "The new office in Hyderabad opens in March.", "Database backups run every night at two.", "The marketing budget moves to digital ads.",
 "On-call engineers hand over at nine every Monday.", "The contract renews automatically unless cancelled sixty days before.",
 "Security training is mandatory for all new joiners.", "The API rate limit is one hundred requests per second per key.",
 "Support tickets must get a first reply within four hours.", "The product roadmap adds offline mode next quarter."]
words = "please note that the team will review update this from next week all staff should check with your manager before".split()
def make(i):
    t = random.choice(topics); s = t.split()
    for _ in range(random.randint(0, 3)):
        s.insert(random.randrange(len(s)+1), random.choice(words))
    return f"{random.choice(depts)} {random.choice(kinds)} {i}: " + " ".join(s)
N = 1_000_000
c = psycopg.connect("host=localhost port=5433 user=postgres", autocommit=True); register_vector(c); x = c.execute
x("drop table if exists big"); x("drop table if exists real1m")
x("create table real1m (id bigint primary key, readers text[], embedding vector(256))")
out = {}; t0 = time.time()
with c.cursor() as cur:
    with cur.copy("copy real1m (id, readers, embedding) from stdin with (format binary)") as cp:
        cp.set_types(["int8", "text[]", "vector"])
        B = 20000
        for start in range(0, N, B):
            texts = [make(i) for i in range(start, start+B)]
            E = wl.embed(texts); E = (E / np.linalg.norm(E, axis=1, keepdims=True)).astype(np.float32)
            for j, e in enumerate(E):
                i = start + j
                cp.write_row((i, ["legal"] if i % 200 == 0 else ["all-staff"], e))
out["load_and_embed_s"] = round(time.time()-t0, 1)
x("analyze real1m"); x("set max_parallel_workers_per_gather = 0")
Qs = ["How many weeks of maternity leave do I get?","How many days can I work remotely?","When does my salary come?","What do I do if I lose my laptop?",
      "Is there a bus from the metro station?","What does error E4017 mean?","When do backups run?","How fast must support reply?",
      "What is the API rate limit?","When does the contract renew?","Is security training mandatory?","When is the bonus paid?",
      "How much can I spend on courses?","Can I accept a gift from a vendor?","What is the notice period?","Who approves my leave?",
      "Where is the new office opening?","How are refunds approved?","When do on-call engineers hand over?","What is the sales target?"]
qv = wl.embed(Qs); qv = (qv / np.linalg.norm(qv, axis=1, keepdims=True)).astype(np.float32)
def med(sql, extra=()):
    ts=[]; rows=[]
    for q in qv:
        t=time.perf_counter(); r=x(sql, (q,)+extra).fetchall(); ts.append((time.perf_counter()-t)*1000); rows.append(r)
    return round(float(np.median(ts)),1), rows
for n in (250_000, 500_000, 1_000_000):
    out[f"brute_ms_{n}"], _ = med(f"select id from real1m where id < {n} order by embedding <=> %s limit 50")
_, ex = med("select id from real1m order by embedding <=> %s limit 50"); exact = [set(i for (i,) in r) for r in ex]
x("set maintenance_work_mem='2GB'"); t0=time.time()
x("create index real1m_hnsw on real1m using hnsw (embedding vector_cosine_ops)"); out["hnsw_build_s"] = round(time.time()-t0,1)
out["table_mb"] = x("select pg_relation_size('real1m')/1048576").fetchone()[0]; out["index_mb"] = x("select pg_relation_size('real1m_hnsw')/1048576").fetchone()[0]
for ef in (40, 100, 200):
    x(f"set hnsw.ef_search={ef}"); ms, rows = med("select id from real1m order by embedding <=> %s limit 50")
    out[f"hnsw_ms_ef{ef}"] = ms; out[f"hnsw_recall_ef{ef}"] = round(float(np.mean([len(set(i for (i,) in r) & e)/50 for r,e in zip(rows, exact)])),3)
x("set hnsw.ef_search=40")
for mode in ("off","relaxed_order"):
    x(f"set hnsw.iterative_scan={mode}"); ms, rows = med("select id from real1m where readers && array['legal'] order by embedding <=> %s limit 50")
    out[f"strict_rows_{mode}"] = float(np.mean([len(r) for r in rows])); out[f"strict_ms_{mode}"] = ms
x("set hnsw.iterative_scan=off")
json.dump(out, open("m6.json","w"), indent=1); print(json.dumps(out, indent=1), flush=True)
