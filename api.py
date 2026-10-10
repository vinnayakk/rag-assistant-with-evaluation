import logging, os, time
from contextlib import asynccontextmanager
from typing import Literal, Optional

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

import dashboard, metrics, rag, tracing

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
    tracing.init()                            # Langfuse tracing: on only when its keys are set (see tracing.py)
    yield
    tracing.shutdown()                        # send the traces that are still waiting in the background queue


app = FastAPI(title="GitLab docs assistant", version="0.1", lifespan=lifespan)
app.include_router(dashboard.router)      # GET /dashboard and GET /stats: average latency and cost from the request log


def get_client(request: Request):
    """A 'dependency': FastAPI calls this before /ask. Tests replace it with a fake (app.dependency_overrides)."""
    client = request.app.state.client
    if client is None:
        raise HTTPException(503, "The server has no ANTHROPIC_API_KEY. Set it and restart.")
    return client


def trace_hit(c: dict) -> dict:
    """One search hit as the Langfuse trace shows it: where it ranked and the scores that put it there. A score is None when
    that kind of search did not return the chunk (vector: distance; bm25: bm25; hybrid: all three, rrf is the fused score;
    hybrid_rerank adds rerank_score), so in hybrid mode a None tells you which of the two searches missed it."""
    return {**{k: c[k] for k in ("rank", "title", "section", "url")},
            **{k: None if c[k] is None else round(float(c[k]), 4) for k in ("distance", "bm25", "rrf", "rerank_score")}}


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
    t1 = t2 = None                                            # when search finished, when the model call finished
    # what goes into the request log (metrics.py). It starts as a failure and is filled in as the request succeeds, so
    # exactly one line is written per request even if something raises half way.
    rec = {"question": req.question, "mode": mode, "k": req.k, "model": rag.LLM_MODEL, "status": "error", "trace_id": None}
    try:
        with tracing.trace("ask", input={"question": req.question, "mode": mode, "k": req.k}, mode=mode) as tr:
            rec["trace_id"] = tr.id
            with tr.step("search", "retriever", input=req.question, metadata={"k": req.k}) as step:
                chunks = rag.search(req.question, k=req.k, mode=mode)
                step.update(output=[trace_hit(c) for c in chunks])
            t1 = time.perf_counter()
            # the generation shows in Langfuse exactly what the model was given and what it answered
            prompt = [{"role": "system", "content": rag.SYSTEM_PROMPT},
                      {"role": "user", "content": rag.build_user_message(req.question, chunks)}]
            with tr.generation("llm", rag.LLM_MODEL, input=prompt) as gen:
                r = rag.answer(req.question, chunks, client=client)
                n_in, n_out = r["usage"]["input_tokens"], r["usage"]["output_tokens"]
                gen.update(output=r["answer"], usage_details={"input": n_in, "output": n_out},
                           cost_details=metrics.cost_parts(rag.LLM_MODEL, n_in, n_out))      # None: Langfuse works it out
            t2 = time.perf_counter()
            status = status_of(r)
            tr.update(output={"answer": r["answer"], "status": status})
            rec.update(status=status, input_tokens=n_in, output_tokens=n_out,
                       cost_usd=metrics.cost_usd(rag.LLM_MODEL, n_in, n_out))
    except anthropic.RateLimitError as e:
        rec["error"] = type(e).__name__
        raise HTTPException(429, "The language model is rate-limiting us. Try again in a moment.")
    except anthropic.APIError as e:                           # bad key, overloaded, network down, ...
        rec["error"] = type(e).__name__
        log.error("LLM call failed: %s %s", type(e).__name__, e)
        raise HTTPException(502, f"The language model call failed ({type(e).__name__}).")
    finally:
        def ms(a, b):
            return None if b is None else round((b - a) * 1000)
        metrics.log_request(**rec, search_ms=ms(t0, t1), llm_ms=ms(t1, t2), total_ms=ms(t0, time.perf_counter()))

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
            "api_key_set": request.app.state.client is not None, "tracing": tracing.enabled()}
