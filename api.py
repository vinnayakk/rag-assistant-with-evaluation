import logging, os, time
from contextlib import asynccontextmanager
from typing import Literal, Optional

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

import rag

log = logging.getLogger("uvicorn.error")          # shows up in the same terminal as uvicorn's own messages


# --------------------------------------------------------------------------- what goes in and out
class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)      # "   " counts as empty
    question: str = Field(min_length=3, max_length=500, examples=["How do I limit memory for Gitaly?"])
    k: int = Field(5, ge=1, le=10, description="how many chunks to retrieve and give to the model")
    mode: Optional[Literal["vector", "bm25", "hybrid", "hybrid_rerank"]] = Field(
        None, description="how to search; leave empty for the server default (env RAG_RETRIEVAL, otherwise vector)")
    debug: bool = Field(False, description="also return the full text of each retrieved chunk")


class Citation(BaseModel):
    n: int
    title: str
    section: str
    url: str


class Retrieved(BaseModel):
    rank: int
    id: str
    title: str
    section: str
    url: str
    # each search fills in its own score; the ones that did not take part are null
    distance: Optional[float] = None          # vector search: cosine distance, smaller = closer
    bm25: Optional[float] = None              # keyword search: bigger = more shared (rare) words
    rrf: Optional[float] = None               # hybrid: fused score
    rerank_score: Optional[float] = None      # reranker: only the order matters, not the number
    text: Optional[str] = None                # only filled when debug=true


class AskResponse(BaseModel):
    question: str
    mode: str                                 # the search mode that was actually used
    answer: str
    # one word that says what kind of reply this is (rag.answer() returns three separate flags; this merges them)
    status: Literal["answered", "refused", "clarifying", "uncited"]
    citations: list[Citation]
    invalid_citations: list[int]              # [n] the model cited that do not exist: a red flag
    retrieved: list[Retrieved]                # everything the model saw, so you can see WHY an answer failed
    usage: dict
    timing_ms: dict


# --------------------------------------------------------------------------- start-up: load things ONCE
@asynccontextmanager
async def lifespan(app: FastAPI):
    rag.get_collection()                      # fails right now (not on the first request) if the database path is wrong
    rag.embed_query("warm up")                # loads the embedding model now, so the first real question is not slow
    rag.get_corpus()                          # builds the BM25 index (about a second)
    if rag.RETRIEVAL_MODE == "hybrid_rerank":
        from reranker import score_pairs
        score_pairs("warm up", ["warm up"])   # loads the reranker model now (other modes load it on first use)
    # building the client does not need a key, so check for one separately and give a clear message later
    app.state.client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
    if app.state.client is None:
        log.warning("ANTHROPIC_API_KEY is not set: /ask will return 503 until it is")
    yield


app = FastAPI(title="GitLab docs assistant", version="0.1", lifespan=lifespan)


def get_client(request: Request):
    """A 'dependency': FastAPI calls this before /ask. Tests replace it with a fake (app.dependency_overrides)."""
    client = request.app.state.client
    if client is None:
        raise HTTPException(503, "The server has no ANTHROPIC_API_KEY. Set it and restart.")
    return client


def status_of(r: dict) -> str:
    if r["refused"]:
        return "refused"
    if r["clarifying"]:
        return "clarifying"
    return "uncited" if r["uncited"] else "answered"


# --------------------------------------------------------------------------- routes
# A plain `def` (not `async def`) on purpose: search and the LLM call are blocking, and FastAPI runs plain `def`
# routes in a thread pool, so one slow question does not freeze every other request.
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, client=Depends(get_client)):
    mode = req.mode or rag.RETRIEVAL_MODE
    t0 = time.perf_counter()
    chunks = rag.search(req.question, k=req.k, mode=mode)
    t1 = time.perf_counter()
    try:
        r = rag.answer(req.question, chunks, client=client)
    except anthropic.RateLimitError:
        raise HTTPException(429, "The language model is rate-limiting us. Try again in a moment.")
    except anthropic.APIError as e:                           # bad key, overloaded, network down, ...
        log.error("LLM call failed: %s %s", type(e).__name__, e)
        raise HTTPException(502, f"The language model call failed ({type(e).__name__}).")
    t2 = time.perf_counter()

    status = status_of(r)
    log.info("ask mode=%s status=%s search=%dms llm=%dms q=%r", mode, status, (t1 - t0) * 1000, (t2 - t1) * 1000,
             req.question)
    return AskResponse(
        question=r["question"], mode=mode, answer=r["answer"], status=status,
        citations=r["citations"], invalid_citations=r["invalid_citations"],
        retrieved=[Retrieved(**{k: c[k] for k in ("rank", "id", "title", "section", "url", "distance", "bm25", "rrf",
                                                    "rerank_score")},
                             text=c["text"] if req.debug else None) for c in chunks],
        usage=r["usage"],
        timing_ms={"search": round((t1 - t0) * 1000), "llm": round((t2 - t1) * 1000)},
    )


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "chunks": rag.get_collection().count(), "llm_model": rag.LLM_MODEL,
            "default_mode": rag.RETRIEVAL_MODE,
            "api_key_set": request.app.state.client is not None}
