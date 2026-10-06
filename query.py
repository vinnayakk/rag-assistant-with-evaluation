import argparse
import chromadb
from embedder import embed_query

ap = argparse.ArgumentParser()
ap.add_argument("question", nargs="?")
ap.add_argument("-k", type=int, default=5)
ap.add_argument("--db", default="outputs/chroma_db")
ap.add_argument("--collection", default="gitlab_docs")
a = ap.parse_args()

col = chromadb.PersistentClient(path=a.db).get_collection(a.collection, embedding_function=None)
questions = [a.question] if a.question else [
    "How do I limit memory and CPU for Gitaly?",
    "What events can trigger a webhook?",
    "How do I find out which GitLab version I am running?",
    "Which SAST analyzers are supported?",
    "How do I set up database replication for Geo?",
]
for q in questions:
    res = col.query(query_embeddings=[embed_query(q).tolist()], n_results=a.k)
    print("\n" + "=" * 78 + f"\nQ: {q}")
    for rank, (doc, meta, dist) in enumerate(zip(res["documents"][0], res["metadatas"][0], res["distances"][0]), 1):
        snippet = doc.split("\n\n", 1)[-1].replace("\n", " ")[:150]
        print(f"{rank}. dist {dist:.3f} | {meta['title']} > {meta['section']}\n   {meta['url']}\n   {snippet}...")
