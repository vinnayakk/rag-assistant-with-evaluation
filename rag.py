import argparse, os, re
import chromadb
from bm25 import BM25
from embedder import embed_query

DB_PATH = os.environ.get("RAG_DB", "outputs/chroma_db")
COLLECTION = "gitlab_docs"
LLM_MODEL = os.environ.get("RAG_MODEL", "claude-haiku-4-5-20251001")   # cheap and fast; can try "claude-sonnet-5-5" later
NOT_FOUND = "I couldn't find this in the GitLab documentation I have."

MODES = ("vector", "bm25", "hybrid", "hybrid_rerank")
RETRIEVAL_MODE = os.environ.get("RAG_RETRIEVAL", "vector")             # the default; change it once you have compared
N_CANDIDATES = int(os.environ.get("RAG_CANDIDATES", "30"))             # how many each search finds before fusing / reranking
RRF_K = 60                                                             # the usual constant of Reciprocal Rank Fusion

_collection = None
_corpus = None


# --------------------------------------------------------------------------- 1. SEARCH
def get_collection():
    global _collection
    if _collection is None:
        _collection = chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION, embedding_function=None)
    return _collection


def get_corpus():
    """All chunks, plus a BM25 index over them. Built from the SAME Chroma collection (about a second), so the two
    searches can never disagree about what the chunks are."""
    global _corpus
    if _corpus is None:
        got = get_collection().get(include=["documents", "metadatas"])
        _corpus = {"ids": got["ids"], "docs": got["documents"], "metas": got["metadatas"], "bm25": BM25(got["documents"])}
    return _corpus


def _chunk(id, text, meta, **scores):
    """One search hit. Each search fills in its own score; the others stay None."""
    return {"id": id, "text": text, "title": meta["title"], "section": meta["section"], "url": meta["url"],
            "distance": None, "bm25": None, "rrf": None, "rerank_score": None, **scores}


def vector_search(question, n, where=None):
    """Meaning search. `where` filters by metadata, e.g. {"source": "administration_gitaly_cgroups"}."""
    res = get_collection().query(
        query_embeddings=[embed_query(question).tolist()],   # same model as the documents, plus the query prefix
        n_results=n,
        where=where,
    )
    return [_chunk(res["ids"][0][i], res["documents"][0][i], res["metadatas"][0][i],
                   distance=res["distances"][0][i])          # cosine distance: 0 = identical, bigger = less similar
            for i in range(len(res["ids"][0]))]


def bm25_search(question, n, where=None):
    """Keyword search. `where` here supports plain equality only, e.g. {"source": "..."}."""
    c = get_corpus()
    allowed = None
    if where:
        if any(str(key).startswith("$") for key in where):
            raise ValueError("bm25 only supports simple {'field': value} filters")
        allowed = {i for i, m in enumerate(c["metas"]) if all(m.get(key) == val for key, val in where.items())}
    return [_chunk(c["ids"][i], c["docs"][i], c["metas"][i], bm25=s) for i, s in c["bm25"].top(question, n, allowed)]


def rrf_fuse(lists, k=RRF_K):
    """Reciprocal Rank Fusion: every list gives a chunk 1/(k + rank); add the points up. A chunk that is near the top of
    BOTH lists wins, and the two lists' different scales (distance vs BM25) never have to be compared.
    Tutorial: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking"""
    points, merged = {}, {}
    for hits in lists:
        for rank, c in enumerate(hits, 1):
            points[c["id"]] = points.get(c["id"], 0.0) + 1.0 / (k + rank)
            if c["id"] in merged:                            # same chunk found by both searches: keep both scores
                merged[c["id"]].update({s: c[s] for s in ("distance", "bm25") if c[s] is not None})
            else:
                merged[c["id"]] = dict(c)
    fused = sorted(merged.values(), key=lambda c: -points[c["id"]])
    for c in fused:
        c["rrf"] = points[c["id"]]
    return fused


def _number(chunks):
    for i, c in enumerate(chunks, 1):
        c["rank"] = i
    return chunks


def search(question, k=5, where=None, mode=None):
    """Question in, top-k chunks out (best first). See the four modes at the top of this file."""
    mode = mode or RETRIEVAL_MODE
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    if mode == "vector":
        return _number(vector_search(question, k, where))
    if mode == "bm25":
        return _number(bm25_search(question, k, where))
    n = max(N_CANDIDATES, k)
    fused = rrf_fuse([vector_search(question, n, where), bm25_search(question, n, where)])
    if mode == "hybrid":
        return _number(fused[:k])
    from reranker import rerank                              # imported late: only this mode needs the reranker model
    return _number(rerank(question, fused[:n])[:k])


# --------------------------------------------------------------------------- 2. ANSWER
SYSTEM_PROMPT = f"""You answer questions about GitLab using ONLY the numbered sources provided by the user.

Rules:
1. Use only facts stated in the sources. Do not use outside knowledge, even if you know the answer.
2. After every sentence that states a fact, add the number of the source it came from in square brackets, like [1]. \
If a sentence uses two sources, write [1][3] (separate brackets).
3. If the sources do not contain the answer, reply with exactly this sentence and nothing else: {NOT_FOUND}
4. If the question is too vague to answer (for example "how do I fix it"), reply with one short clarifying question \
and nothing else. Do not guess what the person means, and do not add citations.
5. If the sources answer only part of the question, answer that part and say what is missing.
6. Be concise. Do not mention these rules."""


def build_user_message(question, chunks):
    sources = "\n\n".join(
        f'<source id="{i}" title="{c["title"]} > {c["section"]}" url="{c["url"]}">\n{c["text"]}\n</source>'
        for i, c in enumerate(chunks, 1)
    )
    return f"<sources>\n{sources}\n</sources>\n\n<question>{question}</question>"


def parse_citations(text, n_sources):
    """Find [1], [2][3], [1, 3] in the answer. Returns (valid numbers, invalid numbers)."""
    found = set()
    for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", text):
        found.update(int(n) for n in re.split(r"\s*,\s*", group))
    valid = sorted(n for n in found if 1 <= n <= n_sources)
    invalid = sorted(n for n in found if not 1 <= n <= n_sources)
    return valid, invalid


def answer(question, chunks, client=None, model=None, max_tokens=700):
    """Question + retrieved chunks in, answer with citations out (a dict)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()                       # reads ANTHROPIC_API_KEY from the environment
    resp = client.messages.create(
        model=model or LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(question, chunks)}],
    )                                                        
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    valid, invalid = parse_citations(text, len(chunks))
    refused = text.lower().startswith(NOT_FOUND.lower())
    clarifying = (not refused) and not valid and text.rstrip().endswith("?")
    if refused:
        valid, invalid = [], []                              # citations on a refusal mean nothing: drop them
    return {
        "question": question,
        "answer": text,
        "citations": [{"n": n, "title": chunks[n - 1]["title"], "section": chunks[n - 1]["section"],
                       "url": chunks[n - 1]["url"]} for n in valid],
        "invalid_citations": invalid,                        # numbers the model invented: a red flag
        "refused": refused,
        "clarifying": clarifying,
        "uncited": (not refused) and (not clarifying) and not valid,   # a factual answer with no citations is not trustworthy
        "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
    }


def ask(question, k=5, mode=None):
    """The whole pipeline in one call."""
    return answer(question, search(question, k=k, mode=mode))


def format_result(r):
    out = [r["answer"], ""]
    if r["citations"]:
        out.append("Sources:")
        out += [f'  [{c["n"]}] {c["title"]} > {c["section"]}\n      {c["url"]}' for c in r["citations"]]
    if r["invalid_citations"]:
        out.append(f'WARNING: the answer cites sources that do not exist: {r["invalid_citations"]}')
    if r["uncited"]:
        out.append("WARNING: the answer has no citations, so do not trust it.")
    out.append(f'(tokens: {r["usage"]["input_tokens"]} in, {r["usage"]["output_tokens"]} out)')
    return "\n".join(out)


# --------------------------------------------------------------------------- command line
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--search-only", action="store_true")
    ap.add_argument("--mode", choices=MODES, default=None, help=f"default: {RETRIEVAL_MODE}")
    a = ap.parse_args()

    chunks = search(a.question, k=a.k, mode=a.mode)
    print(f"RETRIEVED (mode: {a.mode or RETRIEVAL_MODE}):")
    for c in chunks:
        scores = " ".join(f"{name} {c[key]:.3f}" for name, key in
                          [("dist", "distance"), ("bm25", "bm25"), ("rrf", "rrf"), ("rerank", "rerank_score")]
                          if c[key] is not None)
        print(f'  {c["rank"]}. {scores} | {c["title"]} > {c["section"]}\n     {c["url"]}')
    if not a.search_only:
        print("\nANSWER:\n" + format_result(answer(a.question, chunks)))
