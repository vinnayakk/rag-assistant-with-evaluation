"""Offline tests for eval_answers.py: no API key, no network, no cost. Search runs for real on your database; the answering
model and the judge are a fake HTTP server (a real anthropic client pointed at it), so what is sent and how the reply is read are tested.
Run:   RAG_DB=outputs/chroma_db python test_eval_answers.py
What this CANNOT test: whether the real models answer or judge well. The trial run (--limit 3) and your own reading do that.
"""
import argparse, hashlib, json, os, pathlib, re, sys, tempfile
os.environ["FAKE_RERANK"] = "1"                                    # word-overlap stand-in for the reranker model
import numpy as np, anthropic
try:
    import httpx2 as httpx_for_llm                                  # newer anthropic SDKs use httpx2
except ImportError:
    import httpx as httpx_for_llm

import rag, judge
import eval_answers as ev

# pretend every question embeds to one real chunk of the Gitaly cgroups page (as test_api.py does)
probe = rag.get_collection().get(where={"source": "administration_gitaly_cgroups"}, include=["embeddings", "documents", "metadatas"])
rag.embed_query = lambda q: np.array(probe["embeddings"][0])
PAGE = "/" + probe["metadatas"][0]["url"].split("docs.gitlab.com/")[1]                       # /administration/gitaly/cgroups/
EVIDENCE = " ".join(probe["documents"][0].split()[-4:])                                      # words that ARE in the first retrieved chunk

QUESTIONS = [
    dict(id=1, q="How do I limit memory for Gitaly?", type="direct", pages=[PAGE], evidence=[EVIDENCE], expected=["answered"]),
    dict(id=2, q="Which port does Gitaly listen on?", type="direct", pages=[PAGE], evidence=[], expected=["answered"]),
    dict(id=3, q="Can you write a haiku about merge conflicts?", type="off-topic", pages=[], evidence=[], expected=["refused"]),
    dict(id=4, q="How do I set it up?", type="vague", pages=[], evidence=[], expected=["clarifying"]),
    dict(id=5, q="Is the sky green?", type="off-topic", pages=[], evidence=[], expected=["refused"]),
]


def fake_llm(judge_overrides=None):
    """A real anthropic client whose calls go to a fake. It tells the two jobs apart: a request with output_config is the JUDGE.
    Answering model: replies by question. Judge: 'INVENTED' in the answer -> an unsupported claim, else one claim backed by a
    real quote from source 1. -> (client, list of (job, request body))"""
    calls = []
    def handler(request):
        body = json.loads(request.content)
        msg = body["messages"][0]["content"]
        if "output_config" in body:
            calls.append(("judge", body))
            answer = re.search(r"<answer>\n(.*)\n</answer>", msg, re.S).group(1)
            src1 = re.search(r'<source id="1"[^\n]*>\n(.*?)\n</source>', msg, re.S).group(1)
            if "INVENTED" in answer or "is green" in answer:
                claims = [{"claim": "Gitaly listens on port 9999", "source": 0, "quote": "", "verdict": "unsupported", "note": "not stated"}]
            else:
                claims = [{"claim": "something the page says", "source": 1, "quote": " ".join(src1.split()[:6]), "verdict": "supported", "note": ""}]
            text = json.dumps({"claims": (judge_overrides or {}).get("claims", claims)})
        else:
            calls.append(("answer", body))
            m = re.search(r"<question>(.*)</question>", msg, re.S)
            q = m.group(1) if m else ""                                  # the preflight's "Reply with the word OK." has no <question>
            text = {"How do I limit memory for Gitaly?": "Set the limit in the file [1].",
                    "Which port does Gitaly listen on?": "INVENTED: Gitaly listens on port 9999 [1].",
                    "Can you write a haiku about merge conflicts?": rag.NOT_FOUND,
                    "How do I set it up?": "Which part of GitLab do you mean?",
                    "Is the sky green?": "Yes it is [1]."}.get(q, "OK")
        return httpx_for_llm.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn",
            "stop_sequence": None, "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 2000, "output_tokens": 100}})
    client = anthropic.Anthropic(api_key="t", max_retries=0,
                                 http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))
    return client, calls


ns = argparse.Namespace(k=5, controls=0, judge_model="judge-test-model")

# ---------------------------------------------------------------- one mode, question by question
client, calls = fake_llm()
with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp) / "eval_answers_vector.jsonl"
    rows, controls = ev.run_mode("vector", QUESTIONS, ns, client, path)
    assert [r["status"] for r in rows] == ["answered", "answered", "refused", "clarifying", "answered"], [r["status"] for r in rows]
    assert [r["reply_ok"] for r in rows] == [True, True, True, True, False]               # Q5 was answered but should be refused
    assert rows[0]["judge"]["verdict"] == "faithful" and rows[0]["judge"]["n_supported"] == 1
    assert rows[1]["judge"]["verdict"] == "unfaithful" and rows[1]["judge"]["claims"][0]["verdict"] == "unsupported"
    assert rows[2]["judge"] is None and rows[3]["judge"] is None                           # refusals and questions are not judged
    assert [j for j, _ in calls].count("judge") == 3 and [j for j, _ in calls].count("answer") == 5
    assert rows[0]["page_found"] is True and rows[0]["evidence_found"] is True and rows[2]["page_found"] is None
    assert len(rows[0]["chunks"]) == 5 and rows[0]["chunks"][0]["text"] and rows[0]["usage"] == {"input_tokens": 2000, "output_tokens": 100}
    assert set(rows[0]["ms"]) == {"search", "llm", "judge"} and set(rows[2]["ms"]) == {"search", "llm"}
    assert next(b for j, b in calls if j == "judge")["model"] == "judge-test-model"
    assert next(b for j, b in calls if j == "answer")["model"] == rag.LLM_MODEL
    print("ok  run_mode: statuses, reply check, judge only on answers, page/evidence check, timings, models")

    # the file on disk is complete and reads back the same
    back, back_controls = ev.load_mode(path)
    assert back == json.loads(json.dumps(rows)) and back_controls == []
    print("ok  every question is written to the .jsonl as it finishes, and reads back")

    # ---- numbers
    s = ev.stats(rows, controls)
    assert s["reply"] == (4, 5) and s["answered"] == (2, 2) and s["held_back"] == (2, 3)
    assert s["faithful"] == (2, 3) and s["claims"] == (2, 3)       # Q1 and Q5 are backed (Q5 is a wrong REPLY, but a faithful one), Q2 is not
    assert s["contradicted"] == 0 and s["page"] == (2, 2) and s["evidence"] == (1, 1)
    assert s["errors"] == 0 and s["uncited"] == 0 and s["tok_gen"] == (10000, 500) and s["tok_judge"][0] == 3 * 2000
    text = ev.report({"vector": (rows, controls)}, ["vector"])
    assert "| right kind of reply (answered, refused or asked back, as expected) | 4/5 (80%), 95% interval" in text, text
    assert "| faithful answers (every claim backed by the chunks) | 2/3 (67%)" in text
    assert "| Q2 | direct | answered, unfaithful 0/1 |" in text and "| Q5 | off-topic | answered (expected refused)" in text, text
    assert "| Q1 |" not in text.split("## Questions to look at")[1]                          # a clean answer is not listed
    assert "0 of 0 flagged unfaithful  (no control run)" in text
    a_md = ev.audit(rows, controls, "vector")
    assert "**Needs your eyes (2):** Q2, Q5" in a_md and "Do you agree with the judge?" in a_md and "unsupported | Gitaly listens on port 9999" in a_md
    print("ok  stats, report and audit")

    # ---- an answer the model gave but the API could not deliver is a failed question, not a wrong one
    bad = dict(rows[0], error="APIConnectionError: boom", status=None, reply_ok=None)
    assert ev.stats([bad], [])["errors"] == 1 and ev.stats([bad], [])["reply"] == (0, 0)
    assert ev.trouble(bad) and ev.short(bad) == "ERROR (no answer)"

# ---------------------------------------------------------------- controls: judge answers against the WRONG chunks
def row(i, urls, answer="An answer [1]."):
    """A complete saved row, made by hand."""
    return dict(kind="answer", mode="vector", id=i, q=f"question {i}", type="direct", expected=["answered"], pages=[], answer=answer,
                status="answered", reply_ok=True, citations=[1], invalid_citations=[], page_found=None, evidence_found=None,
                ms={"search": 1, "llm": 1, "judge": 1}, usage={"input_tokens": 1, "output_tokens": 1},
                chunks=[{"rank": n, "title": "T", "section": "S", "url": u, "text": f"text of {u} for question {i}"} for n, u in enumerate(urls, 1)],
                judge={"verdict": "faithful", "n_supported": 1, "n_claims": 1, "n_contradicted": 0, "claims": [], "model": "m",
                       "usage": {"input_tokens": 1, "output_tokens": 1}})
mix = [row(1, ["/a", "/b"]), row(2, ["/a", "/c"]), row(3, ["/d"]), row(4, ["/e"]), row(5, ["/d", "/f"])]
pairs = ev.pick_control_pairs(mix, 3)
assert len(pairs) == 3 and all(not {c["url"] for c in m["chunks"]} & {c["url"] for c in o["chunks"]} for m, o in pairs)
assert ev.pick_control_pairs(mix, 0) == [] and ev.pick_control_pairs([], 3) == []
assert [m["id"] for m, _ in ev.pick_control_pairs(mix, 3)] == [m["id"] for m, _ in pairs]                   # same choice every time
assert ev.pick_control_pairs([row(1, ["/a"]), row(2, ["/a"])], 2) == []                                    # no question with other pages: no control
client, calls = fake_llm()
done = ev.run_controls(pairs[:1], client, "judge-test-model")
sent = calls[0][1]["messages"][0]["content"]
m0, o0 = pairs[0]
assert o0["chunks"][0]["text"] in sent and m0["chunks"][0]["text"] not in sent and m0["answer"] in sent         # WRONG chunks, own answer
assert done[0]["kind"] == "control" and done[0]["id"] == m0["id"] and done[0]["wrong_sources_from"] == o0["id"]
print("ok  controls: the answer is judged against another question's chunks that share no page with its own")

# the sanity check is reported, and a judge that passes the wrong chunks gets a loud warning
r_ok = ev.report({"vector": (mix, [dict(kind="control", mode="vector", id=1, wrong_sources_from=3, judge={"verdict": "unfaithful", "usage": {"input_tokens": 1, "output_tokens": 1}})])}, ["vector"])
r_bad = ev.report({"vector": (mix, [dict(kind="control", mode="vector", id=1, wrong_sources_from=3, judge={"verdict": "faithful", "usage": {"input_tokens": 1, "output_tokens": 1}})])}, ["vector"])
assert "- vector: 1 of 1 flagged unfaithful\n" in r_ok + "\n" and "do not trust" not in r_ok and "do not trust" in r_bad
print("ok  report: control result shown; a judge that fails it triggers the warning")

# ---------------------------------------------------------------- preflight: stop before spending
def failing_client(status, kind="authentication_error"):
    def handler(request):
        return httpx_for_llm.Response(status, json={"type": "error", "error": {"type": kind, "message": "invalid x-api-key"}})
    return anthropic.Anthropic(api_key="t", max_retries=0, http_client=httpx_for_llm.Client(transport=httpx_for_llm.MockTransport(handler)))

client, calls = fake_llm()
ev.preflight(client, "gen-test-model", "judge-test-model")
assert [j for j, _ in calls] == ["answer", "judge", "judge"] and calls[0][1]["model"] == "gen-test-model" and calls[1][1]["model"] == "judge-test-model"
for bad_client, name in [(failing_client(401), "AuthenticationError"), (failing_client(404, "not_found_error"), "NotFoundError"),
                         (failing_client(400, "invalid_request_error"), "BadRequestError")]:
    try:
        ev.preflight(bad_client, "gen-test-model", "judge-test-model")
        raise AssertionError("preflight should have stopped")
    except SystemExit as e:
        assert "preflight failed" in str(e) and name in str(e) and "Nothing was spent" in str(e), str(e)
print("ok  preflight: tries both models and the judge first; a bad key, model name or request stops everything with a clear message")

# ---------------------------------------------------------------- the whole program: file names, compare, rejudge
def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

def run_main(*argv, client=None):
    keep = (sys.argv, anthropic.Anthropic)
    sys.argv = ["eval_answers.py", *argv]
    if client:
        anthropic.Anthropic = lambda *a, **k: client
    try:
        ev.main()
    finally:
        sys.argv, anthropic.Anthropic = keep

here = os.getcwd()
with tempfile.TemporaryDirectory() as tmp:
    qfile = pathlib.Path(tmp) / "q.jsonl"
    qfile.write_text("\n".join(json.dumps(q) for q in QUESTIONS) + "\n")
    os.chdir(tmp)
    try:
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        client, calls = fake_llm()
        run_main("--questions", str(qfile), "--modes", "vector,hybrid_rerank", "--judge-model", "judge-test-model", "--controls", "0", client=client)
        files = sorted(p.name for p in pathlib.Path("outputs").iterdir())
        assert files == ["eval_answers_hybrid_rerank.jsonl", "eval_answers_hybrid_rerank.md", "eval_answers_vector+hybrid_rerank.md",
                         "eval_answers_vector.jsonl", "eval_answers_vector.md"], files
        combined = pathlib.Path("outputs/eval_answers_vector+hybrid_rerank.md").read_text()
        assert "# Answer evaluation: 5 questions, answered with vector and hybrid_rerank" in combined and "| vector | hybrid_rerank |" in combined
        assert "## Question by question against `vector`" in combined
        assert "# Answers and judge verdicts, search mode: hybrid_rerank" in pathlib.Path("outputs/eval_answers_hybrid_rerank.md").read_text()
        print("ok  main: one pair of files per mode and one combined table, each named after its modes")

        # a failing preflight writes no files at all
        files_before = sorted(p.name for p in pathlib.Path("outputs").iterdir())
        try:
            run_main("--questions", str(qfile), "--modes", "bm25", "--controls", "0", client=failing_client(401))
            raise AssertionError("should have stopped")
        except SystemExit as e:
            assert "preflight failed" in str(e)
        assert files_before == sorted(p.name for p in pathlib.Path("outputs").iterdir())
        print("ok  main: a failing preflight stops before anything is written")

        # running ONE mode again replaces only that mode's files
        before = {p: md5(p) for p in pathlib.Path("outputs").iterdir() if "hybrid_rerank" in p.name}
        run_main("--questions", str(qfile), "--modes", "vector", "--judge-model", "judge-test-model", "--controls", "0", client=fake_llm()[0])
        assert before == {p: md5(p) for p in pathlib.Path("outputs").iterdir() if "hybrid_rerank" in p.name}, "another mode's file changed"
        print("ok  re-running vector did not touch any hybrid_rerank file")

        # a trial never replaces a full run
        run_main("--questions", str(qfile), "--modes", "vector", "--limit", "2", "--judge-model", "judge-test-model", "--controls", "0", client=fake_llm()[0])
        full = sorted(p.name for p in pathlib.Path("outputs").iterdir())
        assert "eval_answers_trial_vector.jsonl" in full and "eval_answers_trial_vector.md" in full, full
        assert len(pathlib.Path("outputs/eval_answers_trial_vector.jsonl").read_text().splitlines()) == 2
        assert len(pathlib.Path("outputs/eval_answers_vector.jsonl").read_text().splitlines()) == 5
        run_main("--questions", str(qfile), "--modes", "vector", "--ids", "1,3", "--judge-model", "judge-test-model", "--controls", "0", client=fake_llm()[0])
        assert len(pathlib.Path("outputs/eval_answers_trial_vector.jsonl").read_text().splitlines()) == 2 and True
        assert len(pathlib.Path("outputs/eval_answers_vector.jsonl").read_text().splitlines()) == 5
        print("ok  --limit and --ids write to ..._trial_... and leave the full run alone")

        # --compare: no key, no model calls, same table
        os.environ.pop("ANTHROPIC_API_KEY")
        os.remove("outputs/eval_answers_vector+hybrid_rerank.md")
        run_main("--questions", str(qfile), "--modes", "vector,hybrid_rerank", "--compare")
        assert pathlib.Path("outputs/eval_answers_vector+hybrid_rerank.md").read_text().startswith("# Answer evaluation: 5 questions")
        try:
            run_main("--questions", str(qfile), "--modes", "vector,bm25", "--compare")
            raise AssertionError("a missing file should stop --compare")
        except SystemExit as e:
            assert "eval_answers_bm25.jsonl" in str(e) and "--modes bm25" in str(e)
        try:
            run_main("--questions", str(qfile), "--modes", "vector")
            raise AssertionError("no key should stop the run")
        except SystemExit as e:
            assert "ANTHROPIC_API_KEY" in str(e)
        print("ok  --compare rebuilds the table from the saved files; missing files and a missing key give a clear message")

        # --rejudge: same answers, new verdicts, other mode untouched
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        old = {p: md5(p) for p in pathlib.Path("outputs").iterdir() if "hybrid_rerank" in p.name and p.suffix == ".jsonl"}
        before_rows = ev.load_mode("outputs/eval_answers_vector.jsonl")[0]
        strict, calls = fake_llm({"claims": [{"claim": "x", "source": 0, "quote": "", "verdict": "unsupported", "note": "strict"}]})
        run_main("--questions", str(qfile), "--modes", "vector", "--rejudge", "--judge-model", "judge-test-model", "--controls", "0", client=strict)
        after_rows = ev.load_mode("outputs/eval_answers_vector.jsonl")[0]
        assert [r["answer"] for r in before_rows] == [r["answer"] for r in after_rows]                      # answers kept
        assert [j for j, _ in calls] == ["judge"] * 5          # 2 preflight judgements + the 3 answers; nothing was answered again
        assert [r["judge"]["verdict"] if r["judge"] else None for r in after_rows] == ["unfaithful", "unfaithful", None, None, "unfaithful"]
        assert old == {p: md5(p) for p in pathlib.Path("outputs").iterdir() if "hybrid_rerank" in p.name and p.suffix == ".jsonl"}
        print("ok  --rejudge keeps the answers, re-runs only the judge, and touches only the mode asked for")
    finally:
        os.chdir(here)
        os.environ.pop("ANTHROPIC_API_KEY", None)
print("all eval_answers tests passed")
