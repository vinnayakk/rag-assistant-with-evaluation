import eval_recall as ev

# --- norm_path: a full URL, a path with and without the trailing slash, a query string and capitals all match
assert ev.norm_path("https://docs.gitlab.com/user/version/") == "/user/version"
assert ev.norm_path("/user/version") == "/user/version"
assert ev.norm_path("https://docs.gitlab.com/User/Version/?x=1#top") == "/user/version"

# --- wilson: 20 of 40 -> about 35% to 65%; 0 of 0 does not crash; all 10 of 10 still has a lower bound below 100%
lo, hi = ev.wilson(20, 40)
assert 0.34 < lo < 0.36 and 0.64 < hi < 0.66, (lo, hi)
assert ev.wilson(0, 0) == (0.0, 0.0)
lo, hi = ev.wilson(10, 10)
assert 0.70 < lo < 0.73 and hi > 0.99, (lo, hi)

# --- first_rank and evidence_rank
chunks = [
    {"url": "https://docs.gitlab.com/a/", "text": "nothing here"},
    {"url": "https://docs.gitlab.com/b/", "text": "The answer is 42. Also: blue"},
    {"url": "https://docs.gitlab.com/b/", "text": "more text   about   Green"},
]
assert ev.first_rank(chunks, ["/b/"]) == 2
assert ev.first_rank(chunks, ["/c/"]) is None
assert ev.first_rank(chunks, ["/a/", "/b/"]) == 1                       # any of the right pages counts
assert ev.evidence_rank(chunks, ["/b/"], ["answer is 42"]) == 2
assert ev.evidence_rank(chunks, ["/b/"], ["answer is 42", "about green"]) == 3   # needs both: the later one decides; spaces and case ignored
assert ev.evidence_rank(chunks, ["/b/"], ["answer is 43"]) is None
assert ev.evidence_rank(chunks, ["/a/"], ["answer is 42"]) is None      # the text is there, but on the wrong page
assert ev.evidence_rank(chunks, ["/b/"], []) is None                    # no evidence strings: not scored

# --- share
rows = [{"page_rank": 1}, {"page_rank": 6}, {"page_rank": None}, {"page_rank": 5}]
assert ev.share(rows, "page_rank", 5) == (2, 4)
assert ev.share(rows, "page_rank", 10) == (3, 4)

# --- file names: made from the modes, so two different runs can never get the same name
assert str(ev.out_file("outputs/eval_recall", ["vector"], ".md")) == "outputs/eval_recall_vector.md"
assert str(ev.out_file("outputs/eval_recall", ["hybrid_rerank"], ".jsonl")) == "outputs/eval_recall_hybrid_rerank.jsonl"
assert str(ev.out_file("outputs/eval_recall", ["vector", "bm25"], ".md")) == "outputs/eval_recall_vector+bm25.md"
names = {str(ev.out_file("o/e", [m], ".md")) for m in ev.MODES}
assert len(names) == len(ev.MODES), "every mode needs its own file name"
assert str(ev.out_file("o/e", ["vector", "bm25"], ".md")) not in names

# --- saving and loading: one file per mode, and --compare only keeps the questions every mode has
import json, pathlib, tempfile
def row(i, page_rank, evidence_rank=1, has_evidence=True, type_="direct"):
    return dict(id=i, type=type_, q=f"question {i}", pages=["/a/"], ms=10.0 + i, page_rank=page_rank,
                evidence_rank=evidence_rank, has_evidence=has_evidence, top=[("https://docs.gitlab.com/a/", "S")])
with tempfile.TemporaryDirectory() as tmp:
    prefix = f"{tmp}/eval_recall"
    a_rows = [row(1, 1), row(2, 3, None), row(3, None, None)]
    b_rows = [row(1, 1), row(2, 1), row(3, 2, 2), row(4, 1)]          # b also has a question 4 that a never saw
    p1, p2 = ev.save_mode(prefix, "vector", a_rows), ev.save_mode(prefix, "bm25", b_rows)
    assert p1.name == "eval_recall_vector.jsonl" and p2.name == "eval_recall_bm25.jsonl"
    ev.save_mode(prefix, "bm25", b_rows)                               # same mode again: replaces its own file only
    assert p1.exists() and p2.exists() and len(p1.read_text().splitlines()) == 3
    got = ev.load_saved(prefix, ["vector", "bm25"])
    assert [r["id"] for r in got["bm25"]] == [1, 2, 3]                 # question 4 dropped: vector does not have it
    try:
        ev.load_saved(prefix, ["vector", "hybrid"])                    # no hybrid file yet: say so, do not guess
        raise AssertionError("a missing file should stop the comparison")
    except SystemExit as e:
        assert "eval_recall_hybrid.jsonl" in str(e) and "--modes hybrid" in str(e)

    # --- the combined report
    text = ev.report(got, ["vector", "bm25"], [1, 3, 5, 10], 5, 2, False)
    assert "| vector | **2/3 (67%)**" in text and "| bm25 | **3/3 (100%)**" in text, text
    assert "| bm25 | 1 | 0 | Q3 | - |" in text, text                   # bm25 gains Q3 against vector, loses nothing
    assert "| Q2 | direct | 3 / - | 1 / 1 |" in text and "| Q3 | direct | - / - | 2 / 2 |" in text, text
    single = ev.report({"vector": got["vector"]}, ["vector"], [1, 3, 5, 10], 5, 2, False)
    assert "Question by question" not in single and "| vector | **2/3 (67%)**" in single

# --- ok / cell
assert ev.ok({"page_rank": 5}, "page_rank", 5) and not ev.ok({"page_rank": 6}, "page_rank", 5) and not ev.ok({"page_rank": None}, "page_rank", 5)
assert ev.cell(row(1, 2, None)) == "2 / -" and ev.cell(row(1, None, None, False)) == "- / n/a"
print("all eval_recall tests passed")
