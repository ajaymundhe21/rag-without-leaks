# Benchmarks behind the video

Run against Postgres 16 + pgvector 0.8.0 on port 5433 in a 2-CPU, 7 GB machine. Scripts connect as `postgres` on localhost:5433; change the connection string for yours.

| script | what it measures | result |
|---|---|---|
| `m1_chunks.py` | word search vs meaning; four ways to cut the handbook (21 questions) | `results/m1.json` |
| `m2_pg.py` | post-filter vs pre-filter, error codes and hybrid merge, transaction gap, same write twice, tenant partitions | `results/m2.json` |
| `m4_cache_eval.py` | Redis hit, cache key leak, not-found scores, leak test, model switch | `results/m4.json` |
| `m6_real_scale.py` | 1,000,000 real embeddings: brute force, HNSW speed and recall, size, strict filter | `results/m6.json` |
| `m7_acl_update.py` | permission update on 10,000 of 200,000 chunks, with and without an index on readers, fillfactor 100 vs 70 | `results/m7_acl_update_rerun.json` |
| `m8_small_group.py` | small group (1 in 200): HNSW, iterative scan, exact search over a small index | `results/m8_small_group_rerun.json` |

`results/m5.json`, `m7.json` and `m8.json` are the first runs, made with one-off commands. The rerun files come from the scripts above. Where they differ, the rerun is the one to trust: the first run reported 45% recall for iterative scan, and the script measures 96 to 100%.

`data.py` holds the demo text. It is made up for the video.
