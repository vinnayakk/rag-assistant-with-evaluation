import argparse, pathlib, time

import rag
from ten_questions import QUESTIONS, norm

MODES = ["vector", "bm25", "hybrid", "hybrid_rerank"]


def check(q, chunks):
    """-> (ok, text for the table cell). Evidence counts only when it is in a chunk of the right page."""
    ranks, lost = [], []
    for e in q["evidence"]:
        hit = [c["rank"] for c in chunks if (not q["page"] or q["page"] in c["url"]) and norm(e) in norm(c["text"])]
        (ranks if hit else lost).append(min(hit) if hit else e)
    if lost:
        return False, "✗ missing: " + ", ".join(lost)
    return True, "✓ rank " + ",".join(str(r) for r in ranks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("--show", action="store_true", help="list the chunks each mode returned")
    ap.add_argument("--out", default="outputs/compare_retrieval.md")
    a = ap.parse_args()
    modes = a.modes.split(",")

    rows, wins, total_ms = [], {m: 0 for m in modes}, {m: 0.0 for m in modes}
    detail = []
    scored = [q for q in QUESTIONS if q["evidence"]]
    for q in QUESTIONS:
        cells = []
        for m in modes:
            t0 = time.perf_counter()
            chunks = rag.search(q["q"], k=a.k, mode=m)
            total_ms[m] += (time.perf_counter() - t0) * 1000
            if q["evidence"]:
                ok, cell = check(q, chunks)
                wins[m] += ok
            else:
                cell = "(no evidence to check)"
            cells.append(cell)
            detail.append((q, m, chunks))
        rows.append((q, cells))

    head = f"| # | question | " + " | ".join(modes) + " |"
    md = [f"# Search modes compared (top {a.k}, {len(scored)} questions with evidence)", "",
          "Evidence = text that has to be in the retrieved chunks of the right page for any model to answer correctly.", "",
          head, "|" + "---|" * (len(modes) + 2)]
    for q, cells in rows:
        md.append(f"| {q['id']} | {q['q'][:60]} | " + " | ".join(cells) + " |")
    md.append("| | **evidence found** | " + " | ".join(f"**{wins[m]}/{len(scored)}**" for m in modes) + " |")
    md.append("| | avg search time | " + " | ".join(f"{total_ms[m] / len(QUESTIONS):.0f} ms" for m in modes) + " |")
    if a.show:
        md += ["", "## What each mode returned"]
        for q, m, chunks in detail:
            md += ["", f"**{q['id']}. {q['q']}**  (mode: {m})"]
            md += [f"- {c['rank']}. {c['title']} > {c['section']}  ({c['id'].split('::')[-1]})" for c in chunks]
    text = "\n".join(md)
    print(text)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
