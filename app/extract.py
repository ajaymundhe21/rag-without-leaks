"""Line 1: get clean text out of a file, and cut it at the document's own headings (line 2)."""
import re
from pathlib import Path


def read_markdown(path: Path) -> list[tuple[int, str]]:
    """One chunk per '## N. Heading' section. N is the page number we link to."""
    text = path.read_text()
    title = text.splitlines()[0].lstrip("# ").strip() if text.startswith("#") else path.stem
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    out = []
    for part in parts:
        head, _, body = part.partition("\n")
        m = re.match(r"(\d+)\.\s*(.*)", head.strip())
        page, heading = (int(m.group(1)), m.group(2)) if m else (len(out) + 1, head.strip())
        body = " ".join(body.split())
        out.append((page, f"{title} · {heading}. {body}"))
    return out


def read_pdf(path: Path) -> list[tuple[int, str]]:
    """One chunk per page. Tables are read by row, and each row keeps its column names."""
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for n, page in enumerate(pdf.pages, 1):
            lines = []
            for table in page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"}):
                head, *rows = [[(c or "").strip() for c in r] for r in table]
                for r in rows:
                    lines.append(" · ".join(f"{h}: {v}" for h, v in zip(head, r) if h or v))
            text = " ".join(lines) if lines else (page.extract_text() or "")
            out.append((n, " ".join(text.split())))
    return out


def read_file(path: Path) -> list[tuple[int, str]]:
    if path.suffix == ".md":
        return read_markdown(path)
    if path.suffix == ".pdf":
        return read_pdf(path)
    raise ValueError(f"no reader for {path.suffix} yet (scanned files need OCR, emails need old replies cut)")
