import math, os
os.environ["FAKE_RERANK"] = "1"                              # word-overlap stand-in instead of the real cross-encoder
import numpy as np

import bm25, rag, reranker
from bm25 import BM25, tokenize

# ---------------------------------------------------------------- tokenizer
t = tokenize("Set `memory_bytes` in /etc/gitlab/gitlab.rb, fixed in 16.11.1. See [Executors](https://docs.gitlab.com/runner/executors/).")
assert "memory_bytes" in t and "memory" in t and "byte" in t, t              # whole word AND its parts ('bytes' -> 'byte')
assert "etc/gitlab/gitlab.rb" in t and "rb" in t, t
assert "16.11.1" in t and "16" not in t and "11" not in t, t                  # the version stays whole; bare numbers are dropped
assert "executor" in t and not any("docs.gitlab.com" in x for x in t), t      # plural folded, link target removed
assert "the" not in tokenize("the and of") and tokenize("How do I") == []
print("ok  tokenizer: memory_bytes / 16.11.1 / paths kept whole and in parts, link targets dropped, stop words dropped")

# ---------------------------------------------------------------- BM25 maths
docs = ["gitaly cgroups memory limit", "memory", "runner executors docker kubernetes", "memory memory memory padding " * 5]
b = BM25(docs, k1=1.5, b=0.75)
assert b.n == 4 and b.postings["memory"] == [(0, 1), (1, 1), (3, 15)]
# hand calculation for doc 1 ('memory', one word, length 1) and the query 'memory'
n_mem = 3                                                                      # 3 of 4 docs contain 'memory'
idf = math.log(1 + (4 - n_mem + 0.5) / (n_mem + 0.5))
dl, avg = b.dl[1], b.dl.mean()
want = idf * 1 * 2.5 / (1 + 1.5 * (1 - 0.75 + 0.75 * dl / avg))
assert abs(b.scores("memory")[1] - want) < 1e-9, (b.scores("memory")[1], want)
assert b.scores("memory")[2] == 0                                             # no shared word -> 0
assert b.scores("zzz").sum() == 0 and b.scores("the of").sum() == 0
assert b.idf["docker"] > b.idf["memory"]                                      # a word in 1 of 4 docs counts more than one in 3 of 4
top = b.top("gitaly memory", 3)
assert [i for i, _ in top] == [0, 3, 1], top      # doc 0 has both words; doc 3 repeats "memory" 15 times (but with diminishing returns)
assert b.top("memory", 5, allowed={2, 3})[0][0] == 3 and all(i in (2, 3) for i, _ in b.top("memory", 5, allowed={2, 3}))
print("ok  BM25: score matches the hand-calculated formula; rare words count more; filter and 'no match' work")

# ---------------------------------------------------------------- fusion
def hit(id, **kw):
    return {"id": id, "text": id, "title": "t", "section": "s", "url": "u", "distance": None, "bm25": None, "rrf": None,
            "rerank_score": None, **kw}

v = [hit("a", distance=.1), hit("b", distance=.2), hit("c", distance=.3)]
k_ = [hit("c", bm25=9.0), hit("d", bm25=5.0), hit("a", bm25=1.0)]
f = rag.rrf_fuse([v, k_])
assert [c["id"] for c in f] == ["a", "c", "b", "d"], [c["id"] for c in f]      # a: 1/61+1/63, c: 1/63+1/61 (tie -> a first), b, d
assert abs(f[0]["rrf"] - (1 / 61 + 1 / 63)) < 1e-12 and f[1]["rrf"] == f[0]["rrf"]
assert f[0]["distance"] == .1 and f[0]["bm25"] == 1.0 and f[1]["distance"] == .3 and f[1]["bm25"] == 9.0   # both scores kept
assert f[2]["bm25"] is None and f[3]["distance"] is None
print("ok  fusion: chunks found by both searches win; both scores are kept; formula 1/(60+rank) checked")

# ---------------------------------------------------------------- the real database
col = rag.get_collection()
probe = col.get(where={"source": "administration_gitaly_cgroups"}, include=["embeddings"])
rag.embed_query = lambda q: np.array(probe["embeddings"][0])                  # every question 'means' a Gitaly cgroups chunk

q = "memory_bytes"
kw = rag.search(q, k=5, mode="bm25")
assert len(kw) == 5 and all("memory_bytes" in c["text"] or "memory" in c["text"].lower() for c in kw)
assert kw[0]["bm25"] >= kw[-1]["bm25"] and kw[0]["distance"] is None and [c["rank"] for c in kw] == [1, 2, 3, 4, 5]
print("ok  bm25 mode: top hits really contain the word:", kw[0]["id"])

one = rag.search("Which security issues were fixed in GitLab 16.11.1?", k=5, mode="bm25")
assert any("16.11.1" in c["text"] for c in one) and one[0]["url"].count("16-11-1") == 1, [c["id"] for c in one]
print("ok  bm25 finds the version number:", sorted({c["id"].split("::")[0][-30:] for c in one}))

filt = rag.search("memory", k=5, mode="bm25", where={"source": "administration_gitaly_cgroups"})
assert filt and all(c["url"].endswith("/administration/gitaly/cgroups/") for c in filt)
try:
    rag.search("memory", mode="bm25", where={"$and": []})
    raise SystemExit("expected an error")
except ValueError:
    pass
print("ok  bm25 metadata filter works; complex filters are refused with a clear error")

hy = rag.search("memory_bytes", k=5, mode="hybrid")
assert len(hy) == 5 and all(c["rrf"] for c in hy) and [c["rank"] for c in hy] == [1, 2, 3, 4, 5]
assert any(c["distance"] is not None for c in hy) and any(c["bm25"] is not None for c in hy)
print("ok  hybrid mode: 5 fused hits carrying their scores")

rr = rag.search("memory_bytes", k=5, mode="hybrid_rerank")
assert len(rr) == 5 and all(c["rerank_score"] is not None for c in rr)
assert [c["rerank_score"] for c in rr] == sorted((c["rerank_score"] for c in rr), reverse=True)
pool = rag.rrf_fuse([rag.vector_search("memory_bytes", 30), rag.bm25_search("memory_bytes", 30)])[:30]
best = max(reranker.score_pairs("memory_bytes", [c["text"] for c in pool]))
assert abs(rr[0]["rerank_score"] - best) < 1e-9                                # the reranker picked from the 30 candidates
print("ok  hybrid_rerank: the best of the 30 candidates is now first")

assert rag.search("anything", k=3)[0]["distance"] < 1e-4                      # default mode is still vector search
try:
    rag.search("x", mode="nope")
    raise SystemExit("expected an error")
except ValueError as e:
    assert "nope" in str(e)
print("ok  default mode is vector (nothing changes unless you ask); unknown mode gives a clear error")

print("\nAll hybrid-search tests passed.")
