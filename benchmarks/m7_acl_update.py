"""Permission change: update readers on 10,000 chunks of a 200,000-chunk table with an HNSW index.
Compares with and without an index on readers, and table fillfactor 100 vs 70.
Uses real1m (built by m6_real_scale.py) as the source of real embeddings."""
import json, time, psycopg
c = psycopg.connect("host=localhost port=5433 user=postgres", autocommit=True); x = c.execute
x("set maintenance_work_mem = '1GB'")
res = {}
for fill in (100, 70):
    for gin in (False, True):
        name = f"fill{fill}_{'hnsw_plus_readers_index' if gin else 'hnsw_only'}"
        x("drop table if exists acl_t")
        x(f"create table acl_t (id bigint primary key, readers text[], embedding vector(256)) with (fillfactor = {fill})")
        x("insert into acl_t select id, readers, embedding from real1m where id < 200000")
        x("create index on acl_t using hnsw (embedding vector_cosine_ops)")
        if gin:
            x("create index on acl_t using gin (readers)")
        x("vacuum analyze acl_t")
        t = time.perf_counter()
        x("update acl_t set readers = array['finance'] where id < 10000")
        ms = (time.perf_counter() - t) * 1000
        hot = x("select n_tup_upd, n_tup_hot_upd from pg_stat_user_tables where relname = 'acl_t'").fetchone()
        res[name] = {"seconds": round(ms / 1000, 1), "rows_updated": hot[0], "hot_updates": hot[1]}
        print(name, res[name], flush=True)
x("drop table if exists acl_t")
json.dump(res, open("results/m7_acl_update_rerun.json", "w"), indent=1)
