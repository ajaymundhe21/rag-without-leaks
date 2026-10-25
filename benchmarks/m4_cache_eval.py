"""Measure 4: Redis cache hit vs full path, cache key leak, not-found threshold, negative test set, model switch."""
import json, time, numpy as np, psycopg, redis, subprocess
from wordllama import WordLlama
wl = WordLlama.load(disable_download=True)
def emb(t):
    v = wl.embed(t); return v / np.linalg.norm(v, axis=1, keepdims=True)
def vec(v): return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
c = psycopg.connect("host=localhost port=5433 user=postgres", autocommit=True); x = c.execute
subprocess.run("redis-server --port 6380 --daemonize yes >/dev/null", shell=True); time.sleep(1)
r = redis.Redis(port=6380); r.flushall()
out = {}
def search(q, groups):
    qv = vec(emb([q])[0])
    m = x("select id, doc_id, page, text, 1-(embedding <=> %s) from chunks where tenant_id=1 and readers && %s order by embedding <=> %s limit 50", (qv, groups, qv)).fetchall()
    k = x("select id, doc_id, page, text, 0 from chunks, plainto_tsquery('english', %s) qq where tenant_id=1 and readers && %s and tsv @@ qq order by ts_rank(tsv,qq) desc limit 50", (q, groups)).fetchall()
    s = {}
    for lst in (m, k):
        for rank, row in enumerate(lst, 1): s[row[:4]] = s.get(row[:4], 0) + 1/(60+rank)
    merged = sorted(s, key=lambda z: -s[z])[:5]
    return merged, (m[0][4] if m else 0)
Q = "How many weeks of maternity leave do I get?"
staff = ["all-staff", "engineering"]; board = ["all-staff", "board"]
# full path vs cache hit (search part only; no language model here)
ts = []
for _ in range(20):
    t = time.perf_counter(); search(Q, staff); ts.append((time.perf_counter()-t)*1000)
out["search_path_ms_median"] = round(float(np.median(ts)), 2)
key = "t1|" + Q.lower() + "|" + ",".join(sorted(staff))
r.set(key, json.dumps([row[1:3] for row in search(Q, staff)[0]]), ex=300)
ts = []
for _ in range(200):
    t = time.perf_counter(); r.get(key); ts.append((time.perf_counter()-t)*1000)
out["redis_hit_ms_median"] = round(float(np.median(ts)), 3)
# key = question only: board member asks first, normal user gets their answer
r.flushall()
bad_key = Q.lower()
board_ans = search(Q, board)[0]
r.set(bad_key, json.dumps([row[1] for row in board_ans]))
got = json.loads(r.get(bad_key))
out["bad_key_board_answer_docs"] = got
out["bad_key_normal_user_sees_restricted"] = sum(1 for d in got if d.startswith("restricted"))
good_key_staff = "t1|" + Q.lower() + "|" + ",".join(sorted(staff))
out["good_key_staff_hits_board_entry"] = r.get(good_key_staff) is not None
# not-found threshold: best meaning score for answered vs unanswered questions
answered = ["How many weeks of maternity leave do I get?", "How many days can I work remotely?", "When does my salary come?",
            "How many vacation days do I get in a year?", "Is there free counselling?", "When is the bonus paid?"]
unanswered = ["Can I carry my unused leave into next year?", "Can I bring my dog to the office?", "Is there a gym in the office?",
              "Do we get stock options?", "Can I change my manager?", "Is there a night shift allowance?"]
out["best_score_answered"] = [round(float(search(q, staff)[1]), 3) for q in answered]
out["best_score_unanswered"] = [round(float(search(q, staff)[1]), 3) for q in unanswered]
out["carry_leave_top3"] = [row[1:3] for row in search("Can I carry my unused leave into next year?", staff)[0][:3]]
# negative test set: questions that would find the board page, run as a normal user
neg = ["parental leave changes next year", "board compensation plan parental leave", "will parental leave become 16 weeks",
       "cost of parental leave per employee", "board estimate parental leave budget", "maternity paternity leave budget FY27",
       "new parental leave policy draft", "parental leave comparison with other companies"]
leaks = 0
for q in neg:
    res, _ = search(q, staff); leaks += sum(1 for row in res if row[1].startswith("restricted"))
out["negative_set_questions"] = len(neg); out["negative_set_restricted_rows_returned"] = leaks
board_found = sum(1 for q in neg if any(row[1].startswith("restricted") for row in search(q, board)[0]))
out["same_questions_as_board_member_find_restricted"] = board_found
# model switch: question from a different model cannot even be compared
try:
    x("select embedding <=> %s from chunks limit 1", ("[" + ",".join(["0.1"]*100) + "]",)).fetchone(); out["model_switch_error"] = None
except Exception as e:
    out["model_switch_error"] = str(e).split("\n")[0]
json.dump(out, open("m4.json","w"), indent=1); print(json.dumps(out, indent=1))
