import json, pathlib, random, re, sys
sys.path.insert(0, ".")
from chunk import load_counter, fix_code_labels

chunks_path = sys.argv[1] if len(sys.argv) > 1 else "outputs/chunks.jsonl"
src_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "outputs/clean_text_v3")
rows = [json.loads(l) for l in open(chunks_path, encoding="utf-8")]
count = load_counter()

# 1. size: recount every chunk from scratch
sizes = [count(r["text"]) for r in rows]
print(f"1. size      max {max(sizes)} tokens (limit 512), over 500: {sum(s > 500 for s in sizes)}, under 80: {sum(s < 80 for s in sizes)}")

# 2. every code fence opened must be closed inside the same chunk
bad = [r["id"] for r in rows if len(re.findall(r"^\s*```", r["text"], re.M)) % 2]
print(f"2. fences    chunks with an unclosed code block: {len(bad)} {bad[:3]}")

# 3. overlap: the last 6 words of a chunk should reappear near the start of the next chunk of the same section
def words(s):
    return re.findall(r"\w+", s.lower())
ov = pairs = 0
nov = []
for a, b in zip(rows, rows[1:]):
    if a["source"] == b["source"] and a["section"] == b["section"]:
        pairs += 1
        end_of_a = " ".join(words(a["text"])[-6:])
        start_of_b = " ".join(words(b["text"].split("\n\n", 1)[1])[:90])
        if end_of_a in start_of_b:
            ov += 1
        else:
            nov.append(b["id"])
print(f"3. overlap   {ov} of {pairs} consecutive same-section chunks start with the end of the previous one")

# 4. nothing lost: the first and last 6 words of every source line must appear in a chunk of that page
def norm(s):
    return " ".join(re.findall(r"\w+", s.lower()))
lost = total = 0
by_page = {}
for r in rows:
    by_page.setdefault(r["source"], []).append(r["text"])
for f in src_dir.glob("*.md"):
    haystack = norm("\n".join(by_page.get(f.stem, [])))
    for line in fix_code_labels(f.read_text(encoding="utf-8")).splitlines():
        w = norm(line).split()
        if len(w) < 6:
            continue
        for piece in (" ".join(w[:6]), " ".join(w[-6:])):
            total += 1
            lost += piece not in haystack
print(f"4. coverage  {100 * (1 - lost / total):.2f}% of line starts/ends from the pages are present in chunks ({lost} missing)")

# 5. read some chunks yourself
random.seed(1)
for r in random.sample(rows, 3):
    print("\n" + "=" * 70 + f"\n{r['id']}  ({r['n_tokens']} tokens)  {r['url']}\n" + "-" * 70)
    print(r["text"][:900] + (" ..." if len(r["text"]) > 900 else ""))
