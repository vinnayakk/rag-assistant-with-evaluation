import argparse, json, pathlib, time
import chromadb
from embedder import embed_documents, MODEL_NAME

ap = argparse.ArgumentParser()
ap.add_argument("chunks", nargs="?", default="outputs/chunks.jsonl")
ap.add_argument("db", nargs="?", default="outputs/chroma_db")
ap.add_argument("--collection", default="gitlab_docs")
ap.add_argument("--reset", action="store_true")
a = ap.parse_args()

rows = [json.loads(l) for l in open(a.chunks, encoding="utf-8")]
client = chromadb.PersistentClient(path=a.db)          # saved to disk; reopen it any time
if a.reset:
    try: client.delete_collection(a.collection)
    except Exception: pass
col = client.get_or_create_collection(
    name=a.collection,
    metadata={"hnsw:space": "cosine", "embedding_model": MODEL_NAME},   # how "closeness" is measured
    embedding_function=None,                            # compute vectors
)

done = set(col.get(include=[])["ids"])                  # makes the script safe to re-run
todo = [r for r in rows if r["id"] not in done]
print(f"{len(rows)} chunks total, {len(done)} already stored, embedding {len(todo)}")

t0 = time.time()
BATCH = 128
for i in range(0, len(todo), BATCH):
    batch = todo[i:i + BATCH]
    vectors = embed_documents([r["text"] for r in batch], show_progress=False)
    col.upsert(
        ids=[r["id"] for r in batch],
        embeddings=vectors.tolist(),
        documents=[r["text"] for r in batch],
        metadatas=[{k: r[k] for k in ("source", "title", "section", "url", "tier", "n_tokens", "chunk_index")} for r in batch],
    )
    print(f"  {min(i + BATCH, len(todo))}/{len(todo)}  ({time.time() - t0:.0f}s)")

print(f"Done. Collection '{a.collection}' now holds {col.count()} chunks at {a.db}")
