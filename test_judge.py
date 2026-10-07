import json
import anthropic
try:
    import httpx2 as httpx_for_llm                                  # newer anthropic SDKs use httpx2
except ImportError:
    import httpx as httpx_for_llm

import judge, rag


def fake_client(reply, stop_reason="end_turn"):
    """A real anthropic client whose HTTP calls go to a fake. `reply` is a dict (sent as JSON) or a string. -> (client, requests)"""
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx_for_llm.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": stop_reason,
            "stop_sequence": None, "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 3000, "output_tokens": 300}})
    client = anthropic.Anthropic(api_key="t", max_retries=0,
                                 http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))
    return client, calls


CHUNKS = [
    {"title": "Gitaly cgroups", "section": "Introduction", "url": "https://docs.gitlab.com/a/",
     "text": "Gitaly cgroups\n\nSet `memory_bytes` in gitlab.rb. The default is 5 seconds. You don’t need **root** access."},
    {"title": "Other page", "section": "Intro", "url": "https://docs.gitlab.com/b/", "text": "Epsilon zeta eta theta iota."},
]


def claim(text, verdict="supported", source=1, quote="", note=""):
    return {"claim": text, "source": source, "quote": quote, "verdict": verdict, "note": note}


# --- quote_in: is the judge's 'copied' text really in the source?
assert judge.quote_in("memory_bytes", CHUNKS[0]["text"])
assert judge.quote_in("MEMORY_BYTES in gitlab.rb", CHUNKS[0]["text"])                 # case and backticks do not matter
assert judge.quote_in("You don't need root access", CHUNKS[0]["text"])                  # curly quote and **bold** do not matter
assert judge.quote_in("Set ... gitlab.rb", CHUNKS[0]["text"])                           # ... skips words
assert not judge.quote_in("Set ... nowhere", CHUNKS[0]["text"])                         # every piece must be there
assert not judge.quote_in("the default is 9 seconds", CHUNKS[0]["text"])                # a changed number is not a quote
assert not judge.quote_in("the", "the the the")                                         # too short to prove anything
assert not judge.quote_in("", CHUNKS[0]["text"])
print("ok  quote_in")

# --- check_quotes: the judge cannot vouch for itself
got = judge.check_quotes([
    claim("default is 5 s", quote="The default is 5 seconds"),                          # fine
    claim("same, wrong source number", source=2, quote="The default is 5 seconds"),     # real quote, wrong number: corrected
    claim("invented quote", quote="The default is 9 seconds"),                          # not in any source: downgraded
    claim("no quote at all", quote=""),                                                 # 'supported' without evidence: downgraded
    claim("not in sources", verdict="unsupported", source=0, quote="", note="not stated"),
    claim("different value", verdict="contradicted", quote="The default is 5 seconds", note="source says 5"),
], CHUNKS)
assert [c["verdict"] for c in got] == ["supported", "supported", "unsupported", "unsupported", "unsupported", "contradicted"], got
assert got[1]["source"] == 1 and got[1]["quote_found"] and not got[1]["downgraded"]
assert got[2]["downgraded"] and "not in the sources" in got[2]["note"]
assert got[3]["downgraded"] and "no quote" in got[3]["note"]
assert not got[4]["downgraded"] and got[4]["quote_found"] is None
assert got[5]["verdict"] == "contradicted" and got[5]["quote_found"]
print("ok  check_quotes: invented quote and missing quote are downgraded, wrong source number is corrected")

# --- summarise
s = judge.summarise(got)
assert s["verdict"] == "unfaithful" and s["n_claims"] == 6 and s["n_supported"] == 2 and s["n_contradicted"] == 1
assert abs(s["score"] - 2 / 6) < 1e-9
assert judge.summarise([])["verdict"] == "no_claims" and judge.summarise([])["score"] is None
ok = judge.summarise(judge.check_quotes([claim("a", quote="memory_bytes in gitlab.rb")], CHUNKS))
assert ok["verdict"] == "faithful" and ok["score"] == 1.0
print("ok  summarise: faithful only when every claim is supported")


# --- the schema follows the API's rules: every object closed, every property required
def walk(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, node
            assert set(node["required"]) == set(node["properties"]), node
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
walk(judge.SCHEMA)
assert judge.SCHEMA["properties"]["claims"]["items"]["properties"]["verdict"]["enum"] == judge.VERDICTS
print("ok  schema: additionalProperties false and all properties required, as structured outputs demand")

# --- judge_answer: the request that goes out, and the reading of the reply
reply = {"claims": [claim("Set memory_bytes in gitlab.rb", quote="Set `memory_bytes` in gitlab.rb"),
                    claim("The default is 5 seconds", quote="The default is 5 seconds"),
                    claim("It uses 9 cgroups", verdict="unsupported", source=0, note="not stated")]}
client, calls = fake_client(reply)
r = judge.judge_answer("How do I limit memory?", CHUNKS, "Set memory_bytes [1]. Default 5 seconds [1]. It uses 9 cgroups [1].", client)
assert r["verdict"] == "unfaithful" and r["n_supported"] == 2 and r["n_claims"] == 3 and abs(r["score"] - 2 / 3) < 1e-9
assert r["usage"] == {"input_tokens": 3000, "output_tokens": 300} and r["model"] == judge.JUDGE_MODEL
body = calls[0]
assert body["model"] == judge.JUDGE_MODEL and body["system"] == judge.JUDGE_SYSTEM
assert body["output_config"]["format"]["type"] == "json_schema" and body["output_config"]["format"]["schema"] == judge.SCHEMA
assert "tools" not in body and "tool_choice" not in body and "temperature" not in body        # Sonnet 5.5 cannot be forced to call a tool
msg = body["messages"][0]["content"]
assert '<source id="1"' in msg and '<source id="2"' in msg and "<question>How do I limit memory?</question>" in msg
assert msg.rstrip().endswith("It uses 9 cgroups [1].\n</answer>") and "memory_bytes" in msg      # the judge sees the sources and the answer
assert judge.judge_answer("q", CHUNKS, "a", client, model="my-judge")["model"] == "my-judge" and calls[-1]["model"] == "my-judge"
assert judge.JUDGE_MODEL != rag.LLM_MODEL, "the judge should not be the model that writes the answers"
print("ok  judge_answer: sends the sources and the answer with a JSON schema, reads claims, applies the quote check")

# --- an answer with nothing to check, and a fully backed one
assert judge.judge_answer("q", CHUNKS, "a", fake_client({"claims": []})[0])["verdict"] == "no_claims"
assert judge.judge_answer("q", CHUNKS, "a", fake_client({"claims": [claim("x", quote="memory_bytes in gitlab.rb")]})[0])["verdict"] == "faithful"

# --- a judge that fails must not look like a verdict
for bad, why in [(reply, "max_tokens"), (reply, "refusal"), ("this is not json", "end_turn"), ({"nothing": 1}, "end_turn")]:
    try:
        judge.judge_answer("q", CHUNKS, "a", fake_client(bad, stop_reason=why)[0])
        raise AssertionError(f"should have raised for {why} / {bad!r}")
    except judge.JudgeError:
        pass
print("ok  cut-off, refused, non-JSON and wrong-shape replies raise JudgeError (a failure, not 'unfaithful')")
print("all judge tests passed")
