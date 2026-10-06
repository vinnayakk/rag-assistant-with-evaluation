import os, re, hashlib
import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"          # 384 numbers per text, reads up to 512 tokens, free, runs locally
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "   # recommended by the model's authors, queries only
DIM = 384

_model = None
def _load():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
        _model.max_seq_length = 512
    return _model

def _fake(texts):
    """Offline stand-in for TESTING the pipeline only (hashed bag of words). Not real semantic search."""
    out = np.zeros((len(texts), DIM), dtype="float32")
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1
    n = np.linalg.norm(out, axis=1, keepdims=True); n[n == 0] = 1
    return out / n

def embed_documents(texts, show_progress=True):
    if os.environ.get("FAKE_EMBED"):
        return _fake(texts)
    return _load().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=show_progress)

def embed_query(text):
    if os.environ.get("FAKE_EMBED"):
        return _fake([text])[0]
    return _load().encode([QUERY_PREFIX + text], normalize_embeddings=True)[0]
