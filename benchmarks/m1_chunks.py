"""Measure 1: word search vs meaning search, whole doc vs chunks, chunk size on 21 questions."""
import re, json, numpy as np
from wordllama import WordLlama
from data import HANDBOOK
wl = WordLlama.load(disable_download=True)
def emb(texts):
    v = wl.embed(texts); v = v / np.linalg.norm(v, axis=1, keepdims=True); return v
Q = "How many weeks of maternity leave do I get?"
out = {}

# 1. word search
out["word_search_maternity_hits"] = sum(1 for p,h,b in HANDBOOK if "maternity" in (h+" "+b).lower())

# 2. whole handbook as one item vs page-12 chunk vs WFH page
whole = " ".join(f"{h}. {b}" for p,h,b in HANDBOOK)
pages = [f"{h}. {b}" for p,h,b in HANDBOOK]
qv = emb([Q])[0]
out["score_whole_handbook"] = float(emb([whole])[0] @ qv)
pv = emb(pages); s = pv @ qv
out["score_page12"] = float(s[11]); out["score_wfh_page3"] = float(s[2])
out["rank_page12_among_40"] = int((s > s[11]).sum()) + 1
out["whole_handbook_words"] = len(whole.split())
wfh_q = "Can I work from home?"
out["wfh_question_vs_whole"] = float(emb([whole])[0] @ emb([wfh_q])[0])

# 3. strategies
def sentences(t): return [x.strip() for x in re.split(r'(?<=[.!?])\s+', t) if x.strip()]
def strat_sentence():
    return [(p, s_) for p,h,b in HANDBOOK for s_ in sentences(f"{h}. {b}")]
def strat_heading():
    return [(p, f"{h}. {b}") for p,h,b in HANDBOOK]
def strat_three_pages():
    out_=[];
    for i in range(0, len(HANDBOOK), 3):
        grp = HANDBOOK[i:i+3]; out_.append((grp[0][0], " ".join(f"{h}. {b}" for p,h,b in grp)))
    return out_
def strat_heading_overlap():
    ch=[]
    for i,(p,h,b) in enumerate(HANDBOOK):
        prev_last = sentences(HANDBOOK[i-1][2])[-1] if i>0 else ""
        ch.append((p, f"{prev_last} {h}. {b}".strip()))
    return ch

GOLD = [
 ("How many weeks of maternity leave do I get?", "12 weeks"),
 ("How many days can I work remotely?", "two days a week"),
 ("How much is the reward for referring a friend?", "50,000"),
 ("When does my salary come?", "last working day"),
 ("Do I get paid time off when someone in my family dies?", "5 days"),
 ("How much can I spend on courses and books?", "25,000"),
 ("Is my wife covered by medical insurance?", "spouse"),
 ("How long is my notice when I resign?", "60 days"),
 ("Is there a bus from the metro station?", "shuttles"),
 ("Can I do freelance work on weekends?", "written approval"),
 ("How many vacation days do I get in a year?", "18 days"),
 ("When do appraisals happen?", "April and October"),
 ("What do I do if I lose my laptop?", "24 hours"),
 ("Can I get money back for a new monitor?", "15,000"),
 ("Do I get money for wifi at home?", "1,000 rupees"),
 ("How many days off do I get when I am ill?", "10 days"),
 ("What time does lunch start?", "12:30"),
 ("Can I accept a present from a vendor?", "2,000"),
 ("Who do I go to if my manager does not fix my complaint?", "raise it with HR"),
 ("Is there free counselling?", "six free sessions"),
 ("When is the bonus paid?", "April"),
]
gq = emb([q for q,_ in GOLD])
res = {}
for name, fn in [("one_sentence", strat_sentence), ("by_heading", strat_heading), ("three_pages", strat_three_pages), ("heading_plus_overlap", strat_heading_overlap)]:
    ch = fn(); cv = emb([t for _,t in ch]); S = gq @ cv.T
    hit1 = hit3 = 0; maternity = None
    for i,(q,key) in enumerate(GOLD):
        order = np.argsort(-S[i])
        top1 = ch[order[0]][1]; top3 = " ".join(ch[j][1] for j in order[:3])
        hit1 += key in top1; hit3 += key in top3
        if i == 0: maternity = {"top1_text": top1, "top1_has_answer": key in top1, "top1_score": float(S[i][order[0]])}
    res[name] = {"chunks": len(ch), "top1_correct": hit1, "top3_correct": hit3, "of": len(GOLD), "maternity": maternity}
out["chunk_strategies"] = res
print(json.dumps(out, indent=1))
json.dump(out, open("m1.json","w"), indent=1)
