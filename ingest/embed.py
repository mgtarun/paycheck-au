# ingest/embed.py
import json, sys
from functools import lru_cache
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder

MODEL = "BAAI/bge-m3"
RERANKER = "BAAI/bge-reranker-v2-m3"
DB_DIR = "data/chroma"
COLLECTION = "awards"


@lru_cache
def get_model():
    return SentenceTransformer(MODEL)


@lru_cache
def get_reranker():
    return CrossEncoder(RERANKER, max_length=512)


@lru_cache
def get_collection():
    client = chromadb.PersistentClient(path=DB_DIR)
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def build(award):
    chunks = json.loads(Path(f"data/processed/{award}_chunks.json").read_text(encoding="utf-8"))
    texts = [c["text"] for c in chunks]

    vecs = get_model().encode(texts, batch_size=16, normalize_embeddings=True,
                              show_progress_bar=True)

    col = get_collection()
    col.delete(where={"award": award})          # clean re-run, no stale chunks

    col.add(
        ids=[f"{award}-{i}" for i in range(len(chunks))],
        embeddings=vecs.tolist(),
        documents=texts,
        metadatas=[{
            "award": c["award"],
            "clause": str(c.get("clause") or ""),
            "parent_clause": str(c.get("parent_clause") or ""),
            "title": c.get("title") or "",
            "part": c.get("part") or "",
        } for c in chunks],
    )
    print(f"stored {len(chunks)} chunks for {award} -> {DB_DIR}")


def search(query, k=4, award=None, rerank=False, fetch=20):
    # step 1: vector search (fetch more than k if we will rerank)
    n = fetch if rerank else k
    q = get_model().encode([query], normalize_embeddings=True).tolist()
    res = get_collection().query(
        query_embeddings=q, n_results=n,
        where={"award": award} if award else None,
    )
    results = [
        {"text": d, "score": round(1 - dist, 3), **m}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
    if not rerank:
        return results

    # step 2: cross encoder reads (question, chunk) together and re-scores
    scores = get_reranker().predict([(query, r["text"]) for r in results])
    for r, s in zip(results, scores):
        r["vector_score"] = r["score"]
        r["score"] = round(float(s), 3)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:k]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python ingest/embed.py MA000009   OR   search "question" [--rerank]')
    elif sys.argv[1] == "search":
        rerank = "--rerank" in sys.argv
        words = [w for w in sys.argv[2:] if w != "--rerank"]
        for r in search(" ".join(words), rerank=rerank):
            print(f"{r['score']}  clause {r['clause']}  {r['title']}")
    else:
        build(sys.argv[1])