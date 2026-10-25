"""Writes the demo documents into data/docs. All text is made up for the demo."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from demo_data import HANDBOOK, BOARD_PAGE, VARIANTS, ERROR_TOPICS

root = os.path.join(os.path.dirname(__file__), "..", "data", "docs")
def put(path, text):
    p = os.path.join(root, path); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)

# HR folder: everyone can read it. Pages take their permission from the folder.
put("hr/_acl.json", json.dumps({"readers": ["all-staff"]}))
put("hr/hr-handbook.md", "# HR handbook\n\n" + "\n\n".join(f"## {p}. {h}\n\n{b}" for p, h, b in HANDBOOK) + "\n")

# Board, exec, finance and legal folders: only that group can read them.
groups = ["board", "exec", "finance", "legal"]
for g in groups: put(f"{g}/_acl.json", json.dumps({"readers": [g]}))
put("board/compensation-plan-fy27.md", f"# {BOARD_PAGE[0]}\n\n## 1. Parental leave\n\n{BOARD_PAGE[1]}\n")
for i in range(1, 32):
    g = groups[i % 4]
    put(f"{g}/note-{i:02d}.md", f"# Note {i}\n\n## 1. Note {i}\n\n{VARIANTS[i % len(VARIANTS)]} Note {i}.\n")

# IT knowledge base: one page per error code.
put("it-kb/_acl.json", json.dumps({"readers": ["all-staff"]}))
for i in range(40):
    topic, fix = ERROR_TOPICS[i % len(ERROR_TOPICS)]
    code = f"E40{i:02d}"
    put(f"it-kb/{code}.md", f"# Error {code} ({topic})\n\n## 1. Error {code}\n\nIf you see error {code} on your screen, here is what it means. {fix}\n")
print("docs written to", os.path.abspath(root))
