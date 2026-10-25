"""Run every day. Scores the search on questions where we know the right page,
and checks that restricted pages never reach a person who cannot open them.

    python -m eval.run
"""
import json, sys
from pathlib import Path
from app.identity import login
from app.search import search

HERE = Path(__file__).parent
RESTRICTED = ("board/", "exec/", "finance/", "legal/")


def golden(user="emp-1"):
    tenant, groups = login(user)
    rows = [json.loads(l) for l in open(HERE / "golden.jsonl")]
    top1 = top5 = 0
    misses = []
    for g in rows:
        hits = [(c["doc_id"], c["page"]) for c in search(tenant, groups, g["question"])[:5]]
        want = (g["doc_id"], g["page"])
        top1 += hits[:1] == [want]
        top5 += want in hits
        if want not in hits:
            misses.append(g["question"])
    return {"questions": len(rows), "right_page_first": top1, "right_page_in_top5": top5, "misses": misses}


def leak(user):
    tenant, groups = login(user)
    qs = [l.strip() for l in open(HERE / "leak_questions.txt") if l.strip()]
    restricted_rows, questions_that_found_one = 0, 0
    for q in qs:
        res = search(tenant, groups, q)
        n = sum(1 for c in res if c["doc_id"].startswith(RESTRICTED))
        restricted_rows += n
        questions_that_found_one += n > 0
    return {"user": user, "questions": len(qs), "restricted_rows": restricted_rows,
            "questions_that_found_restricted": questions_that_found_one}


if __name__ == "__main__":
    g = golden()
    emp, board = leak("emp-1"), leak("board-1")
    print(json.dumps({"golden": g, "leak_as_employee": emp, "leak_as_board_member": board}, indent=1))
    # The employee run must return zero. The board run must find them, or the test cannot catch a leak at all.
    ok = emp["restricted_rows"] == 0 and board["questions_that_found_restricted"] > 0
    print("LEAK TEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
