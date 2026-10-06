"""Step 9: ask 10 questions through the running API and write down which ones fail.

1. Start the server in one terminal:     uvicorn api:app
2. In another terminal run:              python ten_questions.py
   (options: --url http://127.0.0.1:8000/ask    --out outputs/ten_questions)

Writes  <out>.md  (read this one, add your notes)  and  <out>.jsonl  (raw results, for later scoring).
No extra packages needed (uses only the Python standard library).

Each question has an expected KIND of reply, and (when it has one) the page that should be retrieved. The script
checks four things automatically. It cannot check whether the answer is actually TRUE: that part is for you
(compare the answer to the page, and tick the box in the .md file).
"""
import argparse, json, pathlib, urllib.error, urllib.request

# kind: what a good reply looks like.  answered = a cited answer | refused = "I couldn't find this" | clarifying = a question back
# page:  part of the URL of the page that holds the answer (None = no page should be needed)
# words: every one of these must appear in the answer (case-insensitive)
QUESTIONS = [
    dict(id=1, q="How do I limit memory for Gitaly?", ok={"answered"},
         page="/administration/gitaly/cgroups", words=["memory_bytes"],
         tests="baseline: one clear question, one page, a named setting"),
    dict(id=2, q="How can I stop people from overwriting or deleting a container image tag once it has been pushed?",
         ok={"answered"}, page="/immutable_container_tags", words=["immutable"],
         tests="different words from the page ('overwrite' vs 'immutable'): does meaning-based search bridge them?"),
    dict(id=3, q="What fields does the payload of a push event webhook contain?", ok={"answered"},
         page="/webhook_events", words=["commits"],
         tests="one page has 102 chunks; the right one has to beat 100 look-alikes (tag events, merge request events...)"),
    dict(id=4, q="Which executors does GitLab Runner support?", ok={"answered"},
         page="/runner/executors", words=["Kubernetes", "Docker"],
         tests="a list answer: does it name them all, or stop at the first ones?"),
    dict(id=5, q="What is the difference between the Docker executor and the Kubernetes executor?", ok={"answered"},
         page="/runner/executors", words=["Pod"],
         tests="a comparison: needs two passages from the same page; only fair if both are retrieved"),
    dict(id=6, q="Which security issues were fixed in GitLab 16.11.1?", ok={"answered"},
         page="patch-release-gitlab-16-11-1", words=["Path Traversal"],
         tests="near-duplicate pages: the other patch releases look the same, only the version number differs"),
    dict(id=7, q="Where in the admin UI do I switch on Gitaly cgroups?", ok={"answered", "refused"},
         page="/administration/gitaly/cgroups", words=["gitlab.rb"],
         tests="FALSE PREMISE: the page describes a config file, not a UI switch. A good reply corrects the question"),
    dict(id=8, q="What is the difference between a system hook and a webhook?", ok={"refused", "answered"},
         page=None, words=[],
         tests="CORPUS GAP: the system hooks page is not in the 147 pages. Good = says what is missing / answers only "
               "from what is there. Bad = confident invention"),
    dict(id=9, q="How do I reset my GitHub password?", ok={"refused"},
         page=None, words=[],
         tests="close to the topic but not in the docs: must refuse, not use outside knowledge"),
    dict(id=10, q="It doesn't work. What should I do?", ok={"clarifying"},
         page=None, words=[],
         tests="too vague: must ask what is meant, not guess"),
]


def post(url, question):
    req = urllib.request.Request(url, data=json.dumps({"question": question, "k": 5}).encode(),
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except urllib.error.URLError as e:
        raise SystemExit(f"Cannot reach {url} ({e.reason}). Is `uvicorn api:app` running?")


def judge(q, r):
    """-> (list of problems, label for the kind of failure). Empty list = passed the automatic checks."""
    if "error" in r:
        return [r["error"]], "server error"
    urls = [c["url"] for c in r["retrieved"]]
    cited = [c["url"] for c in r["citations"]]
    problems, kind = [], ""
    if q["page"] and not any(q["page"] in u for u in urls):
        problems.append(f"the right page ({q['page']}) is NOT in the 5 retrieved chunks")
        kind = "RETRIEVAL: right page not retrieved"
    if r["status"] not in q["ok"]:
        problems.append(f"expected {' or '.join(sorted(q['ok']))}, got {r['status']}")
        if not kind:
            kind = {"refused": "GENERATION: refused although the page was retrieved",
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
    ap.add_argument("--out", default="outputs/ten_questions")
    a = ap.parse_args()

    results = []
    for q in QUESTIONS:
        print(f"[{q['id']:>2}/{len(QUESTIONS)}] {q['q']}")
        r = post(a.url, q["q"])
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
    md = [f"# 10-question test\n", f"Automatic checks passed: **{passed}/{len(results)}**. "
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
                   "**Retrieved** (rank, cosine distance, page > section; * = cited in the answer):"]
            cited = {c["url"] + c["section"] for c in r["citations"]}
            for c in r["retrieved"]:
                star = "*" if c["url"] + c["section"] in cited else " "
                md.append(f"- {star}{c['rank']}. {c['distance']:.3f} | {c['title']} > {c['section']} | {c['url']}")
        md += ["", f"**Automatic checks:** {'all passed' if not x['problems'] else '; '.join(x['problems'])}",
               "", "**Your verdict:** [ ] true and complete  [ ] partly right  [ ] wrong  [ ] invented",
               "**Your notes (why did it fail? what would fix it?):** ", ""]
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")

    print(f"\n{passed}/{len(results)} passed the automatic checks.")
    print(f"Read and annotate: {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
