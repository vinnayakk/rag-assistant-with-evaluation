import argparse, difflib, json, math, pathlib, re, statistics, time
from collections import defaultdict

import rag

MODES = ["vector", "bm25", "hybrid", "hybrid_rerank"]
REPLIES = {"answered", "refused", "clarifying"}


# ----------------------------------------------------------------------------- small helpers
def norm(s):
    return re.sub(r"\s+", " ", s).lower()


def norm_path(url):
    """'https://docs.gitlab.com/user/version/?x=1' -> '/user/version'   (so '/user/version/' and the full URL match)"""
    path = re.sub(r"^https?://[^/]+", "", url).split("?")[0].split("#")[0]
    return path.rstrip("/").lower()


def wilson(hits, n, z=1.96):
    """95% interval for a share hits/n. With 40 questions it is wide."""
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - half) / d, (centre + half) / d


def load_questions(path):
    rows = []
    for no, line in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}, line {no}: not valid JSON ({e}). Every line must be one complete JSON object.")
    return rows


def out_file(prefix, modes, suffix):
    """The file name is made from the modes it holds:
         ('outputs/eval_recall', ['vector'], '.md')                    -> outputs/eval_recall_vector.md
         ('outputs/eval_recall', ['vector', 'bm25'], '.md')            -> outputs/eval_recall_vector+bm25.md
    Two different sets of modes can never get the same name, so one run cannot replace another's file."""
    return pathlib.Path(f"{prefix}_{'+'.join(modes)}{suffix}")


# ----------------------------------------------------------------------------- validate
def corpus_by_page():
    """-> {normalised path: [text of each chunk of that page]}"""
    got = rag.get_collection().get(include=["documents", "metadatas"])
    pages = defaultdict(list)
    for doc, meta in zip(got["documents"], got["metadatas"]):
        pages[norm_path(meta["url"])].append(doc)
    return {p: [norm(t) for t in texts] for p, texts in pages.items()}


def validate(questions):
    problems = []
    pages = corpus_by_page()
    seen = set()
    for x in questions:
        i = x.get("id")
        tag = f"Q{i}"
        for field in ("id", "q", "type", "pages", "evidence", "expected"):
            if field not in x:
                problems.append(f"{tag}: missing field '{field}'")
        if i in seen:
            problems.append(f"{tag}: id used twice")
        seen.add(i)
        if not str(x.get("q", "")).strip():
            problems.append(f"{tag}: empty question")
        bad = set(x.get("expected", [])) - REPLIES
        if bad or not x.get("expected"):
            problems.append(f"{tag}: expected must be a list from {sorted(REPLIES)}, got {x.get('expected')}")
        if x.get("evidence") and not x.get("pages"):
            problems.append(f"{tag}: has evidence but no page")
        for p in x.get("pages", []):
            key = norm_path(p)
            if key not in pages:
                close = difflib.get_close_matches(key, list(pages), n=3, cutoff=0.6)     # catches typos
                problems.append(f"{tag}: page {p} is not in the database" + (f" (did you mean {close}?)" if close else ""))
                continue
            for e in x.get("evidence", []):
                if not any(norm(e) in chunk for chunk in pages[key]):       # one chunk must hold all of it
                    problems.append(f"{tag}: evidence {e!r} is not inside a single chunk of {p}")
    scored = sum(1 for x in questions if x.get("pages"))
    print(f"{len(questions)} questions, {scored} with a page, {len(questions) - scored} without (gaps, off-topic, vague)")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)
    print("All pages exist in the database and every evidence string is inside one chunk of its page.")


# ----------------------------------------------------------------------------- scoring
def first_rank(chunks, pages):
    """Rank (1 = best) of the first chunk that belongs to one of the right pages; None if there is none."""
    want = {norm_path(p) for p in pages}
    for rank, c in enumerate(chunks, 1):
        if norm_path(c["url"]) in want:
            return rank
    return None


def evidence_rank(chunks, pages, evidence):
    """Smallest k at which EVERY evidence string has appeared in a chunk of the right page; None if some never does.
    No evidence strings -> None (the question is left out of the evidence score)."""
    if not evidence:
        return None
    want = {norm_path(p) for p in pages}
    needed = 0
    for e in evidence:
        hit = [r for r, c in enumerate(chunks, 1) if norm_path(c["url"]) in want and norm(e) in norm(c["text"])]
        if not hit:
            return None
        needed = max(needed, min(hit))
    return needed


def run(questions, modes, ks):
    kmax = max(ks)
    for m in modes:                                    # load the models once, so the timings below measure search only
        rag.search("warm up", k=1, mode=m)
    scored = [x for x in questions if x["pages"]]
    results = {m: [] for m in modes}
    for m in modes:
        for x in scored:
            t0 = time.perf_counter()
            chunks = rag.search(x["q"], k=kmax, mode=m)
            ms = (time.perf_counter() - t0) * 1000
            results[m].append(dict(
                id=x["id"], type=x["type"], q=x["q"], pages=x["pages"], ms=ms,
                page_rank=first_rank(chunks, x["pages"]),
                evidence_rank=evidence_rank(chunks, x["pages"], x.get("evidence", [])),
                has_evidence=bool(x.get("evidence")),
                top=[(c["url"], c["section"]) for c in chunks[:5]]))
    return results


def share(rows, key, k):
    hits = sum(1 for r in rows if r[key] is not None and r[key] <= k)
    return hits, len(rows)


def ok(r, key, k):
    return r[key] is not None and r[key] <= k


def pct(h, n):
    return f"{100 * h / n:.0f}%" if n else "-"


# ----------------------------------------------------------------------------- saved results (what --compare reads)
def save_mode(prefix, mode, rows):
    path = out_file(prefix, [mode], ".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"mode": mode, **r}, ensure_ascii=False) + "\n")
    return path


def load_saved(prefix, modes):
    """Read outputs/eval_recall_<mode>.jsonl for each mode. Only the questions that EVERY mode has are kept,
    so that the side-by-side numbers are about the same questions."""
    results, missing = {}, []
    for m in modes:
        path = out_file(prefix, [m], ".jsonl")
        if not path.exists():
            missing.append(f"  - {path}   (make it with:  python eval_recall.py --modes {m})")
            continue
        results[m] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if missing:
        raise SystemExit("--compare needs one saved result file per mode, and these are missing:\n" + "\n".join(missing))
    common = set.intersection(*(set(r["id"] for r in rows) for rows in results.values()))
    for m in modes:
        if len(results[m]) != len(common):
            print(f"note: {m} has {len(results[m])} questions but only {len(common)} are in every file; "
                  f"comparing those {len(common)}. Re-run the modes that are out of date.")
        results[m] = [r for r in results[m] if r["id"] in common]
    if not common:
        raise SystemExit("the saved files have no question in common")
    return results


# ----------------------------------------------------------------------------- the report
def paired(results, modes, key, k, only_evidence):
    """For each mode after the first: the questions it gets right that the first mode misses, and the other way round."""
    base = modes[0]
    pick = (lambda rows: [r for r in rows if r["has_evidence"]]) if only_evidence else (lambda rows: rows)
    b = {r["id"]: r for r in pick(results[base])}
    lines = ["| mode | gained | lost | questions gained | questions lost |", "|---|---|---|---|---|"]
    for m in modes[1:]:
        gained = [r["id"] for r in pick(results[m]) if ok(r, key, k) and not ok(b[r["id"]], key, k)]
        lost = [r["id"] for r in pick(results[m]) if ok(b[r["id"]], key, k) and not ok(r, key, k)]
        lines.append(f"| {m} | {len(gained)} | {len(lost)} | {', '.join(f'Q{i}' for i in gained) or '-'} | "
                     f"{', '.join(f'Q{i}' for i in lost) or '-'} |")
    return lines


def cell(r):
    """'page rank / evidence rank' for one question in one mode; '-' = not in the top results at all, n/a = no evidence strings"""
    p = "-" if r["page_rank"] is None else str(r["page_rank"])
    e = "n/a" if not r["has_evidence"] else ("-" if r["evidence_rank"] is None else str(r["evidence_rank"]))
    return f"{p} / {e}"


def report(results, modes, ks, k, n_unscored, show_misses):
    n = len(results[modes[0]])
    out = [f"# Retrieval evaluation: {n} questions that have a page ({n_unscored} more have none and are not scored here)", "",
           "Page recall = the right page is among the top k chunks. Evidence recall = the chunk with the answer is. "
           "The interval is a 95% Wilson interval for page recall: with this few questions it is wide, "
           "so a gap between two modes smaller than the intervals is not evidence of anything on its own.", ""]

    out += [f"## Headline: top {k}", "",
            "| mode | page recall@%d | 95%% interval | evidence recall@%d | MRR | median search |" % (k, k), "|---|---|---|---|---|---|"]
    for m in modes:
        rows = results[m]
        h, t = share(rows, "page_rank", k)
        lo, hi = wilson(h, t)
        ev = [r for r in rows if r["has_evidence"]]
        eh, et = share(ev, "evidence_rank", k)
        mrr = sum(1 / r["page_rank"] for r in rows if r["page_rank"]) / len(rows)
        out.append(f"| {m} | **{h}/{t} ({pct(h, t)})** | {100 * lo:.0f}% to {100 * hi:.0f}% | {eh}/{et} ({pct(eh, et)}) | "
                   f"{mrr:.2f} | {statistics.median(r['ms'] for r in rows):.0f} ms |")
    out += ["", "Search time is the median over the questions (the middle one), so one slow search cannot distort it. "
                "It is the search only: no model loading, no answer."]

    out += ["", "## Page recall at different k", "", "| mode | " + " | ".join(f"@{x}" for x in ks) + " |", "|---|" + "---|" * len(ks)]
    for m in modes:
        out.append(f"| {m} | " + " | ".join(pct(*share(results[m], "page_rank", x)) for x in ks) + " |")

    n_ev = sum(1 for r in results[modes[0]] if r["has_evidence"])
    out += ["", f"## Evidence recall at different k ({n_ev} questions have evidence strings)", "",
            "| mode | " + " | ".join(f"@{x}" for x in ks) + " |", "|---|" + "---|" * len(ks)]
    for m in modes:
        ev = [r for r in results[m] if r["has_evidence"]]
        out.append(f"| {m} | " + " | ".join(pct(*share(ev, "evidence_rank", x)) for x in ks) + " |")

    types = sorted({r["type"] for r in results[modes[0]]})
    out += ["", f"## Page recall@{k} by type of question", "", "| type | n | " + " | ".join(modes) + " |", "|---|---|" + "---|" * len(modes)]
    for t in types:
        cells = []
        for m in modes:
            rows = [r for r in results[m] if r["type"] == t]
            h, tot = share(rows, "page_rank", k)
            cells.append(f"{h}/{tot}")
        n_t = sum(1 for r in results[modes[0]] if r["type"] == t)
        out.append(f"| {t} | {n_t} | " + " | ".join(cells) + " |")

    if len(modes) > 1:
        note = ("Counting questions that changed is the fair way to compare two modes on the same questions. "
                "If a mode gains 3 and loses 3, it is not better, just different.")
        out += ["", f"## Question by question against `{modes[0]}`: page recall@{k}", "", note, ""] + paired(results, modes, "page_rank", k, False)
        out += ["", f"## Question by question against `{modes[0]}`: evidence recall@{k}", ""] + paired(results, modes, "evidence_rank", k, True)

        rows_by_id = {m: {r["id"]: r for r in results[m]} for m in modes}
        odd = []
        for i in sorted(rows_by_id[modes[0]]):
            rs = [rows_by_id[m][i] for m in modes]
            cells = [cell(r) for r in rs]
            fails = any(not ok(r, "page_rank", k) or (r["has_evidence"] and not ok(r, "evidence_rank", k)) for r in rs)
            if fails or len(set(cells)) > 1:
                odd.append(f"| Q{i} | {rs[0]['type']} | " + " | ".join(cells) + " |")
        out += ["", "## Where the modes differ, or any mode misses", "",
                "Each cell is: rank of the first chunk from the right page / rank at which the answer chunk has appeared. "
                "`-` means not in the top results at all; `n/a` means the question has no evidence strings. "
                f"{len(rows_by_id[modes[0]]) - len(odd)} questions are not listed because every mode ranks them the same and finds them in the top {k}.", "",
                "| question | type | " + " | ".join(modes) + " |", "|---|---|" + "---|" * len(modes)] + (odd or ["| (none) | | " + " | ".join("" for _ in modes) + " |"])

    out += ["", f"## Misses at top {k} (right page not found)", ""]
    for m in modes:
        miss = [r for r in results[m] if not ok(r, "page_rank", k)]
        out.append(f"**{m}**: {len(miss)} missed" + (": " + ", ".join(f"Q{r['id']}" for r in miss) if miss else ""))
        for r in miss:                                # the file always lists them; the screen only with --show-misses
            out.append(f"- Q{r['id']} ({r['type']}) {r['q']}")
            out.append(f"  - wanted {', '.join(r['pages'])}" + ("" if r["page_rank"] is None else f" (found later, at rank {r['page_rank']})"))
            out.append("  - got: " + "; ".join(f"{norm_path(u)} > {s}" for u, s in r["top"][:3]))
        out.append("")

    out += [f"## Misses at top {k} (right page found, the chunk with the answer not)", ""]
    for m in modes:
        miss = [r for r in results[m] if ok(r, "page_rank", k) and r["has_evidence"] and not ok(r, "evidence_rank", k)]
        out.append(f"**{m}**: {len(miss)}" + (": " + ", ".join(f"Q{r['id']}" for r in miss) if miss else ""))
        for r in miss:
            later = "not in the top results" if r["evidence_rank"] is None else f"at rank {r['evidence_rank']}"
            out.append(f"- Q{r['id']} ({r['type']}) {r['q']}")
            out.append(f"  - right page at rank {r['page_rank']}, the answer chunk {later}")
            out.append("  - got: " + "; ".join(f"{norm_path(u)} > {s}" for u, s in r["top"][:3]))
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="eval_questions.jsonl")
    ap.add_argument("--validate", action="store_true", help="only check the question file against the database")
    ap.add_argument("--modes", default=",".join(MODES), help="comma-separated, from: " + ", ".join(MODES))
    ap.add_argument("--compare", action="store_true",
                    help="no searching: build the combined report for --modes from the saved outputs/eval_recall_<mode>.jsonl files")
    ap.add_argument("-k", type=int, default=5, help="the k for the headline table (default 5)")
    ap.add_argument("--ks", default="1,3,5,10", help="k values for the recall-at-k tables")
    ap.add_argument("--show-misses", action="store_true", help="print the full report on screen, including the misses")
    ap.add_argument("--out", default="outputs/eval_recall",
                    help="start of every file name; the mode(s) are added: outputs/eval_recall_<mode>.md (default outputs/eval_recall)")
    a = ap.parse_args()

    questions = load_questions(a.questions)
    modes = a.modes.split(",")
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        raise SystemExit(f"unknown mode(s): {unknown}. Choose from {MODES}  (note: --modes vector,bm25, not --vector)")
    if len(set(modes)) != len(modes):
        raise SystemExit(f"a mode is listed twice: {modes}")
    ks = sorted({int(x) for x in a.ks.split(",")} | {a.k})
    n_unscored = sum(1 for x in questions if not x.get("pages"))

    written = []
    if a.compare:
        if a.validate:
            raise SystemExit("--compare and --validate do different jobs; use one at a time")
        if len(modes) < 2:
            raise SystemExit("--compare puts two or more modes side by side: --modes vector,bm25")
        results = load_saved(a.out, modes)
        n_file, n_now = len(results[modes[0]]), sum(1 for x in questions if x.get("pages"))
        if n_file != n_now:
            print(f"note: the saved results hold {n_file} scored questions but {a.questions} now has {n_now}. "
                  f"If you changed the questions, re-run the modes.")
    else:
        validate(questions)
        if a.validate:
            return
        results = run(questions, modes, ks)
        for m in modes:                               
            single = {m: results[m]}
            md = out_file(a.out, [m], ".md")
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(report(single, [m], ks, a.k, n_unscored, a.show_misses) + "\n", encoding="utf-8")
            written += [md, save_mode(a.out, m, results[m])]

    text = report(results, modes, ks, a.k, n_unscored, a.show_misses)
    if len(modes) > 1:                                # the side-by-side report, named after all the modes in it
        combined = out_file(a.out, modes, ".md")
        combined.parent.mkdir(parents=True, exist_ok=True)
        combined.write_text(text + "\n", encoding="utf-8")
        written.append(combined)

    print(text if a.show_misses else text.split("## Misses")[0])
    print("\nSaved:")
    for p in written:
        print("  ", p)


if __name__ == "__main__":
    main()
