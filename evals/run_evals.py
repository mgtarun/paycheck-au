# evals/run_evals.py
# usage:
#   python evals/run_evals.py            -> vectors only (baseline)
#   python evals/run_evals.py rerank     -> vectors top 20, then reranker
import json, sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from ingest.embed import search

K = 4
RERANK = "rerank" in sys.argv[1:]

golden = [json.loads(l) for l in Path("evals/golden_rules.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

hits, rr = 0, 0.0
for g in golden:
    res = search(g["q"], k=K, award="MA000009", rerank=RERANK)
    found = [r["parent_clause"] for r in res]
    rank = next((i + 1 for i, c in enumerate(found) if c == g["clause"]), None)
    if rank:
        hits += 1
        rr += 1 / rank
    mark = f"rank {rank}" if rank else "MISS  "
    print(f"{mark:7} want {g['clause']:>3}  got {found}  | {g['q']}")

n = len(golden)
print(f"\nmode: {'rerank' if RERANK else 'vectors only'}")
print(f"recall@{K}: {hits}/{n} = {hits / n:.0%}")
print(f"MRR: {rr / n:.2f}")