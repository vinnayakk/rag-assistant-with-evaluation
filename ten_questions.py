import argparse, json, pathlib, re, urllib.error, urllib.request
QUESTIONS = [
    dict(id=1, q="How do I limit memory for Gitaly?", ok={"answered"},
         page="/administration/gitaly/cgroups", words=["memory_bytes"], evidence=["memory_bytes"],
         tests="baseline: one clear question, one page, a named setting"),
    dict(id=2, q="How can I stop people from overwriting or deleting a container image tag once it has been pushed?",
         ok={"answered"}, page="/immutable_container_tags", words=["immutable"], evidence=["To create an immutable rule"],
         tests="different words from the page ('overwrite' vs 'immutable'): does meaning-based search bridge them?"),
    dict(id=3, q="What fields does the payload of a push event webhook contain?", ok={"answered"},
         page="/webhook_events", words=["total_commits_count"], evidence=['"total_commits_count": 4'],   # the PUSH example; the tag example has ": 0"
         tests="one page has 102 chunks; the right one has to beat 100 look-alikes (tag events, merge request events...)"),
    dict(id=4, q="Which executors does GitLab Runner support?", ok={"answered"},
         page="/runner/executors", words=["Kubernetes", "Docker"], evidence=["Docker Autoscaler"],
         tests="a list answer: does it name them all, or stop at the first ones?"),
    dict(id=5, q="What is the difference between the Docker executor and the Kubernetes executor?", ok={"answered"},
         page="/runner/executors", words=["Pod"], evidence=["new Pod", "Docker installation"],
         tests="a comparison: needs two passages from the same page; only fair if both are retrieved"),
    dict(id=6, q="Which security issues were fixed in GitLab 16.11.1?", ok={"answered"},
         page="patch-release-gitlab-16-11-1", words=["Path Traversal"], evidence=["Path Traversal", "ReDoS", "Bitbucket"],
         tests="near-duplicate pages: the other patch releases look the same, only the version number differs"),
    dict(id=7, q="Where in the admin UI do I switch on Gitaly cgroups?", ok={"answered", "refused"},
         page="/administration/gitaly/cgroups", words=["gitlab.rb"], evidence=["gitlab.rb"],
         tests="FALSE PREMISE: the page describes a config file, not a UI switch. A good reply corrects the question"),
    dict(id=8, q="What is the difference between a system hook and a webhook?", ok={"refused", "answered"},
         page=None, words=[], evidence=[],
         tests="CORPUS GAP: the system hooks page is not in the 147 pages. Good = says what is missing / answers only "
               "from what is there. Bad = confident invention"),
    dict(id=9, q="How do I reset my GitHub password?", ok={"refused"},
         page=None, words=[], evidence=[],
         tests="close to the topic but not in the docs: must refuse, not use outside knowledge"),
    dict(id=10, q="It doesn't work. What should I do?", ok={"clarifying"},
         page=None, words=[], evidence=[],
         tests="too vague: must ask what is meant, not guess"),
]


def post(url, question, mode=None):
    body = {"question": question, "k": 5, "debug": True}        # debug: we need the chunk text for the evidence check
    if mode:
        body["mode"] = mode
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except urllib.error.URLError as e:
        raise SystemExit(f"Cannot reach {url} ({e.reason}). Is `uvicorn api:app` running?")


def scores(c):
    """The scores a hit carries: dist (vector), bm25 (keywords), rrf (fused), rerank (cross-encoder)."""
    parts = [(n, c.get(k)) for n, k in [("dist", "distance"), ("bm25", "bm25"), ("rrf", "rrf"), ("rerank", "rerank_score")]]
    return " ".join(f"{n} {v:.3f}" for n, v in parts if v is not None)


def norm(s):
    return re.sub(r"\s+", " ", s).lower()


def judge(q, r):
    """-> (list of problems, label for the kind of failure). Empty list = passed the automatic checks."""
    if "error" in r:
        return [r["error"]], "server error"
    urls = [c["url"] for c in r["retrieved"]]
    cited = [c["url"] for c in r["citations"]]
    problems, kind = [], ""
    if q["evidence"]:                                           # did SEARCH find the text that holds the answer?
        have = norm(" ".join(c.get("text") or "" for c in r["retrieved"] if not q["page"] or q["page"] in c["url"]))
        lost = [e for e in q["evidence"] if norm(e) not in have]
        if lost:
            problems.append(f"the retrieved chunks do not contain: {', '.join(lost)}")
            kind = "RETRIEVAL: the text with the answer was not retrieved"
    elif q["page"] and not any(q["page"] in u for u in urls):
        problems.append(f"the right page ({q['page']}) is NOT in the 5 retrieved chunks")
        kind = "RETRIEVAL: right page not retrieved"
    if r["status"] not in q["ok"]:
        problems.append(f"expected {' or '.join(sorted(q['ok']))}, got {r['status']}")
        if not kind:
            kind = {"refused": "GENERATION: refused although the retrieved chunks hold the answer",
                    "clarifying": "GENERATION: asked a question instead of answering",
                    "uncited": "GENERATION: answer without citations"}.get(
                        r["status"], "GATE: answered something that should have been refused or clarified")
    if r["status"] == "answered" and q["page"] and any(q["page"] in u for u in urls) \
            and not any(q["page"] in u for u in cited):
        problems.append("the right page was retrieved but the answer does not cite it")
        kind = kind or "GENERATION: right page retrieved, not used"
    missing = [w for w in q["words"] if w.lower() not in r["answer"].lower()]
    if missing and r["status"] == "answered":
        problems.append(f"answer does not mention: {', '.join(missing)}")
        kind = kind or "ANSWER: incomplete or different from the page"
    if r["invalid_citations"]:
        problems.append(f"cites sources that do not exist: {r['invalid_citations']}")
        kind = kind or "GENERATION: invented citation"
    return problems, kind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/ask")
    ap.add_argument("--mode", choices=["vector", "bm25", "hybrid", "hybrid_rerank"], default=None,
                    help="how the server should search (default: the server's own default)")
    ap.add_argument("--out", default=None, help="default: outputs/ten_questions_<mode>")
    a = ap.parse_args()
    a.out = a.out or f"outputs/ten_questions_{a.mode or 'default'}"
    print(f"search mode: {a.mode or 'server default'}")

    results = []
    for q in QUESTIONS:
        print(f"[{q['id']:>2}/{len(QUESTIONS)}] {q['q']}")
        r = post(a.url, q["q"], a.mode)
        problems, kind = judge(q, r)
        results.append(dict(q=q, response=r, problems=problems, failure_kind=kind))
        print(f"       {'PASS' if not problems else 'FAIL'}  {r.get('status', 'error')}"
              + ("" if not problems else "  <- " + "; ".join(problems)))

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.with_suffix(".jsonl").open("w", encoding="utf-8") as fh:
        for x in results:
            fh.write(json.dumps({**x["q"], "ok": sorted(x["q"]["ok"]), "response": x["response"],
                                 "problems": x["problems"], "failure_kind": x["failure_kind"]}, ensure_ascii=False) + "\n")

    passed = sum(not x["problems"] for x in results)
    md = [f"# 10-question test (search mode: {a.mode or 'server default'})\n", f"Automatic checks passed: **{passed}/{len(results)}**. "
          "The checks cannot tell whether an answer is TRUE: read each answer next to its source page and fill in the "
          "last line of every question.\n",
          "| # | question | reply | auto | what went wrong |", "|---|---|---|---|---|"]
    for x in results:
        r = x["response"]
        md.append(f"| {x['q']['id']} | {x['q']['q']} | {r.get('status', 'error')} | "
                  f"{'pass' if not x['problems'] else 'FAIL'} | {x['failure_kind'] or ''} |")
    for x in results:
        q, r = x["q"], x["response"]
        md += ["", f"## {q['id']}. {q['q']}", f"*Tests:* {q['tests']}",
               f"*Expected:* {' or '.join(sorted(q['ok']))}" + (f", page `{q['page']}`" if q["page"] else "")]
        if "error" in r:
            md += [f"**Server error:** {r['error']}"]
        else:
            md += ["", "**Answer** (" + r["status"] + "):", "", "> " + r["answer"].replace("\n", "\n> "), "",
                   "**Retrieved** (rank, scores, page > section; * = cited in the answer):"]
            cited = {c["url"] + c["section"] for c in r["citations"]}
            for c in r["retrieved"]:
                star = "*" if c["url"] + c["section"] in cited else " "
                md.append(f"- {star}{c['rank']}. {scores(c)} | {c['title']} > {c['section']} | {c['url']}")
        md += ["", f"**Automatic checks:** {'all passed' if not x['problems'] else '; '.join(x['problems'])}",
               "", "**Your verdict:** [ ] true and complete  [ ] partly right  [ ] wrong  [ ] invented",
               "**Your notes (why did it fail? what would fix it?):** ", ""]
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")

    print(f"\n{passed}/{len(results)} passed the automatic checks.")
    print(f"Read and annotate: {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
