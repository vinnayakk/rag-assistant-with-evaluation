import base64, gzip, http.server as http_server, json, logging, os, pathlib, ssl, subprocess, tempfile, threading, time
for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LANGFUSE_HOST", "RAG_TRACING"):
    os.environ.pop(k, None)                                        # these tests decide for themselves whether tracing is on
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ["FAKE_RERANK"] = "1"
TMP = pathlib.Path(tempfile.mkdtemp())
os.environ["RAG_REQUEST_LOG"] = str(TMP / "requests.jsonl")

import numpy as np, anthropic
try:
    import httpx2 as httpx_for_llm
except ImportError:
    import httpx as httpx_for_llm
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api, dashboard, metrics, rag, tracing


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


# ================================================================ A. cost, the log file, the averages
assert close(metrics.cost_usd("claude-haiku-4-5-20251001", 1200, 40), 0.0014)          # 1200 x $1/M + 40 x $5/M
assert close(metrics.cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000), 6.0)
assert close(metrics.cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000), 12.0)
assert metrics.cost_usd("some-new-model", 100, 100) is None and metrics.cost_usd("claude-haiku-4-5", None, 5) is None
parts = metrics.cost_parts("claude-haiku-4-5-20251001", 1200, 40)
assert close(parts["input"], 0.0012) and close(parts["output"], 0.0002) and close(parts["total"], 0.0014)
assert metrics.cost_parts("some-new-model", 1, 1) is None
print("ok  cost: Haiku 1200 in + 40 out = $0.0014, dated model ids match, an unknown model gives None (not $0)")

p = TMP / "a.jsonl"
assert metrics.read_log(p) == ([], 0)
r1 = metrics.log_request(p, question="q1", mode="vector", status="answered", total_ms=10)
p.write_text(p.read_text() + "this line is not json\n\n[1, 2]\n")
metrics.log_request(p, question="q2 é中", mode="hybrid", status="refused", total_ms=20)
recs, bad = metrics.read_log(p)
assert [r["question"] for r in recs] == ["q1", "q2 é中"] and bad == 2 and recs[0]["id"] == r1["id"] and "ts" in recs[0]
print("ok  log: lines round-trip (non-ASCII too); unreadable lines are skipped and counted")

p2 = TMP / "threads.jsonl"
def writer(n):
    for i in range(50):
        metrics.log_request(p2, question=f"t{n}-{i}", mode="vector", status="answered", total_ms=1, pad="x" * 3000)
ts = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
recs, bad = metrics.read_log(p2)
assert len(recs) == 400 and bad == 0 and len({r["id"] for r in recs}) == 400
print("ok  log: 8 threads x 50 writes of 3 KB lines -> 400 intact lines")

assert metrics.log_request("/dev/null/cannot/write.jsonl", question="x")["question"] == "x"     # must not raise
print("ok  log: an unwritable path does not raise (a full disk must not break /ask)")

assert metrics.percentile(list(range(1, 21)), 95) == 19 and metrics.percentile([7], 95) == 7 and metrics.percentile([], 95) is None
assert metrics.percentile([5, 1, 3], 50) == 3
rows = [dict(mode="vector", status="answered", total_ms=1000, search_ms=100, llm_ms=900, cost_usd=0.001, input_tokens=1000, output_tokens=50),
        dict(mode="vector", status="refused", total_ms=3000, search_ms=300, llm_ms=2700, cost_usd=0.003, input_tokens=3000, output_tokens=30),
        dict(mode="hybrid", status="error", total_ms=9000, search_ms=200, error="RateLimitError"),                 # no cost, no llm time
        dict(mode="hybrid", status="answered", total_ms=2000, search_ms=200, llm_ms=1800, input_tokens=10, output_tokens=10)]  # no price
s = metrics.summarise(rows)
assert s["requests"] == 4 and s["errors"] == 1 and s["statuses"] == {"answered": 2, "refused": 1, "error": 1}
assert close(s["latency_ms"]["mean"], 2000) and s["latency_ms"]["median"] == 2000 and s["latency_ms"]["p95"] == 3000   # the 9000 error is left out
assert close(s["latency_ms"]["search_mean"], 200) and close(s["latency_ms"]["llm_mean"], 1800)
assert close(s["cost_usd"]["mean"], 0.002) and close(s["cost_usd"]["total"], 0.004) and close(s["cost_usd"]["per_1000"], 2.0)
assert s["cost_usd"]["unpriced"] == 1
bm = metrics.summarise_by_mode(rows)
assert list(bm) == ["vector", "hybrid"] or list(bm) == ["hybrid", "vector"]
assert bm["vector"]["requests"] == 2 and close(bm["vector"]["latency_ms"]["mean"], 2000) and bm["hybrid"]["errors"] == 1
e = metrics.summarise([])
assert e["requests"] == 0 and e["latency_ms"]["mean"] is None and e["cost_usd"]["total"] is None and e["cost_usd"]["per_1000"] is None
assert [r["total_ms"] for r in metrics.select(rows, last=2)] == [9000, 2000] and len(metrics.select(rows, mode="vector")) == 2
print("ok  averages: errors are left out of latency and cost, unpriced requests are counted not zeroed, empty log gives None")


# ================================================================ B. the dashboard page and /stats on their own
metrics_app = FastAPI()
metrics_app.include_router(dashboard.router)
page_log = TMP / "page.jsonl"
os.environ["RAG_REQUEST_LOG"] = str(page_log)
with TestClient(metrics_app) as web:
    r = web.get("/dashboard")
    assert r.status_code == 200 and "No requests" in r.text and "curl" in r.text
    assert web.get("/stats").json()["overall"]["requests"] == 0
    for row in rows[:2] + [rows[3]]:
        metrics.log_request(page_log, question="<script>alert(1)</script> & \"hi\"", ts_note="x", **row)
    metrics.log_request(page_log, question="boom", **rows[2])
    r = web.get("/dashboard")
    assert r.status_code == 200 and "Average latency" in r.text and "Average cost per request" in r.text
    assert "<script>alert(1)" not in r.text and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text, "a question must be escaped"
    assert "hybrid" in r.text and "vector" in r.text and "<svg" in r.text
    j = web.get("/stats").json()
    assert j["overall"]["requests"] == 4 and j["overall"]["errors"] == 1 and close(j["overall"]["latency_ms"]["mean"], 2000)
    assert set(j["by_mode"]) == {"vector", "hybrid"}
    j = web.get("/stats?mode=vector").json()
    assert j["overall"]["requests"] == 2 and list(j["by_mode"]) == ["vector"]
    assert web.get("/stats?last=1").json()["overall"]["requests"] == 1
    assert web.get("/stats?last=0").status_code == 422
    assert web.get("/dashboard?mode=nonsense").status_code == 200 and "No requests with search mode nonsense" in web.get("/dashboard?mode=nonsense").text
    assert "&lt;img" in web.get("/dashboard?mode=%3Cimg%20src=x%3E").text and "<img src=x>" not in web.get("/dashboard?mode=%3Cimg%20src=x%3E").text
    err_log = TMP / "onlyerrors.jsonl"
    os.environ["RAG_REQUEST_LOG"] = str(err_log)
    metrics.log_request(err_log, question="x", mode="vector", status="error", total_ms=5000)
    r = web.get("/dashboard")
    assert r.status_code == 200 and "No request has had a model reply yet" in r.text
os.environ["RAG_REQUEST_LOG"] = str(TMP / "requests.jsonl")
print("ok  dashboard: renders empty / filled / filtered / all-errors logs; questions and filter values are HTML-escaped; /stats agrees")


# ================================================================ C. the real app: one log line per /ask, tracing off
probe = rag.get_collection().get(where={"source": "administration_gitaly_cgroups"}, include=["embeddings"])
rag.embed_query = lambda q: np.array(probe["embeddings"][0])


def fake_llm(reply_text="Set `memory_bytes` in gitlab.rb [1].", status=200):
    def handler(request):
        body = json.loads(request.content)
        if status != 200:
            return httpx_for_llm.Response(status, json={"type": "error", "error": {"type": "x", "message": "boom"}})
        return httpx_for_llm.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn",
            "stop_sequence": None, "content": [{"type": "text", "text": reply_text}],
            "usage": {"input_tokens": 1200, "output_tokens": 40}})
    return anthropic.Anthropic(api_key="t", max_retries=0, http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))


def use(client):
    api.app.dependency_overrides[api.get_client] = lambda: client


log_file = pathlib.Path(os.environ["RAG_REQUEST_LOG"])
with TestClient(api.app) as http:
    assert http.get("/health").json()["tracing"] is False
    use(fake_llm("Set `memory_bytes` in gitlab.rb [1]."))
    assert http.post("/ask", json={"question": "How do I limit memory for Gitaly?", "mode": "hybrid"}).status_code == 200
    use(fake_llm("I couldn't find this in the GitLab documentation I have."))
    assert http.post("/ask", json={"question": "What is the stock price?"}).status_code == 200
    use(fake_llm(status=500))
    assert http.post("/ask", json={"question": "this one fails"}).status_code == 502
    use(fake_llm(status=429))
    assert http.post("/ask", json={"question": "this one is rate limited"}).status_code == 429
    http.post("/ask", json={"question": "x"})                                          # too short: rejected before the handler
    recs, bad = metrics.read_log(log_file)
    assert len(recs) == 4 and bad == 0, f"expected 4 lines, got {len(recs)}"
    a, b, c, d = recs
    assert (a["status"], a["mode"], a["model"], a["input_tokens"], a["output_tokens"]) == ("answered", "hybrid", rag.LLM_MODEL, 1200, 40)
    assert close(a["cost_usd"], 0.0014) and a["trace_id"] is None and a["k"] == 5 and a["question"].startswith("How do I limit")
    assert a["search_ms"] is not None and a["llm_ms"] is not None and a["search_ms"] + a["llm_ms"] <= a["total_ms"] + 1
    assert 0 <= a["total_ms"] < 20_000
    assert b["status"] == "refused" and close(b["cost_usd"], 0.0014)                  # a refusal still costs tokens
    assert c["status"] == "error" and c["error"] == "InternalServerError" and "cost_usd" not in c and c["search_ms"] is not None and c["llm_ms"] is None
    assert d["status"] == "error" and d["error"] == "RateLimitError"
    s = http.get("/stats").json()["overall"]
    assert s["requests"] == 4 and s["errors"] == 2 and close(s["cost_usd"]["total"], 0.0028) and close(s["cost_usd"]["mean"], 0.0014)
    page = http.get("/dashboard")
    assert page.status_code == 200 and "$0.0014" in page.text and "refused" in page.text
print("ok  /ask: exactly one log line per request (answered, refused, model error, rate limit); too-short question is not logged;")
print("    tokens, cost ($0.0014), search/model/total ms are right; /stats and /dashboard on the real app agree")


# ================================================================ D. tracing is a no-op without keys
assert tracing.init() is False and tracing.enabled() is False
with tracing.trace("ask", input={"q": 1}, mode="vector") as t:
    assert t.id is None
    with t.step("search", "retriever", input="q") as s_:
        s_.update(output=[1])
    with t.generation("llm", "claude-haiku-4-5", input=[]) as g_:
        g_.update(output="x", usage_details={"input": 1, "output": 1}, cost_details=None)
    t.update(output={"a": 1})
tracing.shutdown()
os.environ.update(LANGFUSE_PUBLIC_KEY="pk-lf-x", LANGFUSE_SECRET_KEY="sk-lf-x", RAG_TRACING="0")
assert tracing.init() is False                                                         # keys present, but switched off
os.environ.pop("RAG_TRACING")
for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ.pop(k)
print("ok  tracing off: no keys or RAG_TRACING=0 -> every call is a harmless no-op")


# ================================================================ E. tracing on, against a stand-in Langfuse
try:
    import langfuse                                                                    # noqa: F401
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
except ImportError as exc:
    print(f"skip  tracing on: needs the langfuse package ({exc}); run: pip install langfuse \"opentelemetry-exporter-otlp-proto-http==1.45.0\"")
    print("\nAll observability tests passed (tracing-on part skipped).")
    raise SystemExit(0)

captured = []


class StandIn(http_server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, body, ctype):
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        captured.append(("GET", self.path, {k.lower(): v for k, v in self.headers.items()}, b""))
        self._reply(json.dumps({"data": [{"id": "p1", "name": "demo", "organization": {"id": "o1", "name": "org"}, "metadata": {}}]}).encode(),
                    "application/json")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        captured.append(("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        self._reply(b"", "application/x-protobuf")


server = http_server.ThreadingHTTPServer(("127.0.0.1", 0), StandIn)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ.update(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test",
                  LANGFUSE_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}")
log_file.write_text("")
with TestClient(api.app) as http:                                                      # start-up calls tracing.init()
    assert tracing.enabled() and http.get("/health").json()["tracing"] is True
    use(fake_llm("Set `memory_bytes` in gitlab.rb [1]."))
    ok = http.post("/ask", json={"question": "How do I limit memory for Gitaly?", "mode": "hybrid"})
    assert ok.status_code == 200
    use(fake_llm(status=500))
    assert http.post("/ask", json={"question": "this one fails", "mode": "vector"}).status_code == 502
# leaving the `with` ran the app's shut-down, which flushes the queue to the stand-in


def val(v):
    kind = v.WhichOneof("value")
    if kind == "array_value":
        return [val(x) for x in v.array_value.values]
    return getattr(v, kind)


spans = []
for method, path, headers, body in captured:
    if method == "POST" and path == "/api/public/otel/v1/traces":
        assert headers["authorization"] == "Basic " + base64.b64encode(b"pk-lf-test:sk-lf-test").decode()
        req = ExportTraceServiceRequest()
        req.ParseFromString(gzip.decompress(body) if headers.get("content-encoding") == "gzip" else body)
        for rs in req.resource_spans:
            for ss in rs.scope_spans:
                for sp in ss.spans:
                    spans.append(dict(name=sp.name, trace=sp.trace_id.hex(), id=sp.span_id.hex(), parent=sp.parent_span_id.hex(),
                                      err=sp.status.code == 2, attrs={a.key: val(a.value) for a in sp.attributes}))
assert any(m == "GET" and p == "/api/public/projects" for m, p, _, _ in captured), "start-up should check the keys once"
assert sorted(s["name"] for s in spans) == ["ask", "ask", "llm", "llm", "search", "search"], [s["name"] for s in spans]

traces = {}
for s in spans:
    traces.setdefault(s["trace"], {})[s["name"]] = s
assert len(traces) == 2
good = next(t for t in traces.values() if not t["ask"]["err"])
bad = next(t for t in traces.values() if t["ask"]["err"])

root, search, llm = good["ask"], good["search"], good["llm"]
# FastAPI 0.14x makes its own OpenTelemetry spans, so `ask` has a parent that Langfuse does not export. The SDK marks it as the
# root of the trace for that reason (is_app_root); the two steps hang under it.
assert root["attrs"]["langfuse.internal.is_app_root"] is True
assert search["parent"] == root["id"] and llm["parent"] == root["id"]
assert root["attrs"]["langfuse.observation.type"] == "span" and search["attrs"]["langfuse.observation.type"] == "retriever"
assert llm["attrs"]["langfuse.observation.type"] == "generation"
assert root["attrs"]["langfuse.trace.name"] == "ask" and root["attrs"]["langfuse.trace.tags"] == ["hybrid"]
assert root["attrs"]["langfuse.trace.metadata.mode"] == "hybrid"
assert json.loads(root["attrs"]["langfuse.observation.input"]) == {"question": "How do I limit memory for Gitaly?", "mode": "hybrid", "k": 5}
assert json.loads(root["attrs"]["langfuse.observation.output"])["status"] == "answered"
out = json.loads(search["attrs"]["langfuse.observation.output"])
assert len(out) == 5 and out[0]["rank"] == 1
assert set(out[0]) == {"rank", "title", "section", "url", "distance", "bm25", "rrf", "rerank_score"}
# hybrid mode: every hit has the fused score, and each hit has at least one of the two searches' scores (None = that search missed it)
assert all(h["rrf"] is not None and (h["distance"] is not None or h["bm25"] is not None) for h in out), out
assert all(h["rerank_score"] is None for h in out)                                 # the reranker is not part of plain hybrid
assert any(h["distance"] is not None for h in out) and any(h["bm25"] is not None for h in out)
assert all(isinstance(h[k], (float, type(None))) for h in out for k in ("distance", "bm25", "rrf"))
# scores can arrive as numpy numbers (the reranker's are float32); the trace must hold plain, JSON-safe, rounded floats
h = api.trace_hit({"rank": 1, "title": "t", "section": "s", "url": "u", "distance": np.float32(0.123456), "bm25": None,
                   "rrf": np.float64(0.0312345), "rerank_score": np.float32(-4.5)})
assert json.dumps(h) and h["distance"] == 0.1235 and h["bm25"] is None and h["rrf"] == 0.0312 and h["rerank_score"] == -4.5, h
assert llm["attrs"]["langfuse.observation.model.name"] == rag.LLM_MODEL
assert json.loads(llm["attrs"]["langfuse.observation.usage_details"]) == {"input": 1200, "output": 40}
cd = json.loads(llm["attrs"]["langfuse.observation.cost_details"])
assert close(cd["total"], 0.0014) and close(cd["input"], 0.0012) and close(cd["output"], 0.0002)
prompt = json.loads(llm["attrs"]["langfuse.observation.input"])
assert prompt[0] == {"role": "system", "content": rag.SYSTEM_PROMPT}
assert "<question>How do I limit memory for Gitaly?</question>" in prompt[1]["content"] and prompt[1]["content"].count("<source id=") == 5
assert llm["attrs"]["langfuse.observation.output"] == "Set `memory_bytes` in gitlab.rb [1]."

assert bad["llm"]["err"] and bad["ask"]["err"] and not bad["search"]["err"], "a failed model call must show as an error in the trace"
assert bad["ask"]["attrs"]["langfuse.trace.tags"] == ["vector"]
vec = json.loads(bad["search"]["attrs"]["langfuse.observation.output"])             # vector mode: only the distance exists
assert len(vec) == 5 and all(h["distance"] is not None and h["bm25"] is None and h["rrf"] is None and h["rerank_score"] is None for h in vec)

recs, _ = metrics.read_log(log_file)
assert len(recs) == 2 and recs[0]["trace_id"] == root["trace"] and recs[1]["trace_id"] == bad["ask"]["trace"]
print("ok  tracing on: start-up checks the keys; each /ask is one trace = ask > search (retriever, 5 chunks) + llm (generation)")
print("    the generation carries model, exact prompt, answer, usage {input 1200, output 40} and cost $0.0014;")
print("    the trace is tagged with the search mode; a failed model call is an error span; the request log holds the trace id")


# ================================================================ F. the certificate problem on macOS, reproduced
def make_certs(d):
    """A throw-away CA, a server certificate for 127.0.0.1 signed by it, and a second CA that signed nothing. None if openssl fails."""
    def run(*args):
        subprocess.run(["openssl", *args], cwd=d, check=True, capture_output=True)
    try:
        for name in ("ca", "other"):
            run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key", "-out", f"{name}.pem", "-days", "2",
                "-subj", f"/CN=test {name} CA", "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-addext", "subjectKeyIdentifier=hash")
        run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "srv.key", "-out", "srv.csr", "-subj", "/CN=127.0.0.1")
        (d / "srv.ext").write_text("subjectAltName=IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                                   "extendedKeyUsage=serverAuth\nauthorityKeyIdentifier=keyid\n")
        run("x509", "-req", "-in", "srv.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial", "-out", "srv.pem", "-days", "2",
            "-extfile", "srv.ext")
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


certdir = TMP / "certs"
certdir.mkdir()
if not make_certs(certdir):
    print("skip  certificate problem: the openssl command could not make a test certificate")
else:
    tls_server = http_server.ThreadingHTTPServer(("127.0.0.1", 0), StandIn)
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_context.load_cert_chain(certdir / "srv.pem", certdir / "srv.key")
    tls_server.socket = tls_context.wrap_socket(tls_server.socket, server_side=True)
    threading.Thread(target=tls_server.serve_forever, daemon=True).start()
    url = f"https://127.0.0.1:{tls_server.server_address[1]}"
    ca, other = str(certdir / "ca.pem"), str(certdir / "other.pem")

    class Collect(logging.Handler):
        def __init__(self):
            super().__init__(); self.lines = []

        def emit(self, record):
            self.lines.append(f"{record.levelname}: {record.getMessage()}")

    def with_env(**env):
        """Set (or, for None, remove) environment variables for one call; returns the old values to restore."""
        old = {k: os.environ.get(k) for k in env}
        for k, v in env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        return old

    NONE = dict(OTEL_EXPORTER_OTLP_CERTIFICATE=None, OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE=None, SSL_CERT_FILE=None, SSL_CERT_DIR=None)
    restore = with_env(**NONE)
    try:
        # the probe on its own
        kind, why = tracing._tls_problem(url)
        assert kind == "cert" and ("issuer" in why or "self" in why), (kind, why)         # Python's own list does not know our CA
        with_env(OTEL_EXPORTER_OTLP_CERTIFICATE=ca)
        assert tracing._tls_problem(url) is None                                       # the fix from the README
        with_env(OTEL_EXPORTER_OTLP_CERTIFICATE=None, OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE=ca)
        assert tracing._tls_problem(url) is None                                       # the more specific variable works too
        with_env(OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE=None, OTEL_EXPORTER_OTLP_CERTIFICATE=other)
        assert tracing._tls_problem(url)[0] == "cert"                                  # a list that lacks the right CA
        with_env(OTEL_EXPORTER_OTLP_CERTIFICATE=str(certdir / "missing.pem"))
        assert tracing._tls_problem(url)[0] == "other"                                 # a typo in the path is not a "cert" problem
        with_env(OTEL_EXPORTER_OTLP_CERTIFICATE=ca)
        assert tracing._tls_problem("https://127.0.0.1:1")[0] == "other"               # nothing is listening
        assert tracing._tls_problem(f"http://127.0.0.1:{server.server_address[1]}") is None     # plain http: nothing to check

        # init() end to end: the SDK's own client trusts the CA through SSL_CERT_FILE (it passes the key check), the trace sender's
        # list lacks it: the two clients disagree, which is exactly the macOS case.
        handler, lines = Collect(), None
        tracing.log.addHandler(handler); tracing.log.setLevel(logging.INFO)
        os.environ.update(LANGFUSE_SECRET_KEY="sk-lf-tls", LANGFUSE_BASE_URL=url)

        starts = []

        def start(**env):
            # The SDK keeps one client per public key for the life of the process, so each start-up here uses its own key (a real
            # server calls init() once, so this only matters in a test).
            starts.append(1); os.environ["LANGFUSE_PUBLIC_KEY"] = f"pk-lf-tls{len(starts)}"
            with_env(**env); handler.lines.clear()
            assert tracing.init() is True and tracing.enabled()                          # tracing stays on in every case
            out = list(handler.lines); tracing.shutdown(); return out

        out = start(SSL_CERT_FILE=ca, OTEL_EXPORTER_OTLP_CERTIFICATE=other)
        assert len(out) == 1 and out[0].startswith("WARNING") and "traces will probably NOT arrive" in out[0], out
        assert "OTEL_EXPORTER_OTLP_CERTIFICATE" in out[0] and "connected to Langfuse" not in out[0]
        out = start(SSL_CERT_FILE=ca, OTEL_EXPORTER_OTLP_CERTIFICATE=ca)
        assert out == ["INFO: tracing is on: connected to Langfuse"], out                # both clients agree: say "connected"
        out = start(SSL_CERT_FILE=None, OTEL_EXPORTER_OTLP_CERTIFICATE=None)             # the SDK's own client fails first
        assert len(out) == 1 and "could not be reached" in out[0] and "connected to Langfuse" not in out[0], out
        tracing.log.removeHandler(handler)
    finally:
        with_env(**restore)
        for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
            os.environ.pop(k, None)
    print("ok  certificate problem: with a Python that cannot verify the certificate the start-up log says so and names the fix;")
    print("    OTEL_EXPORTER_OTLP_CERTIFICATE (or the TRACES one) clears it; a bad path, a closed port and plain http are handled")

print("\nAll observability tests passed.")
