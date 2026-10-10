import json, logging, os, pathlib, re, shutil, subprocess, sys, tempfile, threading, time, types
TMP = pathlib.Path(tempfile.mkdtemp())
os.environ["RAG_REQUEST_LOG"] = str(TMP / "requests.jsonl")        # test requests must not land in the real log
os.environ["FAKE_RERANK"] = "1"                                    # word-overlap stand-in for the reranker model
os.environ["ANTHROPIC_API_KEY"] = "test-key"
DB = str(pathlib.Path(os.environ.setdefault("RAG_DB", "outputs/chroma_db")).resolve())   # absolute: one test starts a child process in another folder
os.environ["RAG_DB"] = DB
for _k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):          # tracing must stay off
    os.environ.pop(_k, None)

import numpy as np, anthropic
try:
    import httpx2 as httpx_for_llm                                  # newer anthropic SDKs use httpx2
except ImportError:
    import httpx as httpx_for_llm
import streamlit as st
from streamlit.testing.v1 import AppTest

import api, app_backend, chat_text, embedder, guard, rag, reranker

HERE = pathlib.Path(__file__).resolve().parent
APP = str(HERE / "streamlit_app.py")


# ================================================================ A. the plain helpers
# ---- chat_text.link_citations
cites = [{"n": 1, "title": "T", "section": "S", "url": "https://docs.gitlab.com/a/"},
         {"n": 3, "title": "T", "section": "S", "url": "https://docs.gitlab.com/c_(x) y/"}]
lc = lambda t: chat_text.link_citations(t, cites)
assert lc("Do it [1].") == "Do it [[1]](https://docs.gitlab.com/a/)."
assert lc("Both [1][3].") == "Both [[1]](https://docs.gitlab.com/a/)[[3]](https://docs.gitlab.com/c_%28x%29%20y/)."
assert lc("Both [1, 3].") == "Both [[1]](https://docs.gitlab.com/a/), [[3]](https://docs.gitlab.com/c_%28x%29%20y/)."
assert lc("Invented [9].") == "Invented \\[9\\]." and "(" not in lc("Invented [9].")      # not linked, and not left as markdown
assert lc("Real [1] and invented [2, 9].") == ("Real [[1]](https://docs.gitlab.com/a/) and invented \\[2\\], \\[9\\].")
assert lc("Use `a[1]` here [1].") == "Use `a[1]` here [[1]](https://docs.gitlab.com/a/)."    # inside `code` nothing changes
assert lc("```\nx = a[1] + $HOME\n```\nthen [1]") == "```\nx = a[1] + $HOME\n```\nthen [[1]](https://docs.gitlab.com/a/)"
assert lc("It costs $5 and $10 [1].") == "It costs \\$5 and \\$10 [[1]](https://docs.gitlab.com/a/)."
assert lc("Already \\$5.") == "Already \\$5."                       # an escaped $ is not escaped twice
assert lc("`$CI_PROJECT_DIR` is set") == "`$CI_PROJECT_DIR` is set"
assert chat_text.link_citations("see [1]", [{"n": 1, "url": "javascript:alert(1)"}]) == "see \\[1\\]"   # only http(s) is linked
assert chat_text.link_citations("no citations", []) == "no citations"
# ---- md_text and safe_url
assert chat_text.md_text("Use [x] and *y* (z) $5 <b>") == "Use \\[x\\] and \\*y\\* \\(z\\) \\$5 \\<b\\>"
assert chat_text.safe_url("ftp://x") is None and chat_text.safe_url("/relative") is None
assert chat_text.safe_url("https://a/b (1)") == "https://a/b%20%281%29"
mb = chat_text.peak_memory_mb()
assert mb is None or 20 < mb < 100_000
# pictures and links to other sites: the model's own links stay only for GitLab's sites, and a link can never hide its address
assert lc("![x](https://evil.example/p.png?q=1) see") == "x see"
assert lc("[Official docs](https://evil.example/login) go") == "Official docs (`https://evil.example/login`) go"
assert lc("[ok](https://docs.gitlab.com/x/) end") == "[ok](https://docs.gitlab.com/x/) end"
assert lc("[a](http://docs.gitlab.com/x) [b](https://docs.gitlab.com.evil.example/x) [c](https://docs.gitlab.com@evil.example/x)").count("](") == 0
assert lc("[js](javascript:alert(1))").count("](") == 0 and lc("[bad](https://[::1/x)").count("](") == 0
assert lc("[a][r1]\n\n[r1]: https://evil.example/x\nend") == "[a][r1]\n\n\nend"                    # the other way to write a link
assert lc("`[x](https://evil.example)` and ``` [y](https://evil.example) ```") == "`[x](https://evil.example)` and ``` [y](https://evil.example) ```"
print("ok  chat_text: citations become links (only real ones, never inside code), $ stays a dollar sign, titles are escaped, pictures and foreign links are tamed")

# ---- chat_text.check_api_key / own_key_problem
for raw in ("", "   ", None, "hello", "sk-ant-", "sk-ant-short", "api03-" + "a" * 40, "sk-ant-api03-abc def-ghijklmnop", "sk-ant-api03-abc\ndef-ghijklmnop",
            "sk-ant-api03-é-ghijklmnopqrstuv", "x" * 400, "sk-ant-" + "a" * 400):
    key, problem = chat_text.check_api_key(raw)
    assert key is None and problem, raw
    assert len((raw or "").strip()) < 8 or raw.strip() not in problem        # what was typed is never repeated back (the hint itself says sk-ant-)
assert chat_text.check_api_key("  sk-ant-api03-abcdefghijklmnop  \n") == ("sk-ant-api03-abcdefghijklmnop", None)    # paste with a line break
assert chat_text.own_key_problem("AuthenticationError")[1] is True                  # only a refused key is forgotten
for name in ("PermissionDeniedError", "BadRequestError", "InternalServerError", "", "NotFoundError"):
    assert chat_text.own_key_problem(name)[1] is False and chat_text.own_key_problem(name)[0]
assert "credit" in chat_text.own_key_problem("BadRequestError")[0]
print("ok  chat_text: an API key is checked for shape only and never repeated back; only a refused key is forgotten")

# ---- guard.DailyCounter
day = [1]
dc = guard.DailyCounter(3, today=lambda: day[0])
assert [dc.take() for _ in range(5)] == [True, True, True, False, False] and dc.used() == 3
day[0] = 2
assert dc.used() == 0 and dc.take() and dc.used() == 1                # a new UTC day starts from zero
assert all(guard.DailyCounter(0).take() for _ in range(1000))         # 0 = no limit
many = guard.DailyCounter(100)
threads = [threading.Thread(target=lambda: [many.take() for _ in range(50)]) for _ in range(8)]
[t.start() for t in threads]; [t.join() for t in threads]
assert many.used() == 100                                             # 400 tries from 8 threads: exactly 100 get through
dc2 = guard.DailyCounter(2)
assert dc2.take() and dc2.take() and not dc2.take()
dc2.give_back()
assert dc2.used() == 1 and dc2.take() and not dc2.take()              # a question handed back can be used again
dc3 = guard.DailyCounter(2); dc3.give_back()
assert dc3.used() == 0                                                # and the count never goes below zero
# ---- guard.PasscodeGate: slows a wrong try, never locks anyone out
slept = []
gate = guard.PasscodeGate("pässcode", fail_delay_s=1.5, sleep=slept.append)
assert gate.required and gate.check("pässcode") == "ok" and slept == []
assert gate.check("nope") == "wrong" and gate.check(None) == "wrong" and gate.check("") == "wrong" and slept == [1.5, 1.5, 1.5]
for _ in range(50):
    gate.check("guess")
assert gate.check("pässcode") == "ok"                                 # 50 wrong tries later the right passcode still works
assert not guard.PasscodeGate("").required and guard.PasscodeGate(None).check("anything") == "ok"
assert guard.int_setting("20", 5) == 20 and guard.int_setting(" 0 ", 5) == 0 and guard.int_setting("twenty", 5) == 5
assert guard.int_setting(None, 5) == 5 and guard.int_setting("", 5) == 5
# ---- guard.get_guards: one set per process, however many visitors arrive at once
guard.reset()
made = []
def make():
    made.append(1); time.sleep(0.1)
    return guard.Guards("x", 3, 2)
got = []
ts = [threading.Thread(target=lambda: got.append(guard.get_guards(make))) for _ in range(6)]
[t.start() for t in ts]; [t.join() for t in ts]
assert len(made) == 1 and len({id(g) for g in got}) == 1
st.cache_resource.clear(); st.cache_data.clear()                      # what any visitor's browser can ask the server to do
assert guard.get_guards(make) is got[0]                               # ... does not touch the guards
guard.reset()
import unittest.mock
with unittest.mock.patch("guard.hmac.compare_digest", wraps=guard.hmac.compare_digest) as cd:     # the timing-safe comparison is really used
    guard.PasscodeGate("abc", sleep=lambda s: None).check("abd")
    assert cd.call_count == 1
print("ok  guard: daily cap (also with 8 threads), a new day resets, 429s are handed back, a wrong passcode only costs time, one set of guards survives a cache clear")

# ---- reranker.py: two first requests at the same moment load the model once (the page serves many visitors from one process)
built = []
class SlowCrossEncoder:
    def __init__(self, name, max_length=512):
        built.append(name); time.sleep(0.3)                 # long enough for the other threads to arrive
    def predict(self, pairs, batch_size=16, show_progress_bar=False):
        return [0.5] * len(pairs)
real_st, fake_flag = sys.modules.get("sentence_transformers"), os.environ.pop("FAKE_RERANK")
sys.modules["sentence_transformers"] = types.SimpleNamespace(CrossEncoder=SlowCrossEncoder)
reranker._model = None
try:
    ts = [threading.Thread(target=lambda: reranker.score_pairs("q", ["a", "b"])) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert built == [reranker.MODEL_NAME], built
finally:
    reranker._model = None
    os.environ["FAKE_RERANK"] = fake_flag
    if real_st is not None:
        sys.modules["sentence_transformers"] = real_st
    else:
        del sys.modules["sentence_transformers"]
print("ok  reranker: six simultaneous first requests load the model once")


class Probe:
    
    def __init__(self):
        self.now = self.most = 0
        self._lock = threading.Lock()

    def _enter(self):
        with self._lock:
            self.now += 1; self.most = max(self.most, self.now)
        time.sleep(0.05)
        with self._lock:
            self.now -= 1

    def encode(self, texts, **kw):
        self._enter()
        return np.zeros((len(texts), 384))

    def predict(self, pairs, **kw):
        self._enter()
        return [0.5] * len(pairs)


def hammer(fn, n=6):
    ts = [threading.Thread(target=fn) for _ in range(n)]
    [t.start() for t in ts]; [t.join() for t in ts]


saved = os.environ.pop("FAKE_RERANK"), embedder._model, reranker._model
embedder._model, reranker._model = Probe(), Probe()
hammer(lambda: embedder.embed_query("a question"))
hammer(lambda: reranker.score_pairs("q", ["a", "b"]))
assert embedder._model.most == 1 and reranker._model.most == 1, (embedder._model.most, reranker._model.most)
os.environ["FAKE_RERANK"], embedder._model, reranker._model = saved
print("ok  embedder and reranker: six visitors at the same moment use the model one at a time")


# ================================================================ B. the page, in a fake browser session
probe = rag.get_collection().get(where={"source": "administration_gitaly_cgroups"}, include=["embeddings"])
rag.embed_query = lambda q: np.array(probe["embeddings"][0])          # every question finds the Gitaly cgroups page
SANDBOX_DB = rag.DB_PATH

LLM = {"reply": "Set `memory_bytes` in gitlab.rb [1]. It covers all Git processes [2].", "status": 200}
calls = []


keys_seen = []                                                          # the x-api-key header of every call that reached the "model"


def handler(request):
    body = json.loads(request.content)
    calls.append(body)
    keys_seen.append(request.headers.get("x-api-key"))
    if LLM["status"] != 200:
        return httpx_for_llm.Response(LLM["status"], json={"type": "error", "error": {"type": "x", "message": "boom-secret"}})
    return httpx_for_llm.Response(200, json={
        "id": "m", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn",
        "stop_sequence": None, "content": [{"type": "text", "text": LLM["reply"]}],
        "usage": {"input_tokens": 1200, "output_tokens": 40}})


FAKE = anthropic.Anthropic(api_key="t", max_retries=0, http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))
REAL_ANTHROPIC = anthropic.Anthropic


def fake_client(*a, api_key=None, **k):
    """The page builds the owner's client with anthropic.Anthropic() and a visitor's with anthropic.Anthropic(api_key=...)."""
    if api_key is None:
        return FAKE
    return REAL_ANTHROPIC(api_key=api_key, max_retries=0,
                          http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))


anthropic.Anthropic = fake_client

SETTINGS = ("APP_PASSCODE", "APP_MAX_QUESTIONS", "APP_DAILY_LIMIT", "APP_MODES", "APP_SHOW_MEMORY", "RAG_RETRIEVAL", "LANGFUSE_BASE_URL")
LOG = pathlib.Path(os.environ["RAG_REQUEST_LOG"])


def reset(reply="Set `memory_bytes` in gitlab.rb [1]. It covers all Git processes [2].", status=200):
    LLM.update(reply=reply, status=status)
    guard.reset(); app_backend.reset()                                 # a fresh passcode gate, daily counter and backend
    for k in SETTINGS:
        os.environ.pop(k, None)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ["RAG_DB"] = SANDBOX_DB
    calls.clear(); keys_seen.clear()
    LOG.unlink(missing_ok=True)


def session(app=APP, secrets=None, **env):
    """A new visitor opening the page. env are settings (APP_...), secrets are what .streamlit/secrets.toml would hold."""
    os.environ.update(env)
    at = AppTest.from_file(app, default_timeout=60)
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    return at.run()


def ask(at, q):
    at.chat_input[0].set_value(q).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def shown(at):
    """Everything the page says, as one string."""
    els = [*at.markdown, *at.caption, *at.error, *at.warning, *at.info, *at.title, *at.header]
    return "\n".join(str(e.value) for e in els)


def log_lines():
    return [json.loads(l) for l in LOG.read_text().splitlines()] if LOG.exists() else []


# ---- first look
reset()
at = session()
assert not at.exception and at.title[0].value == "GitLab docs assistant"
examples = [b for b in at.button if b.key and b.key.startswith("example")]
assert len(examples) == 4 and examples[0].label == "How do I limit memory for Gitaly?"
assert at.sidebar.selectbox(key="mode").value == "hybrid" and at.sidebar.selectbox(key="mode").options == ["vector", "bm25", "hybrid", "hybrid_rerank"]
assert len(at.chat_input) == 1 and "CC BY-SA 4.0" in shown(at) and "not affiliated with GitLab" in shown(at)
assert "Questions this session: 0 of 20" in shown(at) and "Peak memory of this app" in shown(at)
assert calls == [] and not LOG.exists()                                # opening the page costs nothing
print("ok  first look: title, 4 example questions, hybrid is the default mode, licence notice, nothing sent to the model")

# ---- a typed question
ask(at, "How do I limit memory for Gitaly?")
txt = shown(at)
# Which chunks come first depends on the database this test runs against (yours is bigger than the one the test was first written on),
# so nothing below names a page. The test reads the "What the search found" list and checks that the rest of the page agrees with it.
found = [m.value for m in at.markdown if "**cited**" in m.value and "distance " in m.value][0]
hits = re.findall(r"^(\d+)\. (.+?)\s*\n(.*)$", found, re.M)               # (number, title, score line) for each chunk the model was shown
assert [h[0] for h in hits] == ["1", "2", "3", "4", "5"] and found.count("distance ") == 5 and "rrf " in found      # 5 hits, 2 lines each
assert {int(n) for n, _, scores in hits if "**cited**" in scores} == {1, 2}              # the reply cites [1] and [2]
src_md = [m.value for m in at.markdown if m.value.startswith("**Sources**")][0]
sources = re.findall(r"^(\d+)\. \[(.+)\]\((https://docs\.gitlab\.com/[^)]+)\)$", src_md, re.M)
assert [s[0] for s in sources] == ["1", "2"], sources                                    # the Sources list holds the two cited pages, in order
for (n, title, url), (_, hit_title, _) in zip(sources, hits):                            # ... with the titles of hit 1 and hit 2
    assert title == chat_text.md_text(hit_title), (title, hit_title)
    assert f"[[{n}]]({url})" in txt                                                       # citations are links to those pages
assert "hybrid search" in txt and "1,240 tokens" in txt and "about $0.0014" in txt
assert "Questions this session: 1 of 20" in shown(at)
assert len(at.chat_message) == 2 and not [b for b in at.button if b.key and b.key.startswith("example")]    # examples are gone
assert len(calls) == 1 and "<question>How do I limit memory for Gitaly?</question>" in calls[0]["messages"][0]["content"]
assert calls[0]["messages"][0]["content"].count("<source id=") == 5
lines = log_lines()
assert len(lines) == 1 and lines[0]["mode"] == "hybrid" and lines[0]["status"] == "answered" and lines[0]["cost_usd"] == 0.0014
print("ok  typed question: answer with clickable [n], Sources, the 5 chunks the model saw (the 2 it cited are marked), cost line, 1 log line")

# ---- the conversation is redrawn on the next question; each question stands alone
ask(at, "Second question")
assert len(at.chat_message) == 4 and len(calls) == 2 and len(log_lines()) == 2
assert "Second question" not in calls[0]["messages"][0]["content"] and "How do I limit memory" not in calls[1]["messages"][0]["content"]
assert len(calls[1]["messages"]) == 1                                  # no earlier turns are sent to the model
print("ok  second question: both answers stay on the page; the model gets one message per question, no history")

# ---- clear the conversation
at.sidebar.button[0].click().run()
assert len(at.chat_message) == 0 and len([b for b in at.button if b.key and b.key.startswith("example")]) == 4
assert "Questions this session: 2 of 20" in shown(at)                  # clearing the screen does not reset the limit
print("ok  clear: the screen is emptied, the per-session question count is kept")

# ---- an example button
reset()
at = session()
at.button(key="example1").click().run()
assert not at.exception and len(calls) == 1 and "Which executors does GitLab Runner support?" in calls[0]["messages"][0]["content"]
assert len(at.chat_message) == 2 and not [b for b in at.button if b.key and b.key.startswith("example")]
at.run()                                                               # a plain rerun must not ask the same thing again
assert len(calls) == 1 and len(log_lines()) == 1
print("ok  example button asks its question once (a rerun does not repeat it)")

# ---- the kinds of reply
for reply, status, expect, absent in [
    ("I couldn't find this in the GitLab documentation I have.", "refused", "Not found in the documentation", "**Sources**"),
    ("Which GitLab feature do you mean?", "clarifying", "needs a clearer question", "**Sources**"),
    ("Just do it, trust me.", "uncited", "no source numbers", "**Sources**"),
]:
    reset(reply)
    at = ask(session(), "some question")
    assert expect in shown(at) and absent not in shown(at) and log_lines()[0]["status"] == status, (status, shown(at))
reset("Do it [1] and also [9].")
at = ask(session(), "some question")
assert "source number(s) 9 that do not exist" in shown(at) and "[[1]](" in shown(at) and "\\[9\\]" in shown(at)
assert "**Sources**" in shown(at) and log_lines()[0]["status"] == "answered"
reset("It costs $5 and $10 [1]. Use `$HOME`.")
at = ask(session(), "some question")
assert "costs \\$5 and \\$10 [[1]](" in shown(at) and "`$HOME`" in shown(at)
reset("Do it [1]. ![t](https://evil.example/p.png?q=secret) [Official GitLab](https://evil.example/login) [Docs](https://docs.gitlab.com/x/)")
at = ask(session(), "some question")
txt = shown(at)
assert "![" not in txt and "](https://evil.example" not in txt and "Official GitLab (`https://evil.example/login`)" in txt
assert "[Docs](https://docs.gitlab.com/x/)" in txt and "[[1]](" in txt
print("ok  refused / clarifying / uncited / invented [9] each get their own note; $ is escaped outside code; pictures and foreign links are tamed")

# ---- model failures: friendly message, no detail, still one log line, the session carries on
for status, words, count in [(429, "busy", 0), (500, "could not be reached", 1), (401, "could not be reached", 1)]:
    reset(status=status)
    at = ask(session(), "some question")
    assert any(words in e.value for e in at.error), (status, shown(at))
    assert "boom-secret" not in shown(at) and "Traceback" not in shown(at)
    ll = log_lines()
    assert len(ll) == 1 and ll[0]["status"] == "error" and ll[0]["trace_id"] is None
    assert f"Questions this session: {count} of 20" in shown(at)       # a 429 is handed back; a 500 or 401 might have cost something
    assert at.session_state["history"] == []                           # an error is shown once, not stored
    LLM["status"] = 200
    ask(at, "again")                                                   # the next question works
    assert any("[[1]](" in m.value for m in at.markdown) and len(log_lines()) == 2 and len(at.session_state["history"]) == 1
reset(status=429)
at = ask(session(APP_DAILY_LIMIT="1"), "some question")                # the daily question is handed back too
LLM["status"] = 200
ask(at, "again")
assert any("[[1]](" in m.value for m in at.markdown) and not any("daily limit" in e.value for e in at.error)
reset(status=500)
at = ask(session(APP_DAILY_LIMIT="1"), "some question")
LLM["status"] = 200
ask(at, "again")
assert any("daily limit" in e.value for e in at.error)                 # a 500 is not handed back
print("ok  model errors (429, 500, 401): a short message with no detail, an error line in the log, the next question works; 429 is handed back")

# ---- turned-away questions: cost nothing, are not stored
reset()
at = ask(session(APP_DAILY_LIMIT="1"), "ab")
assert any("longer question" in e.value for e in at.error) and calls == [] and not LOG.exists()
for _ in range(3):
    ask(at, "ab")
ask(at, "x" * 3_000_000)                                               # the chat box stops this in a browser; a script need not
assert any("under 500 characters" in e.value for e in at.error) and calls == [] and not LOG.exists()
assert at.session_state["history"] == [] and len(at.chat_message) == 2     # only the latest one is on screen, nothing piles up
assert max(len(m.value) for m in at.markdown) < 1000                   # and the long text is not drawn in full
at = ask(at, "a real question")                                        # the daily token was not spent on any of them
assert len(calls) == 1 and "Questions this session: 1 of 20" in shown(at) and len(at.session_state["history"]) == 1
print("ok  too short / too long questions are turned away before any call, session count or daily limit, and are not stored")

# ---- a paid answer survives an interrupted run (Streamlit stops a run at its next st.* call when the visitor clicks something)
reset()
at = session()
import contextlib, io
real_spinner = st.spinner
@contextlib.contextmanager
def interrupting_spinner(*a, **k):
    yield
    raise RuntimeError("interrupted")                                  # what the end of the spinner does when a new click is waiting
st.spinner = interrupting_spinner
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):     # Streamlit prints the planted error; hide it
        at.chat_input[0].set_value("a question").run()
finally:
    st.spinner = real_spinner
assert len(calls) == 1 and len(log_lines()) == 1 and len(at.session_state["history"]) == 1 and at.session_state["asked"] == 1
at.run()
assert any("[[1]](" in m.value for m in at.markdown)                   # the answer is there on the next run
print("ok  a question that was paid for is stored even if the run is interrupted straight after the model call")

# ---- search modes
reset()
at = session()
for m, score in [("vector", "distance "), ("bm25", "bm25 "), ("hybrid_rerank", "rerank_score "), ("hybrid", "rrf ")]:
    at.sidebar.selectbox(key="mode").select(m).run()
    ask(at, f"question for {m}")
    assert log_lines()[-1]["mode"] == m and f"{m} search" in shown(at) and score in shown(at), m
    assert not at.exception
at.sidebar.selectbox(key="mode").select("bm25").run()
ask(at, "x question")
assert [l["mode"] for l in log_lines()] == ["vector", "bm25", "hybrid_rerank", "hybrid", "bm25"]
print("ok  the sidebar mode reaches the search (log shows it) and the scores of that mode are listed")

reset()
at = session(APP_MODES="vector, hybrid", RAG_RETRIEVAL="vector")
assert at.sidebar.selectbox(key="mode").options == ["vector", "hybrid"] and at.sidebar.selectbox(key="mode").value == "vector"
at = session(APP_MODES="nonsense")
assert len(at.sidebar.selectbox(key="mode").options) == 4              # a typo falls back to all modes, not to none
print("ok  APP_MODES limits the choices (typo -> all modes); RAG_RETRIEVAL picks the default")

# ---- limits: per session, per day
reset()
os.environ["APP_MAX_QUESTIONS"], os.environ["APP_DAILY_LIMIT"] = "2", "3"
a = session()
ask(a, "question one"); ask(a, "question two"); ask(a, "question three")
assert len(calls) == 2 and any("used your 2 questions" in e.value for e in a.error)
assert "Questions this session: 2 of 2" in shown(a) and len(log_lines()) == 2
b = session()                                                          # a new visitor (or a reload): own session count, shared day count
ask(b, "question 4")
assert len(calls) == 3 and not b.error
ask(b, "question 5")
assert len(calls) == 3 and any("daily limit" in e.value for e in b.error), shown(b)    # 3 per day for the whole app
assert len(b.session_state["history"]) == 1 and len(a.session_state["history"]) == 2   # turned-away questions are not stored
c = session()
ask(c, "question 6")
assert len(calls) == 3 and any("daily limit" in e.value for e in c.error) and len(log_lines()) == 3
print("ok  limits: 2 per session stop the 3rd without a model call; 3 per day are shared by all visitors; neither writes a log line")

reset()
os.environ["APP_DAILY_LIMIT"] = "0"
a = session()
for i in range(20):                                                    # 0 = no daily limit; the session limit (20) still applies
    ask(a, f"question {i}")
assert len(calls) == 20
ask(a, "question 21")
assert len(calls) == 20 and any("used your 20 questions" in e.value for e in a.error)
print("ok  APP_DAILY_LIMIT=0 turns the daily cap off; the default session limit is 20")

reset()
os.environ["APP_DAILY_LIMIT"], os.environ["APP_MAX_QUESTIONS"] = "lots", "many"       # typos must not switch the limits off
a = session()
assert "of 20" in shown(a)
ask(a, "a question"); assert len(calls) == 1
print("ok  a typo in a limit setting falls back to the defaults (20 per session, 200 per day)")

# ---- passcode (inside a form AppTest keeps a typed value only until the next run, so each set_value is followed straight by the click)
reset()
at = session(secrets={"APP_PASSCODE": "s3cret"})
assert not at.exception and len(at.chat_input) == 0 and len(at.text_input) == 1 and not at.sidebar.selectbox
at.text_input[0].set_value("wrong")
at.button[0].click().run()
assert any("not the passcode" in e.value for e in at.error) and len(at.chat_input) == 0 and "s3cret" not in shown(at)
at.text_input[0].set_value("s3cret")
at.button[0].click().run()
assert not at.error and len(at.chat_input) == 1
ask(at, "now it works")
assert len(calls) == 1
other = session(secrets={"APP_PASSCODE": "s3cret"})                    # another visitor is not unlocked by this one
assert len(other.chat_input) == 0
print("ok  passcode (from st.secrets): the page shows only the passcode box; wrong code refused; right code unlocks this session only")

reset()
at = session(secrets={"APP_PASSCODE": "s3cret"})
slept = []
guard.get_guards(None).gate._sleep = slept.append                      # the real gate waits a second after a wrong try; do not wait in the test
for i in range(12):
    at.text_input[0].set_value(f"guess{i}")
    at.button[0].click().run()
assert slept == [1.0] * 12                                             # every wrong try was slowed
other = session(secrets={"APP_PASSCODE": "s3cret"})
other.text_input[0].set_value("s3cret")
other.button[0].click().run()
assert len(other.chat_input) == 1                                      # 12 wrong tries by one visitor lock nobody out
print("ok  passcode: each wrong try is slowed by a second, and wrong tries never lock out the visitors who know it")

# ---- a clear-cache request from any browser does not reset the limits or reload the models
reset()
os.environ["APP_DAILY_LIMIT"] = "1"
a = ask(session(), "first question")
backend_before, guards_before = app_backend.get_backend(HERE), guard.get_guards(None)
st.cache_resource.clear(); st.cache_data.clear()
b = ask(session(), "second question")
assert any("daily limit" in e.value for e in b.error) and len(calls) == 1
assert app_backend.get_backend(HERE) is backend_before and guard.get_guards(None) is guards_before
print("ok  clearing Streamlit's caches (any visitor can ask for it) does not reset the daily limit or rebuild the backend")

# ---- secrets read from a real .streamlit/secrets.toml (in a separate process: Streamlit reads that file once per process)
CHILD = """
import json, os, sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
print(json.dumps({"errors": [e.value for e in at.error], "chat_input": len(at.chat_input), "text_input": len(at.text_input),
                  "exceptions": [e.value for e in at.exception]}))
"""
def run_with_secrets_file(toml, owner_key=True):
    d = TMP / f"secrets_{abs(hash((toml, owner_key)))}"
    (d / ".streamlit").mkdir(parents=True)
    if toml is not None:
        (d / ".streamlit" / "secrets.toml").write_text(toml)
    env = {k: v for k, v in os.environ.items() if k not in SETTINGS and k != "ANTHROPIC_API_KEY"}
    env.update(PYTHONPATH=str(HERE), HOME=str(d), RAG_DB=SANDBOX_DB, RAG_REQUEST_LOG=str(TMP / "child.jsonl"), FAKE_EMBED="1")   # FAKE_EMBED: no model download
    if owner_key:
        env["ANTHROPIC_API_KEY"] = "test-key"                           # the app has a key of its own (without one the page asks visitors for theirs)
    r = subprocess.run([sys.executable, "-c", CHILD, APP], cwd=d, env=env, capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout.strip().splitlines()[-1]), r
out, r = run_with_secrets_file('APP_PASSCODE = "from-the-file"\n')
assert out["text_input"] == 1 and out["chat_input"] == 0 and not out["exceptions"], (out, r.stderr[-500:])    # the file was read: the gate is up
out, r = run_with_secrets_file('APP_PASSCODE = "no closing quote\n')
assert out["chat_input"] == 0 and out["text_input"] == 0 and any("could not be read" in e for e in out["errors"]), (out, r.stderr[-500:])
out, r = run_with_secrets_file(None)                                    # no file at all is the normal case on a laptop: no gate, no error
assert out["chat_input"] == 1 and not out["errors"], (out, r.stderr[-500:])
out, r = run_with_secrets_file(None, owner_key=False)                   # no file and no key anywhere: the page asks the visitor for a key
assert out["chat_input"] == 0 and out["text_input"] == 1 and not out["errors"] and not out["exceptions"], (out, r.stderr[-500:])
print("ok  a real secrets.toml is read; a broken one stops the page (a passcode in it is never silently ignored); no file is fine")

# ---- settings from st.secrets reach rag / tracing through os.environ
reset()
at = session(secrets={"LANGFUSE_BASE_URL": "https://langfuse.example.test"})
assert os.environ.get("LANGFUSE_BASE_URL") == "https://langfuse.example.test"
os.environ.pop("LANGFUSE_BASE_URL")
reset(); os.environ["APP_PASSCODE"] = "from-env"
at = session(secrets={"APP_PASSCODE": "from-secrets"})
at.text_input[0].set_value("from-env"); at.button[0].click().run()
assert len(at.chat_input) == 1                                         # an environment variable wins over st.secrets
print("ok  secrets are copied to os.environ for rag.py / tracing.py; an environment variable wins over st.secrets")

# ---- the visitor's own API key. The app has no key of its own here, so every visitor must bring one.
KEY_A, KEY_B = "sk-ant-api03-" + "A" * 40, "sk-ant-api03-" + "B" * 40


class Catch(logging.Handler):
    """Collects every log line (with tracebacks) so the test can look for a key in them."""
    def __init__(self):
        super().__init__(); self.text = []
    def emit(self, record):
        self.text.append(self.format(record))


catch = Catch()
for _lg in (logging.getLogger(), api.log):
    _lg.addHandler(catch)


def byo_session(reply="Set `memory_bytes` in gitlab.rb [1]. It covers all Git processes [2].", status=200, secrets=None, **env):
    reset(reply, status)
    os.environ.pop("ANTHROPIC_API_KEY")                                 # the app has no key of its own
    return session(secrets=secrets, **env)


def give_key(at, key):
    at.text_input[0].set_value(key)
    at.button[0].click().run()                                          # on the key page the only button is the form's submit button
    return at


def remove_key_button(at):
    return [b for b in at.sidebar.button if b.label == "Remove my key"][0]


# the key page: nothing is loaded and nothing is sent until a key is given
at = byo_session()
assert not at.exception and at.title[0].value == "GitLab docs assistant"
assert len(at.chat_input) == 0 and len(at.text_input) == 1 and at.text_input[0].label == "Your Anthropic API key"
assert "does not pay for your questions" in shown(at) and "https://platform.claude.com/settings/keys" in shown(at)
assert not at.sidebar.selectbox and calls == [] and not app_backend.ready() and not LOG.exists()
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
assert at.text_input[0].proto.type == TextInputProto.PASSWORD          # the key is typed into a masked box
for bad in ("hello", "sk-ant-short", "sk-ant-api03-has space inside-xxxxxxxxx"):
    at.text_input[0].set_value(bad)
    at.button[0].click().run()
    assert at.error and len(at.chat_input) == 0 and at.session_state["api_key"] is None and bad not in shown(at), bad
assert not app_backend.ready()
print("ok  own key: without an app key the page asks for one first (nothing loaded, nothing sent); a wrong-looking key is refused and not repeated")

# a good key opens the chat; the question goes to Anthropic with that key and the owner's environment is untouched
give_key(at, KEY_A)
assert not at.exception and len(at.chat_input) == 1 and app_backend.ready() and at.session_state["api_key"] == KEY_A
assert "billed to your own API key" in shown(at) and "Questions this session: 0 (on your own key)" in shown(at)
ask(at, "How do I limit memory for Gitaly?")
assert keys_seen == [KEY_A] and len(log_lines()) == 1 and "[[1]](" in shown(at)
assert "Questions this session: 1 (on your own key)" in shown(at) and "about $0.0014" in shown(at)
assert "ANTHROPIC_API_KEY" not in os.environ                           # not copied into the process, which every visitor shares
assert guard.get_guards(None).daily.used() == 0                        # the app's own daily allowance is not touched
assert KEY_A not in json.dumps(at.session_state["history"], default=str)      # the conversation that is kept does not hold the key
print("ok  own key: a good key opens the chat, the question is billed to that key, nothing is put in the environment")

# two visitors at once: each question uses its own visitor's key
other = give_key(session(), KEY_B)
ask(other, "visitor b asks something")
ask(at, "visitor a asks again")
ask(other, "visitor b asks again")
assert keys_seen == [KEY_A, KEY_B, KEY_A, KEY_B], keys_seen
print("ok  own key: two visitors take turns and each question is sent with its own visitor's key")

# the key is nowhere but the visitor's session: not on any page, not in a log line, not in the request log
everything = "\n".join([shown(at), shown(other), LOG.read_text(), *catch.text])
assert any("ask mode=" in t for t in catch.text) and len(everything) > 500
assert KEY_A not in everything and KEY_B not in everything and "sk-ant-api03" not in everything
print("ok  own key: the key does not appear on the page, in the log lines or in the request log")

# the app's per-session and per-day limits are for the owner's key; they do not apply to a visitor's own
at = give_key(byo_session(APP_MAX_QUESTIONS="1", APP_DAILY_LIMIT="1"), KEY_A)
for i in range(3):
    ask(at, f"question number {i}")
assert len(calls) == 3 and "Questions this session: 3 (on your own key)" in shown(at) and guard.get_guards(None).daily.used() == 0
print("ok  own key: the owner's limits do not apply to a visitor who pays for their own questions")

# Anthropic refuses the key: the page forgets it and asks again, with the reason
at = give_key(byo_session(), KEY_A)
LLM.update(status=401)
ask(at, "a question with a key that is refused")
assert at.session_state["api_key"] is None and len(at.chat_input) == 0 and len(at.text_input) == 1
assert any("did not accept this key" in e.value for e in at.error) and "boom-secret" not in shown(at)
assert at.session_state["history"] == []                               # the failed question is not kept
LLM.update(status=200)
give_key(at, KEY_B)
ask(at, "the same question with a good key")
assert keys_seen == [KEY_A, KEY_B] and "[[1]](" in shown(at)
print("ok  own key: a refused key is forgotten and asked for again with the reason; a good one then works")

# other failures keep the key, say what is likely wrong, and never show Anthropic's own text
for status, words in [(400, "no credit left"), (403, "not allowed"), (500, "could not be reached")]:
    at = give_key(byo_session(status=status), KEY_A)
    ask(at, "a question that fails")
    assert at.session_state["api_key"] == KEY_A and len(at.chat_input) == 1, status
    assert any(words in e.value for e in at.error) and "boom-secret" not in shown(at), (status, shown(at))
at = give_key(byo_session(status=429), KEY_A)
ask(at, "a question that is rate limited")
assert any("rate-limiting this key" in e.value for e in at.error) and at.session_state["asked_own"] == 0 and at.session_state["api_key"] == KEY_A
print("ok  own key: 400 / 403 / 429 / 500 keep the key and give a useful sentence; a 429 is handed back")

# remove the key: back to the key page
at = give_key(byo_session(), KEY_A)
remove_key_button(at).click().run()
assert at.session_state["api_key"] is None and len(at.chat_input) == 0 and len(at.text_input) == 1
print("ok  own key: 'Remove my key' returns to the key page")

# a passcode, if the owner set one, comes first
at = byo_session(secrets={"APP_PASSCODE": "s3cret"})
assert len(at.text_input) == 1 and at.text_input[0].label == "Passcode"
at.text_input[0].set_value("s3cret")
at.button[0].click().run()
assert len(at.text_input) == 1 and at.text_input[0].label == "Your Anthropic API key" and len(at.chat_input) == 0
print("ok  own key: the owner's passcode (if any) is asked for before the key")

# the app HAS a key and a visitor still chooses their own (sidebar)
reset()
at = session()
assert len(at.chat_input) == 1 and len(at.sidebar.text_input) == 1                     # the chat is open; the key box is in the sidebar
at.sidebar.text_input[0].set_value(KEY_A)
[b for b in at.sidebar.button if b.label == "Use this key"][0].click().run()
assert at.session_state["api_key"] == KEY_A and not at.sidebar.text_input
ask(at, "on my own key")
assert keys_seen == [KEY_A] and guard.get_guards(None).daily.used() == 0 and at.session_state["asked"] == 0
remove_key_button(at).click().run()
ask(at, "on the app's key")
assert keys_seen == [KEY_A, "t"] and guard.get_guards(None).daily.used() == 1 and at.session_state["asked"] == 1   # "t" = the app's own client
print("ok  own key: when the app has a key, a visitor can switch to their own in the sidebar and back; limits count only the app's key")

# ... and when the app's limit is used up, the message points to the own-key option, which still works
reset()
at = session(APP_MAX_QUESTIONS="1")
ask(at, "first question")
ask(at, "second question")
assert any("use your own API key" in e.value for e in at.error) and len(calls) == 1
at.sidebar.text_input[0].set_value(KEY_B)
[b for b in at.sidebar.button if b.label == "Use this key"][0].click().run()
ask(at, "second question")
assert keys_seen[-1] == KEY_B and len(calls) == 2
print("ok  own key: past the app's session limit the visitor is told about the own-key option, and it works")

# a visitor's refused key in an app that has its own: the chat stays, the reason is shown, the app's key is used again
reset()
at = session()
at.sidebar.text_input[0].set_value(KEY_A)
[b for b in at.sidebar.button if b.label == "Use this key"][0].click().run()
LLM.update(status=401)
ask(at, "question with a refused key")
assert at.session_state["api_key"] is None and len(at.chat_input) == 1 and any("did not accept this key" in e.value for e in at.error)
LLM.update(status=200)
ask(at, "now on the app's key")
assert keys_seen[-1] == "t" and "[[1]](" in shown(at)
print("ok  own key: a refused key in an app that has its own key falls back to the app's key, with the reason shown")

# after every scenario above, failures included: no log line ever held a key
assert len(catch.text) > 30 and not [t for t in catch.text if KEY_A in t or KEY_B in t or "sk-ant-api03" in t]
logging.getLogger().removeHandler(catch); api.log.removeHandler(catch)
print("ok  own key: not one log line of this whole section (failures included) contains a key")


# ---- the search index: missing, explicit, and the committed copy in data/
reset()
os.environ["RAG_DB"] = "/nonexistent/chroma_db"
at = session()
assert not at.exception and any("RAG_DB is set, but there is no Chroma database" in e.value for e in at.error) and len(at.chat_input) == 0
assert "/nonexistent" not in shown(at)                                  # the visitor is not told where things are on the server

bare = TMP / "bare_app"
bare.mkdir()
shutil.copy(APP, bare / "streamlit_app.py")                            # an app folder with no outputs/ and no data/
reset()
os.environ.pop("RAG_DB")
at = session(app=str(bare / "streamlit_app.py"))
assert not at.exception and any("No search index found" in e.value for e in at.error), shown(at)

committed = bare / "data" / "chroma_db"
shutil.copytree(SANDBOX_DB, committed)
before = sorted((str(p.relative_to(committed)), p.stat().st_size, p.stat().st_mtime_ns) for p in committed.rglob("*"))
reset()
os.environ.pop("RAG_DB")
rag.DB_PATH, rag._collection, rag._corpus = "somewhere/else", None, None
at = ask(session(app=str(bare / "streamlit_app.py")), "from the committed copy")
assert not at.exception and len(calls) == 1 and "[[1]](" in shown(at)
used = pathlib.Path(rag.DB_PATH)
assert used != committed and not str(used).startswith(str(bare)) and (used / "chroma.sqlite3").exists(), used
after = sorted((str(p.relative_to(committed)), p.stat().st_size, p.stat().st_mtime_ns) for p in committed.rglob("*"))
assert before == after                                                 # the checked-in copy was only read, never written
rag.DB_PATH, rag._collection, rag._corpus = SANDBOX_DB, None, None
print("ok  index: bad RAG_DB and missing index give a clear message; the committed data/chroma_db is copied to a temp folder and left untouched")

# ---- the memory readout can be switched off
reset()
at = session(APP_SHOW_MEMORY="0")
assert "Peak memory" not in shown(at)
print("ok  APP_SHOW_MEMORY=0 hides the memory readout")

# ---- text from the corpus and from visitors is shown as text, not as markdown
reset("Fine [1].")
at = ask(session(), "what is *this* [x](http://evil.example) $5 <b>hi</b>")
user_line = [m.value for m in at.markdown if "evil.example" in m.value][0]
assert user_line.startswith("what is \\*this\\* \\[x\\]\\(http://evil.example\\)") and "\\$5" in user_line and "\\<b\\>" in user_line
print("ok  a visitor's question is drawn literally (no links, no maths, no HTML)")

# ---- the torchvision warnings: Streamlit's file watcher makes transformers import image modules that need torchvision
import logging
watcher_log = logging.getLogger("streamlit.watcher.local_sources_watcher")
seen = []
class Grab(logging.Handler):
    def emit(self, record): seen.append(record.getMessage())
grab = Grab(); old_handlers, old_propagate = watcher_log.handlers[:], watcher_log.propagate
watcher_log.handlers, watcher_log.propagate = [grab], False                        # only the test sees these records (none reach the screen)
chat_text.quiet_watcher_log(); chat_text.quiet_watcher_log()                       # twice: still one filter
assert sum(isinstance(f, chat_text._TorchvisionNoise) for f in watcher_log.filters) == 1
def log_with(exc):
    try:
        raise exc
    except Exception:
        watcher_log.warning("Examining the path of %s raised:", "transformers.models.x", exc_info=True)
log_with(ModuleNotFoundError("No module named 'torchvision'", name="torchvision"))
log_with(ModuleNotFoundError("No module named 'other'", name="other"))            # another missing module is still reported
log_with(ValueError("something else"))
watcher_log.warning("Failed to watch file %s", "/x")
watcher_log.handlers, watcher_log.propagate = old_handlers, old_propagate
assert [m.split(" raised")[0] for m in seen if "Examining" in m] == ["Examining the path of transformers.models.x"] * 2, seen
assert len(seen) == 3 and any("Failed to watch" in m for m in seen), seen
print("ok  only the torchvision warning from Streamlit's file watcher is hidden (other watcher warnings stay; the watcher stays on)")

print("\nAll Streamlit app tests passed.")
