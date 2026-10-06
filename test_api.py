"""Tests for api.py. They need NO API key, NO internet and NO model download.
  - the HTTP layer is FastAPI's TestClient (it calls the app directly, no server needed)
  - the language model is a fake local server (same trick as test_rag.py)
  - the question embedding is a stored vector from your own database

Run:   pip install httpx pytest      (TestClient needs httpx)
       RAG_DB=outputs/chroma_db python test_api.py
"""
import json, os
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")            # so start-up builds a client (never used for real)
import numpy as np, anthropic
try:
    import httpx2 as httpx_for_llm                                  # newer anthropic SDKs use httpx2
except ImportError:
    import httpx as httpx_for_llm
from fastapi.testclient import TestClient

import rag, api

# pretend every question embeds to one real chunk from the database
probe = rag.get_collection().get(where={"source": "administration_gitaly_cgroups"}, include=["embeddings"])
rag.embed_query = lambda q: np.array(probe["embeddings"][0])


def fake_llm(reply_text=None, status=200):
    """A real anthropic client whose HTTP calls go to a fake. Returns (client, list of request bodies)."""
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if status != 200:
            return httpx_for_llm.Response(status, json={"type": "error", "error": {"type": "x", "message": "boom"}})
        return httpx_for_llm.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn",
            "stop_sequence": None, "content": [{"type": "text", "text": reply_text}],
            "usage": {"input_tokens": 1200, "output_tokens": 40}})
    client = anthropic.Anthropic(api_key="t", max_retries=0,
                                 http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))
    return client, calls


def use(client):
    api.app.dependency_overrides[api.get_client] = lambda: client      # swap the real client for the fake one


with TestClient(api.app) as http:                                      # `with` makes FastAPI run start-up
    # ---- /health
    h = http.get("/health").json()
    assert h["status"] == "ok" and h["chunks"] > 100 and h["llm_model"] == rag.LLM_MODEL
    print("ok  /health:", h)

    # ---- a normal answer
    c, calls = fake_llm("Set `memory_bytes` in gitlab.rb [1]. It covers all Git processes [2].")
    use(c)
    r = http.post("/ask", json={"question": "How do I limit memory for Gitaly?"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "answered" and [x["n"] for x in j["citations"]] == [1, 2] and j["invalid_citations"] == []
    assert len(j["retrieved"]) == 5 and all(x["text"] is None for x in j["retrieved"])
    assert j["retrieved"][0]["distance"] < 1e-4 and j["usage"]["input_tokens"] == 1200 and "search" in j["timing_ms"]
    assert "<question>How do I limit memory for Gitaly?</question>" in calls[0]["messages"][0]["content"]
    print("ok  /ask answered: 2 citations, 5 retrieved chunks, timing + token usage returned")

    # ---- k and debug are passed through
    r = http.post("/ask", json={"question": "anything", "k": 3, "debug": True}).json()
    assert len(r["retrieved"]) == 3 and all(x["text"] for x in r["retrieved"])
    assert calls[-1]["messages"][0]["content"].count("<source id=") == 3
    print("ok  k=3 retrieves 3 chunks and sends 3 to the model; debug=true returns chunk text")

    # ---- the four kinds of reply
    for text, want in [(rag.NOT_FOUND, "refused"),
                       ("Which part of GitLab do you mean?", "clarifying"),
                       ("It just works, trust me.", "uncited")]:
        use(fake_llm(text)[0])
        j = http.post("/ask", json={"question": "some question"}).json()
        assert j["status"] == want, (want, j["status"])
        if want == "refused":
            assert j["citations"] == []
    print("ok  status is refused / clarifying / uncited when it should be")

    use(fake_llm("It is in the config [1] and also here [9].")[0])
    j = http.post("/ask", json={"question": "some question"}).json()
    assert j["status"] == "answered" and j["invalid_citations"] == [9] and [x["n"] for x in j["citations"]] == [1]
    print("ok  an invented citation [9] is reported in invalid_citations")

    # ---- bad requests are rejected before any work is done
    use(fake_llm("x [1]")[0])
    for bad in [{}, {"question": ""}, {"question": "   "}, {"question": "ab"}, {"question": "x" * 501},
                {"question": "fine question", "k": 0}, {"question": "fine question", "k": 11}]:
        assert http.post("/ask", json=bad).status_code == 422, bad
    print("ok  empty / too short / too long question and k outside 1-10 give 422")

    # ---- problems on the model side become clear HTTP errors
    for status, want in [(401, 502), (500, 502), (429, 429)]:
        use(fake_llm(status=status)[0])
        r = http.post("/ask", json={"question": "some question"})
        assert r.status_code == want, (status, r.status_code)
    assert "boom" not in r.text
    print("ok  model errors: 401 and 500 -> 502, rate limit 429 -> 429 (details stay in the server log)")

    # ---- no API key on the server
    api.app.dependency_overrides.clear()
    saved, api.app.state.client = api.app.state.client, None
    r = http.post("/ask", json={"question": "some question"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert http.get("/health").json()["api_key_set"] is False
    api.app.state.client = saved
    print("ok  no key -> 503 with a clear message; /health shows api_key_set=false")

print("\nAll API tests passed.")
