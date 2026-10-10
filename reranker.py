import os, re, threading

MODEL_NAME = os.environ.get("RAG_RERANKER", "cross-encoder/ms-marco-MiniLM-L6-v2")
_model = None
_load_lock = threading.Lock()


def _words(s):
    return set(re.findall(r"[a-z0-9_.]+", s.lower()))


def score_pairs(query, texts):
    """One relevance score per text (higher = more relevant). Only the ORDER means anything, not the numbers."""
    if os.environ.get("FAKE_RERANK") == "1":
        q = _words(query)
        return [len(q & _words(t)) / (len(q) or 1) for t in texts]
    global _model
    if _model is None:
        with _load_lock:                                     # two visitors' first questions must not each load the model
            if _model is None:
                from sentence_transformers import CrossEncoder
                _model = CrossEncoder(MODEL_NAME, max_length=512)    # question + chunk longer than 512 tokens: the end is cut
    with _load_lock:                                         # one rerank at a time: Hugging Face tokenizers can fail ("Already borrowed")
        return [float(x) for x in _model.predict([(query, t) for t in texts], batch_size=16, show_progress_bar=False)]   # when used from several threads


def rerank(query, chunks):
    """chunks: list of dicts with a 'text'. Returns a new list sorted best first, each with 'rerank_score'."""
    scores = score_pairs(query, [c["text"] for c in chunks])
    out = [{**c, "rerank_score": s} for c, s in zip(chunks, scores)]
    return sorted(out, key=lambda c: -c["rerank_score"])
