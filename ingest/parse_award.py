"""
Parse a saved award HTML file into clause chunks for RAG.

Save the award page first as data/raw/MA000009.html
(browser Ctrl+S, "Webpage, HTML Only").

The award HTML marks every paragraph with a CSS class, so we use those
instead of guessing from text:
  Partheading                 -> "Part 5— Overtime and Penalty Rates"
  Level1                      -> clause heading      "28. Overtime"
  Subdocument                 -> schedule heading    "Schedule A — ..."
  Level2 / Level2Bold         -> subclause           "28.1 Reasonable overtime"
  SubLevel1 / SubLevel1Bold   -> schedule subclause  "A.1 Introductory level"
  History, TOC1, TOC2         -> skipped (variation notes, table of contents)
  everything else             -> body text of the current subclause
Tables are turned into "cell | cell | cell" rows.

One chunk per subclause. Long ones are split on paragraph boundaries.

Run: python ingest/parse_award.py MA000009
"""
import re
import sys
import json
from bs4 import BeautifulSoup

AWARD = sys.argv[1] if len(sys.argv) > 1 else "MA000009"
IN_FILE = f"data/raw/{AWARD}.html"
OUT_FILE = f"data/processed/{AWARD}_chunks.json"

MAX_CHARS = 1500

PART = {"Partheading"}
CLAUSE = {"Level1", "Subdocument"}
SUBCLAUSE = {"Level2", "Level2Bold", "SubLevel1", "SubLevel1Bold"}
SKIP = {"History", "TOC1", "TOC2", "Footer"}

CLAUSE_NO = re.compile(r"^(\d{1,2})\.\s*(.*)$")
SCHED_NO = re.compile(r"^Schedule\s+([A-Z]{1,2})\s*[—–-]\s*(.*)$")
SUB_NO = re.compile(r"^([A-Z]{0,2}\d{0,2}\.\d{1,2})\s+(.*)$")


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def classes(el):
    return set(el.get("class") or [])


def table_text(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def award_body(soup):
    """Smallest element that holds every clause and schedule heading.
    Everything outside it (site menus, footer) is ignored."""
    heads = soup.find_all("p", class_=list(CLAUSE))
    box = heads[0].parent
    while box is not None and not all(box in h.parents for h in heads):
        box = box.parent
    return box or soup


def walk(soup):
    """Yield (kind, text) in document order, for award content only."""
    for el in award_body(soup).find_all(["p", "table"]):
        if el.name == "table":
            if el.find_parent("table"):
                continue                     # nested table, handled by parent
            if el.find(class_="AMODTable") is None:
                continue                     # not an award table
            yield "text", table_text(el)
            continue
        if el.find_parent("table"):
            continue                         # cell text, already in the table
        cls = classes(el)
        text = clean(el.get_text(" "))
        if not text or cls & SKIP:
            continue
        if cls & PART:
            yield "part", text
        elif cls & CLAUSE:
            yield "clause", text
        elif cls & SUBCLAUSE:
            yield "sub", text
        else:
            yield "text", text


def build_sections(soup):
    sections = []                            # one per subclause
    part, clause_no, clause_title = "", None, ""
    current = None

    def start(sub_no, sub_title, first_text):
        nonlocal current
        current = {"part": part, "clause_no": clause_no,
                   "clause_title": clause_title, "sub_no": sub_no,
                   "sub_title": sub_title, "paras": [first_text] if first_text else []}
        sections.append(current)

    for kind, text in walk(soup):
        if kind == "part":
            part = text
        elif kind == "clause":
            m = CLAUSE_NO.match(text) or SCHED_NO.match(text)
            if not m:
                continue
            clause_no = m.group(1) if CLAUSE_NO.match(text) else f"Schedule {m.group(1)}"
            clause_title = m.group(2)
            if clause_no.startswith("Schedule"):
                part = ""
            start(None, "", "")              # intro text before the first subclause
        elif kind == "sub" and clause_no:
            m = SUB_NO.match(text)
            sub_no = m.group(1) if m else None
            rest = m.group(2) if m else text
            # bold subclause lines are short headings, plain ones carry text
            is_heading = len(rest) < 90 and not rest.endswith(".")
            start(sub_no, rest if is_heading else "", text)
        elif kind == "text" and current is not None:
            current["paras"].append(text)
    return [s for s in sections if s["paras"]]


def header(s):
    label = s["clause_no"] if s["clause_no"].startswith("Schedule") else f"{s['clause_no']}."
    parts = [AWARD]
    if s["part"]:
        parts.append(s["part"])
    parts.append(f"{label} {s['clause_title']}")
    if s["sub_no"]:
        parts.append(f"{s['sub_no']} {s['sub_title']}".strip())
    return "[" + " > ".join(parts) + "]"


def to_chunks(sections):
    chunks = []
    for s in sections:
        head = header(s)
        groups, buf = [], []
        for p in s["paras"]:
            if buf and len("\n".join(buf + [p])) > MAX_CHARS:
                groups.append(buf)
                buf = [buf[-1]]              # overlap: repeat the last paragraph
            buf.append(p)
        groups.append(buf)
        for g in groups:
            body = "\n".join(g)
            chunks.append({
                "award": AWARD,
                "clause": s["sub_no"] or s["clause_no"],
                "parent_clause": s["clause_no"],
                "title": s["clause_title"],
                "part": s["part"],
                "text": head + "\n" + body,
                "chars": len(body),
            })
    return chunks


if __name__ == "__main__":
    with open(IN_FILE, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    sections = build_sections(soup)
    chunks = to_chunks(sections)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    clauses = list(dict.fromkeys(c["parent_clause"] for c in chunks))
    print(f"clauses: {len(clauses)} | subclauses: {len(sections)} | chunks: {len(chunks)}")
    print(f"saved to {OUT_FILE}\n")
    for test in ["11", "16", "28", "29", "Schedule B"]:
        subs = [c["clause"] for c in chunks if c["parent_clause"] == test]
        print(f"{test}: {len(subs)} chunks -> {subs[:8]}")
    print()
    for c in chunks:
        if c["clause"] == "29.2":
            print(c["text"][:600])
            break