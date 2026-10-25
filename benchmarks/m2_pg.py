"""Measure 2 (real embeddings, small table): keyword vs meaning for error codes, hybrid merge,
post-filter vs pre-filter, transaction gap, idempotent write, ACL-only update, tenant partitions."""
import json, time, random, numpy as np, psycopg
from wordllama import WordLlama
from data import HANDBOOK, BOARD_PAGE, error_pages
wl = WordLlama.load(disable_download=True)
def emb(t):
    v = wl.embed(t); return v / np.linalg.norm(v, axis=1, keepdims=True)
def vec(v): return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
c = psycopg.connect("host=localhost port=5433 user=postgres", autocommit=True)
x = c.execute
out = {}
x("drop table if exists chunks cascade")
x("""create table chunks (id bigserial, tenant_id int, doc_id text, page int, text text,
      readers text[], embedding vector(256), tsv tsvector generated always as (to_tsvector('english', text)) stored,
      primary key (tenant_id, id)) partition by list (tenant_id)""")
for t in range(1, 11): x(f"create table chunks_t{t} partition of chunks for values in ({t})")

rows = []
for p,h,b in HANDBOOK: rows.append((1, "hr-handbook", p, f"{h}. {b}", ["all-staff"]))
# restricted pages that match the parental-leave question strongly (board / exec / finance)
variants = [
 "Parental leave cost per employee for next year, board estimate.",
 "Parental leave changes for next year: 12 weeks will move to 16 weeks.",
 "Board discussion on maternity and paternity leave budget for FY27.",
 "Comparison of parental leave weeks with other companies, for the board.",
 "Finance forecast of parental leave payouts by quarter.",
 "Exec review: how many staff took parental leave last year and the cost.",
 "Draft announcement of the new parental leave policy, not yet approved.",
 "Legal review of parental leave rules for each country we operate in.",
]
groups = ["board", "exec", "finance", "legal"]
for i in range(32):
    rows.append((1, f"restricted-{i}", 1, BOARD_PAGE[1] if i == 0 else variants[i % len(variants)] + f" Note {i}.", [groups[i % 4]]))
for code, h, b in error_pages(): rows.append((1, f"it-kb-{code}", 1, f"{h}. {b}", ["all-staff"]))
# same handbook for 9 other tenants (other companies)
for t in range(2, 11):
    for p,h,b in HANDBOOK: rows.append((t, "hr-handbook", p, f"{h}. {b}", ["all-staff"]))
E = emb([r[3] for r in rows])
with c.cursor() as cur:
    cur.executemany("insert into chunks (tenant_id, doc_id, page, text, readers, embedding) values (%s,%s,%s,%s,%s,%s)",
                    [(r[0], r[1], r[2], r[3], r[4], vec(e)) for r, e in zip(rows, E)])
out["rows"] = len(rows)

Q = "How many weeks of maternity leave do I get?"
qv = vec(emb([Q])[0])
# post-filter: top 10 by meaning, then drop what the user cannot read
top10 = x("select doc_id, readers from chunks where tenant_id=1 order by embedding <=> %s limit 10", (qv,)).fetchall()
user = ["all-staff", "engineering"]
kept = [d for d, r in top10 if set(r) & set(user)]
out["postfilter_top10_restricted"] = 10 - len(kept); out["postfilter_kept"] = len(kept)
out["postfilter_top1_doc"] = top10[0][0]
# pre-filter: filter inside the query
pre = x("select doc_id, page from chunks where tenant_id=1 and readers && %s order by embedding <=> %s limit 5", (user, qv)).fetchall()
out["prefilter_top5"] = pre
out["prefilter_board_rows_returned"] = sum(1 for d,_ in pre if d.startswith("restricted"))

# error code: meaning vs keyword
eq = "E4017"
mv = x("select doc_id from chunks where tenant_id=1 order by embedding <=> %s limit 3", (vec(emb([eq])[0]),)).fetchall()
kw = x("select doc_id, ts_rank(tsv, q) from chunks, plainto_tsquery('english', %s) q where tenant_id=1 and tsv @@ q order by 2 desc limit 3", (eq,)).fetchall()
out["E4017_meaning_top3"] = [r[0] for r in mv]; out["E4017_keyword_top3"] = [r[0] for r in kw]
full_q = "what does error E4017 mean"
mv2 = x("select doc_id from chunks where tenant_id=1 order by embedding <=> %s limit 50", (vec(emb([full_q])[0]),)).fetchall()
kw2 = x("select doc_id from chunks, plainto_tsquery('english', %s) q where tenant_id=1 and tsv @@ q order by ts_rank(tsv,q) desc limit 50", ("E4017",)).fetchall()
mlist = [r[0] for r in mv2]; klist = [r[0] for r in kw2]
out["E4017_sentence_meaning_rank"] = (mlist.index("it-kb-E4017") + 1) if "it-kb-E4017" in mlist else None
# RRF merge
t0 = time.perf_counter()
score = {}
for lst in (mlist, klist):
    for rank, d in enumerate(lst, 1): score[d] = score.get(d, 0) + 1 / (60 + rank)
merged = sorted(score, key=lambda d: -score[d])
out["rrf_merge_ms"] = round((time.perf_counter() - t0) * 1000, 3)
out["E4017_after_merge_rank"] = merged.index("it-kb-E4017") + 1
# maternity through hybrid: keyword finds nothing, meaning carries it
kw3 = x("select count(*) from chunks, plainto_tsquery('english', 'maternity') q where tenant_id=1 and tsv @@ q").fetchone()[0]
out["maternity_keyword_hits"] = kw3

# tenant partitions: how many partitions a tenant query touches
plan = x("explain select id from chunks where tenant_id=1 order by embedding <=> %s limit 5", (qv,)).fetchall()
out["partitions_in_plan"] = sum(1 for (l,) in plan if "chunks_t" in l)

# transaction gap: delete, crash before insert
x("begin"); x("delete from chunks where tenant_id=1 and doc_id='hr-handbook' and page=12")
mid = c.cursor()
gap = psycopg.connect("host=localhost port=5433 user=postgres", autocommit=True)
# no transaction: simulate a crash between two separate statements
x("rollback")
x("delete from chunks where tenant_id=1 and doc_id='hr-handbook' and page=12")
out["chunks_for_page12_after_delete_then_crash"] = x("select count(*) from chunks where tenant_id=1 and doc_id='hr-handbook' and page=12").fetchone()[0]
# put it back, then do it right in one transaction and kill in the middle
p12 = [r for r in HANDBOOK if r[0] == 12][0]; e12 = vec(emb([f"{p12[1]}. {p12[2]}"])[0])
x("insert into chunks (tenant_id, doc_id, page, text, readers, embedding) values (1,'hr-handbook',12,%s,%s,%s)", (f"{p12[1]}. {p12[2]}", ["all-staff"], e12))
w = psycopg.connect("host=localhost port=5433 user=postgres")
w.execute("delete from chunks where tenant_id=1 and doc_id='hr-handbook' and page=12")
w.close()  # connection dies before commit
out["chunks_for_page12_after_crash_inside_transaction"] = x("select count(*) from chunks where tenant_id=1 and doc_id='hr-handbook' and page=12").fetchone()[0]

# idempotent write: run the same write twice
def write_page(conn):
    with conn.transaction():
        conn.execute("delete from chunks where tenant_id=1 and doc_id='hr-handbook' and page=12")
        conn.execute("insert into chunks (tenant_id, doc_id, page, text, readers, embedding) values (1,'hr-handbook',12,%s,%s,%s)", (f"{p12[1]}. {p12[2]}", ["all-staff"], e12))
wc = psycopg.connect("host=localhost port=5433 user=postgres")
write_page(wc); a = x("select count(*) from chunks where tenant_id=1").fetchone()[0]
write_page(wc); b = x("select count(*) from chunks where tenant_id=1").fetchone()[0]
out["rows_after_write_once"] = a; out["rows_after_write_twice"] = b

json.dump(out, open("m2.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
