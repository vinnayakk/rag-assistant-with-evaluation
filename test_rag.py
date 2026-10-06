"""Tests for rag.py that need NO API key and NO model download.
  - search() is tested with a real vector taken from your own database (a chunk used as its own query)
  - answer() is tested through the real Anthropic SDK talking to a fake local server
Run:  RAG_DB=outputs/chroma_db python test_rag.py
"""
import json, numpy as np, anthropic
try:
    import httpx2 as httpx          # newer anthropic SDKs use httpx2
except ImportError:
    import httpx
import rag

# ---------------------------------------------------------------- search()
col = rag.get_collection()
probe = col.get(where={"source": "administration_gitaly_cgroups"}, include=["embeddings", "metadatas"])
target_id = probe["ids"][0]
rag.embed_query = lambda q: np.array(probe["embeddings"][0])      # pretend the question embeds to this chunk

hits = rag.search("anything", k=5)
assert len(hits) == 5 and hits[0]["id"] == target_id and hits[0]["distance"] < 1e-4, hits[0]
assert all(h["rank"] == i + 1 for i, h in enumerate(hits))
assert [h["distance"] for h in hits] == sorted(h["distance"] for h in hits)
assert {"text", "title", "section", "url"} <= set(hits[0])
print(f"search ok: top hit is the chunk itself, distance {hits[0]['distance']:.5f}; "
      f"neighbours from: {sorted({h['title'] for h in hits})}")
only = rag.search("anything", k=3, where={"source": "user_version"})
assert only and all("version" in h["url"] for h in only)
print("search ok: metadata filter works ->", only[0]["url"])

# ---------------------------------------------------------------- answer() through the real SDK
def fake_client(reply_text):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": reply_text}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1500, "output_tokens": 60}})
    c = anthropic.Anthropic(api_key="test", max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return c, calls

chunks = rag.search("anything", k=4)

c, calls = fake_client("Gitaly memory is limited with `memory_bytes` [1]. It applies to all Git processes [2][3].")
r = rag.answer("How do I limit memory?", chunks, client=c)
body = calls[0]
assert body["model"] == rag.LLM_MODEL and body["max_tokens"] == 700 and body["system"].startswith("You answer")
assert '<source id="1"' in body["messages"][0]["content"] and "<question>How do I limit memory?</question>" in body["messages"][0]["content"]
assert [x["n"] for x in r["citations"]] == [1, 2, 3] and not r["invalid_citations"] and not r["uncited"] and not r["refused"]
print("answer ok: prompt is built correctly; citations 1,2,3 resolved to", r["citations"][0]["url"])

r = rag.answer("q", chunks, client=fake_client("Set it in the config [1, 3] and restart [9].")[0])
assert [x["n"] for x in r["citations"]] == [1, 3] and r["invalid_citations"] == [9]
print("answer ok: '[1, 3]' form parsed; invented source [9] flagged")

r = rag.answer("q", chunks, client=fake_client(rag.NOT_FOUND)[0])
assert r["refused"] and not r["uncited"] and r["citations"] == []
print("answer ok: refusal recognised, not flagged as uncited")

r = rag.answer("q", chunks, client=fake_client("You just run the command.")[0])
assert r["uncited"]
print("answer ok: answer without citations flagged as untrustworthy")


r = rag.answer("q", chunks, client=fake_client(rag.NOT_FOUND + " But see [2] for security findings.")[0])
assert r["refused"] and r["citations"] == [] and not r["uncited"]
print("answer ok: refusal with extra text keeps no citations")

r = rag.answer("how do I fix it", chunks, client=fake_client("Which feature or error are you asking about?")[0])
assert r["clarifying"] and not r["uncited"] and not r["refused"]
print("answer ok: clarifying question is recognised, not flagged as uncited")

r = rag.answer("q", chunks, client=fake_client("Sorry. " + rag.NOT_FOUND)[0])
assert not r["refused"]
print("answer ok: a refusal that does not START the answer is not treated as one")

print("\n" + rag.format_result(rag.answer("q", chunks, client=fake_client("Use cgroups [1]. Also [7].")[0])))
print("\nALL TESTS PASSED")
