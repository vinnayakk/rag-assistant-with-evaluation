"""Step 14: answer the question set with two search modes, check every answer with the faithfulness judge, compare.

    python eval_answers.py --limit 3 --modes vector      # a cheap trial first (3 questions, a few cents)
    python eval_answers.py                               # vector and hybrid_rerank on all questions
    python eval_answers.py --modes hybrid                # any modes you like, one set of files per mode
    python eval_answers.py --rejudge --modes vector      # judge the SAVED answers again (after changing judge.py)
    python eval_answers.py --compare                     # rebuild the side-by-side table from the saved files

This one DOES call the language model: once to write each answer (rag.LLM_MODEL) and once to judge it (judge.JUDGE_MODEL).
It needs ANTHROPIC_API_KEY. eval_recall.py is the search-only test; this is the answer test.
Before the real run it makes three tiny test calls (the "preflight"): a wrong key, a wrong model name or a request the API
rejects stops it there, before any real money is spent. It also checks the judge on one true and one false statement.

What it measures per mode, for every question in eval_questions.jsonl:
    right kind of reply    answered / refused / asked back, as the question's "expected" says
    chunks held the answer the evidence strings are in the 5 chunks the model was given (same test as eval_recall)
    faithful               the judge found every claim of the answer backed by those 5 chunks (see judge.py)
Faithful is about the answer against its chunks. It does not say the answer is right: the chunks can be the wrong ones.

Files are named after the mode, like eval_recall.py, so one run never replaces another mode's results:
    outputs/eval_answers_<mode>.jsonl      everything: answer, the 5 chunks, the judge's claims. What --rejudge and --compare read
    outputs/eval_answers_<mode>.md         the same, readable: one block per question, with the judge's claims and a line for YOUR verdict
    outputs/eval_answers_<mode1>+<mode2>.md   the results table
A run with --limit or --ids writes to outputs/eval_answers_trial_... instead, so a trial never replaces a full run.
"""
import argparse, json, os, pathlib, statistics, time

import anthropic

import judge
import rag
from api import status_of                      # one definition of "answered / refused / clarifying / uncited"
from eval_recall import evidence_rank, first_rank, load_questions, out_file, pct, wilson

ANSWERED = ("answered", "uncited")             # the replies that make factual claims, so the judge has something to check


# ----------------------------------------------------------------------------- one question
def judge_row(row, client, model):
    """Judge one saved answer against its own 5 chunks. Fills row['judge'], or row['judge_error'] if the judge failed."""
    row["judge"] = None
    row.pop("judge_error", None)
    t0 = time.perf_counter()
    try:
        row["judge"] = judge.judge_answer(row["q"], row["chunks"], row["answer"], client, model)
    except (judge.JudgeError, anthropic.APIError) as e:
        row["judge_error"] = f"{type(e).__name__}: {e}"
    row["ms"]["judge"] = round((time.perf_counter() - t0) * 1000)


def answer_question(x, mode, k, client, gen_model, judge_model):
    row = dict(kind="answer", mode=mode, id=x["id"], q=x["q"], type=x.get("type", ""), expected=x["expected"],
               pages=x.get("pages", []), status=None, reply_ok=None, answer="", citations=[], invalid_citations=[],
               chunks=[], page_found=None, evidence_found=None, ms={}, usage={}, judge=None)
    t0 = time.perf_counter()
    chunks = rag.search(x["q"], k=k, mode=mode)
    t1 = time.perf_counter()
    row["chunks"] = [{"rank": c["rank"], "title": c["title"], "section": c["section"], "url": c["url"], "text": c["text"]}
                     for c in chunks]
    try:
        r = rag.answer(x["q"], chunks, client=client, model=gen_model)
    except anthropic.APIError as e:
        row["error"] = f"{type(e).__name__}: {e}"
        return row
    t2 = time.perf_counter()
    row.update(status=status_of(r), answer=r["answer"], citations=[c["n"] for c in r["citations"]],
               invalid_citations=r["invalid_citations"], ms={"search": round((t1 - t0) * 1000), "llm": round((t2 - t1) * 1000)},
               usage={"input_tokens": r["usage"]["input_tokens"], "output_tokens": r["usage"]["output_tokens"]})
    row["reply_ok"] = row["status"] in x["expected"]              # 'uncited' is never in expected, so it counts as wrong
    if x.get("pages"):
        row["page_found"] = first_rank(chunks, x["pages"]) is not None
    if x.get("evidence"):
        row["evidence_found"] = evidence_rank(chunks, x["pages"], x["evidence"]) is not None
    if row["status"] in ANSWERED:
        judge_row(row, client, judge_model)
    return row


# ----------------------------------------------------------------------------- the judge's own sanity check
def pick_control_pairs(rows, n):
    """Choose up to n judged answers, spread over the list, and for each the chunks of ANOTHER question that share no page
    with its own. An answer judged against the wrong sources must come out unfaithful."""
    cands = [i for i, r in enumerate(rows) if r.get("judge") and r["judge"]["verdict"] in ("faithful", "unfaithful")]
    if n <= 0 or not cands:
        return []
    pairs = []
    for i in cands[::max(1, len(cands) // n)][:n]:
        mine = {c["url"] for c in rows[i]["chunks"]}
        for j in list(range(i + 1, len(rows))) + list(range(i)):
            if rows[j].get("chunks") and not mine & {c["url"] for c in rows[j]["chunks"]}:
                pairs.append((rows[i], rows[j]))
                break
    return pairs


def run_controls(pairs, client, model):
    out = []
    for mine, other in pairs:
        c = dict(kind="control", mode=mine["mode"], id=mine["id"], wrong_sources_from=other["id"], judge=None)
        try:
            c["judge"] = judge.judge_answer(mine["q"], other["chunks"], mine["answer"], client, model)
        except (judge.JudgeError, anthropic.APIError) as e:
            c["judge_error"] = f"{type(e).__name__}: {e}"
        out.append(c)
    return out


# ----------------------------------------------------------------------------- saving and loading
def write_line(fh, row):
    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    fh.flush()                                                   # so a Ctrl-C leaves every finished question on disk


def write_mode(path, rows, controls):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows + controls:
            write_line(fh, r)


def load_mode(path):
    rows, controls = [], []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            (controls if r.get("kind") == "control" else rows).append(r)
    return rows, controls


def load_saved(prefix, modes):
    """-> {mode: (rows, controls)}, keeping only the questions that EVERY mode has, so the table compares like with like."""
    results, missing = {}, []
    for m in modes:
        path = out_file(prefix, [m], ".jsonl")
        if not path.exists():
            missing.append(f"  - {path}   (make it with:  python eval_answers.py --modes {m})")
        else:
            results[m] = load_mode(path)
    if missing:
        raise SystemExit("--compare needs one saved file per mode, and these are missing:\n" + "\n".join(missing))
    common = set.intersection(*(set(r["id"] for r in rows) for rows, _ in results.values()))
    for m in modes:
        rows, controls = results[m]
        if len(rows) != len(common):
            print(f"note: {m} has {len(rows)} questions but only {len(common)} are in every file; comparing those.")
        results[m] = ([r for r in rows if r["id"] in common], controls)
    return results


# ----------------------------------------------------------------------------- numbers
def ratio(h, n, ci=False):
    if not n:
        return "-"
    s = f"{h}/{n} ({pct(h, n)})"
    if ci:
        lo, hi = wilson(h, n)
        s += f", 95% interval {100 * lo:.0f} to {100 * hi:.0f}%"
    return s


def med(xs, unit="ms"):
    xs = [x for x in xs if x is not None]
    return f"{statistics.median(xs):.0f} {unit}" if xs else "-"


def judged(rows):
    return [r for r in rows if not r.get("error") and r.get("judge") and r["judge"]["verdict"] in ("faithful", "unfaithful")]


def stats(rows, controls):
    ok = [r for r in rows if not r.get("error")]
    should = [r for r in ok if r["expected"] == ["answered"]]            # the questions the docs can answer
    shouldnt = [r for r in ok if "answered" not in r["expected"]]        # gaps, off-topic, vague: refuse or ask back
    pg = [r for r in ok if r["page_found"] is not None]
    ev = [r for r in ok if r["evidence_found"] is not None]
    jd = judged(ok)
    claims = [r["judge"] for r in jd]
    ctl = [c for c in controls if c.get("judge")]
    return dict(
        n=len(rows), errors=len(rows) - len(ok),
        reply=(sum(r["reply_ok"] for r in ok), len(ok)),
        answered=(sum(r["status"] == "answered" for r in should), len(should)),
        held_back=(sum(r["reply_ok"] for r in shouldnt), len(shouldnt)),
        page=(sum(r["page_found"] for r in pg), len(pg)),
        evidence=(sum(r["evidence_found"] for r in ev), len(ev)),
        faithful=(sum(r["judge"]["verdict"] == "faithful" for r in jd), len(jd)),
        claims=(sum(j["n_supported"] for j in claims), sum(j["n_claims"] for j in claims)),
        contradicted=sum(1 for j in claims if j["n_contradicted"]),
        no_claims=sum(1 for r in ok if r.get("judge") and r["judge"]["verdict"] == "no_claims"),
        judge_errors=sum(1 for r in ok if r.get("judge_error")),
        uncited=sum(r["status"] == "uncited" for r in ok),
        invalid=sum(1 for r in ok if r["invalid_citations"]),
        control=(sum(c["judge"]["verdict"] == "unfaithful" for c in ctl), len(ctl)),
        t_search=med(r["ms"].get("search") for r in ok), t_llm=med(r["ms"].get("llm") for r in ok),
        t_judge=med(r["ms"].get("judge") for r in ok if r.get("judge")),
        tok_gen=(sum(r["usage"]["input_tokens"] for r in ok), sum(r["usage"]["output_tokens"] for r in ok)),
        tok_judge=(sum(r["judge"]["usage"]["input_tokens"] for r in ok if r.get("judge")) + sum(c["judge"]["usage"]["input_tokens"] for c in ctl),
                   sum(r["judge"]["usage"]["output_tokens"] for r in ok if r.get("judge")) + sum(c["judge"]["usage"]["output_tokens"] for c in ctl)),
    )


def short(r):
    """One table cell for one question in one mode."""
    if r.get("error"):
        return "ERROR (no answer)"
    s = r["status"] + ("" if r["reply_ok"] else f" (expected {' or '.join(r['expected'])})")
    j = r.get("judge")
    if j and j["verdict"] != "no_claims":
        s += f", {j['verdict']} {j['n_supported']}/{j['n_claims']}"
    elif r.get("judge_error"):
        s += ", judge failed"
    return s


def trouble(r):
    """Does this answer need a human look? Wrong kind of reply, an unfaithful claim, or a failure."""
    j = r.get("judge")
    return bool(r.get("error") or r.get("judge_error") or r["reply_ok"] is False or (j and j["verdict"] == "unfaithful"))


# ----------------------------------------------------------------------------- the report
def diff_ids(base_rows, rows, good):
    """Question ids that `rows` gets right and the base mode does not (gained), and the other way round (lost)."""
    b = {r["id"]: r for r in base_rows}
    gained = [r["id"] for r in rows if good(r) and r["id"] in b and not good(b[r["id"]]) and not b[r["id"]].get("error")]
    lost = [r["id"] for r in rows if not good(r) and not r.get("error") and r["id"] in b and good(b[r["id"]])]
    return gained, lost


def report(results, modes):
    S = {m: stats(*results[m]) for m in modes}
    n = S[modes[0]]["n"]
    out = [f"# Answer evaluation: {n} questions, answered with {' and '.join(modes)}", "",
           "Every answer was written by one model and checked by a judge model against the 5 chunks the answering "
           "model was given. The set is small, so a difference of one or two questions between modes is not evidence of anything.", ""]

    rows = [
        ("right kind of reply (answered, refused or asked back, as expected)", lambda s: ratio(*s["reply"], ci=True)),
        ("  answered when the docs can answer", lambda s: ratio(*s["answered"])),
        ("  refused or asked back when they cannot (gaps, off-topic, vague)", lambda s: ratio(*s["held_back"])),
        ("the 5 chunks held the right page", lambda s: ratio(*s["page"])),
        ("the 5 chunks held the chunk with the answer", lambda s: ratio(*s["evidence"])),
        ("faithful answers (every claim backed by the chunks)", lambda s: ratio(*s["faithful"], ci=True)),
        ("claims backed by the chunks (all claims of all judged answers)", lambda s: ratio(*s["claims"])),
        ("answers with a claim the chunks contradict", lambda s: str(s["contradicted"])),
        ("answers the judge could not judge (failed, or no claims)", lambda s: str(s["judge_errors"] + s["no_claims"])),
        ("answers with no citations, answers citing a source that does not exist", lambda s: f"{s['uncited']}, {s['invalid']}"),
        ("questions that failed (no answer at all)", lambda s: str(s["errors"])),
        ("median time: search, writing the answer, judging", lambda s: f"{s['t_search']}, {s['t_llm']}, {s['t_judge']}"),
        ("tokens, answering (in / out)", lambda s: f"{s['tok_gen'][0]:,} / {s['tok_gen'][1]:,}"),
        ("tokens, judging (in / out)", lambda s: f"{s['tok_judge'][0]:,} / {s['tok_judge'][1]:,}"),
    ]
    out += ["## Results", "", "| | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    out += [f"| {label} | " + " | ".join(fn(S[m]) for m in modes) + " |" for label, fn in rows]

    out += ["", "How to read it:", "",
            "- Faithful is counted only over the answers a mode actually gave. A mode that refuses more has fewer answers to get "
            "wrong, so read this row together with the two 'when' rows above it.",
            "- Faithful is not correct. The answer can be backed by the chunks and still be wrong or incomplete when the chunks "
            "were the wrong ones, which is what the 'held the answer' rows show.",
            "- The judge is a model and can be wrong. The check below tests it, and the .md file of each mode lets you read its "
            "claims and mark where you disagree.", ""]

    out += ["## Judge sanity check", "",
            "Some answers were judged again against the chunks of a different question, where nothing can back them. "
            "A judge that works calls every one of them unfaithful.", ""]
    for m in modes:
        h, t = S[m]["control"]
        flag = "" if (t and h == t) else ("  **<- do not trust the faithfulness numbers until this is explained**" if t else "  (no control run)")
        out.append(f"- {m}: {h} of {t} flagged unfaithful{flag}")

    if len(modes) > 1:
        base = modes[0]
        out += ["", f"## Question by question against `{base}`", "",
                "| mode | measure | gained | lost | questions gained | questions lost |", "|---|---|---|---|---|---|"]
        for m in modes[1:]:
            for label, good in [("right kind of reply", lambda r: bool(r["reply_ok"])),
                                ("faithful", lambda r: bool(r.get("judge")) and r["judge"]["verdict"] == "faithful")]:
                g, l = diff_ids(results[base][0], results[m][0], good)
                out.append(f"| {m} | {label} | {len(g)} | {len(l)} | {', '.join(f'Q{i}' for i in g) or '-'} | "
                           f"{', '.join(f'Q{i}' for i in l) or '-'} |")
        out += ["", "A question counts as 'faithful' only if it was answered and judged. Gaining a question can mean the mode "
                "answered it where the other refused, so check the first measure too."]

    by = {m: {r["id"]: r for r in results[m][0]} for m in modes}
    look = []
    for i in sorted(by[modes[0]]):
        rs = [by[m][i] for m in modes]
        if any(trouble(r) for r in rs) or len({short(r) for r in rs}) > 1:
            look.append(f"| Q{i} | {rs[0]['type']} | " + " | ".join(short(r).replace("|", "/") for r in rs) + " |")
    out += ["", "## Questions to look at", "",
            "Any question where a mode gave the wrong kind of reply, had an unfaithful answer, failed, or where the modes differ. "
            f"The other {n - len(look)} are the same in every mode and fine.", "",
            "| question | type | " + " | ".join(modes) + " |", "|---|---|" + "---|" * len(modes)]
    out += look or ["| (none) | |" + " |" * len(modes)]
    return "\n".join(out)


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def audit(rows, controls, mode):
    """The readable file of one mode: every answer, with the judge's claims, and a line for your own verdict."""
    out = [f"# Answers and judge verdicts, search mode: {mode}", "",
           "Read at least the unfaithful ones, and a few faithful ones, next to the chunks (they are in the .jsonl file). "
           "Where you disagree with the judge, tick the box: that is how you find out how far to trust it.", ""]
    todo = [r for r in rows if trouble(r)]
    out += [f"**Needs your eyes ({len(todo)}):** " + (", ".join(f"Q{r['id']}" for r in todo) or "none"), ""]
    for r in rows:
        out += [f"## Q{r['id']} ({r['type']}): {r['q']}", ""]
        if r.get("error"):
            out += [f"**Failed:** {r['error']}", ""]
            continue
        out += [f"*Expected:* {' or '.join(r['expected'])}. *Got:* **{r['status']}**" + ("" if r["reply_ok"] else "  **<- not what was expected**"), "",
                "> " + r["answer"].replace("\n", "\n> "), "",
                "Chunks the model was given:", ""]
        out += [f"- {c['rank']}. {c['title']} > {c['section']}" + ("  (cited in the answer)" if c["rank"] in r["citations"] else "")
                for c in r["chunks"]]
        out.append("")
        j = r.get("judge")
        if r.get("judge_error"):
            out += [f"**The judge failed:** {r['judge_error']}", ""]
        elif j:
            out += [f"**Judge ({j['model']}): {j['verdict']}**, {j['n_supported']} of {j['n_claims']} claims backed.", ""]
            if j["claims"]:
                out += ["| verdict | claim | source | the words the judge points to | note |", "|---|---|---|---|---|"]
                out += [f"| {c['verdict']} | {esc(c['claim'])} | {c['source'] or '-'} | {esc(c['quote']) or '-'} | {esc(c['note'])} |"
                        for c in j["claims"]]
                out.append("")
            out += ["**Do you agree with the judge?** [ ] yes  [ ] no, it is too strict  [ ] no, it missed something.   Notes: ", ""]
    if controls:
        out += ["## Judge sanity check", ""]
        for c in controls:
            v = c["judge"]["verdict"] if c.get("judge") else "judge failed"
            out.append(f"- the answer to Q{c['id']} judged against the chunks of Q{c['wrong_sources_from']}: {v}"
                       + ("" if v == "unfaithful" else "   **<- should be unfaithful**"))
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------- before spending anything
def preflight(client, gen_model, judge_model, need_answers=True):
    """A few tiny calls before the real run, so a wrong key, a wrong model name or a request the API rejects stops it NOW
    and not after 50 questions. It also tries the judge on one true and one false statement."""
    sky = [{"title": "Sky", "section": "Colour", "url": "https://example.com/sky", "text": "Sky > Colour\n\nThe sky is blue on a clear day."}]
    try:
        if need_answers:
            client.messages.create(model=gen_model, max_tokens=5, messages=[{"role": "user", "content": "Reply with the word OK."}])
        good = judge.judge_answer("What colour is the sky?", sky, "The sky is blue on a clear day [1].", client, judge_model)
        bad = judge.judge_answer("What colour is the sky?", sky, "The sky is green on a clear day [1].", client, judge_model)
    except (anthropic.APIError, judge.JudgeError) as e:
        raise SystemExit(f"preflight failed ({type(e).__name__}): {e}\n"
                         f"Nothing was spent on the real run. Check ANTHROPIC_API_KEY and the model names "
                         f"(answers: {gen_model}, judge: {judge_model}).")
    print(f"preflight: ok. The judge calls a true statement {good['verdict']} and a false one {bad['verdict']}.")
    if good["verdict"] != "faithful" or bad["verdict"] != "unfaithful":
        print("warning: the judge got a trivial case wrong (a true statement should be faithful, a false one unfaithful). "
              "Do not trust the results until you have read judge.py's prompt and the judge's claims.")


# ----------------------------------------------------------------------------- running a mode
def run_mode(mode, questions, a, client, path):
    rag.search("warm up", k=1, mode=mode)                        # load the models now, so the timings below are the search only
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with path.open("w", encoding="utf-8") as fh:
        for i, x in enumerate(questions, 1):
            row = answer_question(x, mode, a.k, client, None, a.judge_model)
            rows.append(row)
            write_line(fh, row)
            j = row.get("judge")
            note = row.get("error") or (f"judge: {j['verdict']} {j['n_supported']}/{j['n_claims']}" if j
                                        else ("judge failed" if row.get("judge_error") else ""))
            print(f"[{i:>2}/{len(questions)}] {mode:<13} Q{x['id']:<3} {row['status'] or 'ERROR':<10} {note}")
        controls = run_controls(pick_control_pairs(rows, a.controls), client, a.judge_model)
        for c in controls:
            write_line(fh, c)
    return rows, controls


def rejudge_mode(mode, path, a, client):
    if not path.exists():
        raise SystemExit(f"--rejudge needs {path} (make it with:  python eval_answers.py --modes {mode})")
    rows, _ = load_mode(path)
    for i, r in enumerate(rows, 1):
        if not r.get("error") and r["status"] in ANSWERED:
            judge_row(r, client, a.judge_model)
            j = r.get("judge")
            print(f"[{i:>2}/{len(rows)}] {mode:<13} Q{r['id']:<3} {('judge: ' + j['verdict']) if j else 'judge failed'}")
    controls = run_controls(pick_control_pairs(rows, a.controls), client, a.judge_model)
    write_mode(path, rows, controls)
    return rows, controls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="eval_questions.jsonl")
    ap.add_argument("--modes", default="vector,hybrid_rerank", help="comma-separated, from: " + ", ".join(rag.MODES))
    ap.add_argument("-k", type=int, default=5, help="chunks given to the model (default 5, what the API uses)")
    ap.add_argument("--limit", type=int, help="only the first N questions: a cheap trial")
    ap.add_argument("--ids", help="only these question numbers, e.g. 1,22,33")
    ap.add_argument("--controls", type=int, default=5, help="answers to judge against the WRONG chunks as a check on the judge (default 5, 0 = none)")
    ap.add_argument("--judge-model", default=judge.JUDGE_MODEL, help=f"default {judge.JUDGE_MODEL} (env RAG_JUDGE_MODEL)")
    ap.add_argument("--rejudge", action="store_true", help="judge the saved answers again; nothing is searched or answered")
    ap.add_argument("--compare", action="store_true", help="no model calls: build the results table from the saved files")
    ap.add_argument("--out", default=None, help="start of every file name (default outputs/eval_answers; the mode is added)")
    a = ap.parse_args()

    modes = a.modes.split(",")
    unknown = [m for m in modes if m not in rag.MODES]
    if unknown or len(set(modes)) != len(modes):
        raise SystemExit(f"--modes must be different names from {list(rag.MODES)}, got {modes}")
    if a.compare and a.rejudge:
        raise SystemExit("--compare and --rejudge do different jobs; use one at a time")

    questions = load_questions(a.questions)
    for x in questions:
        for field in ("id", "q", "expected"):
            if field not in x:
                raise SystemExit(f"{a.questions}: question {x.get('id', '?')} has no '{field}'")
    subset = bool(a.ids or a.limit)
    if a.ids:
        want = {int(i) for i in a.ids.split(",")}
        questions = [x for x in questions if x["id"] in want]
    if a.limit:
        questions = questions[:a.limit]
    if not questions:
        raise SystemExit("no questions selected")
    prefix = a.out or ("outputs/eval_answers_trial" if subset else "outputs/eval_answers")

    written = []
    if a.compare:
        if len(modes) < 2:
            raise SystemExit("--compare puts two or more modes side by side: --modes vector,hybrid_rerank")
        results = load_saved(prefix, modes)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set. In this terminal:  export ANTHROPIC_API_KEY=your-key")
        if rag.LLM_MODEL == a.judge_model:
            print(f"warning: the judge is the same model that writes the answers ({a.judge_model}); a model goes easy on its own "
                  f"writing. Use another with --judge-model.")
        client = anthropic.Anthropic()
        preflight(client, rag.LLM_MODEL, a.judge_model, need_answers=not a.rejudge)
        print(f"answers by {rag.LLM_MODEL}, judged by {a.judge_model}; modes {modes}; {len(questions)} questions"
              + ("  (trial: files go to " + prefix + "_...)" if subset else ""))
        results = {}
        for m in modes:
            path = out_file(prefix, [m], ".jsonl")
            results[m] = rejudge_mode(m, path, a, client) if a.rejudge else run_mode(m, questions, a, client, path)
            md = out_file(prefix, [m], ".md")
            md.write_text(report({m: results[m]}, [m]) + "\n\n" + audit(*results[m], m), encoding="utf-8")
            written += [path, md]

    text = report(results, modes)
    if len(modes) > 1:
        combined = out_file(prefix, modes, ".md")
        combined.parent.mkdir(parents=True, exist_ok=True)
        combined.write_text(text + "\n", encoding="utf-8")
        written.append(combined)
    print("\n" + text + "\n\nSaved:")
    for p in written:
        print("  ", p)


if __name__ == "__main__":
    main()
