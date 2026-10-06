"""Step 1: split the cleaned Markdown pages into ~500-token chunks with overlap.

Usage:
    python chunk.py outputs/clean_text_v3 outputs/url_map.json outputs/chunks.jsonl
    python chunk.py ... --target 450 --max 500 --overlap 50      (defaults shown)

How it works
  1. Each page is split at "##" headings (a section is the natural unit of meaning).
  2. Inside a section, text is cut into blocks: paragraphs, lists, tables, code fences.
     Blocks are never cut in the middle unless a single block is too big to fit.
  3. Blocks are packed into a chunk until it reaches ~TARGET tokens (never above MAX).
  4. The next chunk starts with the last ~OVERLAP tokens of the previous one.
  5. Every chunk is stored with its page title, section, URL and token count.

Token counting uses the SAME tokenizer as the embedding model (BAAI/bge-small-en-v1.5,
max input 512 tokens), so "500 tokens" really means 500 tokens for that model.
"""
import argparse, json, os, pathlib, re, statistics

# ----------------------------------------------------------------------------- tokens
def load_counter():
    """Return a function that counts tokens the way the embedding model does."""
    if os.environ.get("CHUNK_COUNTER") == "approx":      # offline stand-in, for testing only
        pat = re.compile(r"[A-Za-z]+|\d|[^\sA-Za-z\d]")
        return lambda s: len(pat.findall(s))
    from tokenizers import Tokenizer                      # installed together with chromadb
    tok = Tokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
    tok.no_truncation()                                   # count the real length, never cap it at 512
    return lambda s: len(tok.encode(s, add_special_tokens=False).ids)


# ----------------------------------------------------------------------------- parsing
FENCE = re.compile(r"^\s*```")

LANGS = "shell|bash|yaml|json|sql|ruby|markdown|console|graphql|groovy|toml|javascript|powershell|conf|python|xml|go|text|plaintext|html|ini|dockerfile"

def fix_code_labels(md):
    """The scraped pages show the code language as a lone line before the fence ('shell', blank, ```).
    Turn that back into a proper fence: ```shell"""
    return re.sub(rf"^([ \t]*)({LANGS})\n\n\1```\n", r"\1```\2\n", md, flags=re.M)   # also inside list items


def split_sections(md):
    """-> (title, tier_line, [(section_name, body_text), ...]). Splits on '## ' outside code fences."""
    lines = fix_code_labels(md).splitlines()
    title, tier = "", ""
    sections, name, buf, in_code = [], "Introduction", [], False
    for line in lines:
        if FENCE.match(line):
            in_code = not in_code
        if not in_code and line.startswith("# ") and not title:
            title = line[2:].strip().strip("`")
            continue
        if not in_code and line.startswith("## "):
            sections.append((name, "\n".join(buf).strip()))
            name, buf = line[3:].strip().strip("`"), []
            continue
        if line.startswith("Tier: ") and "| Offering:" in line and not tier:
            tier = line.strip()
        buf.append(line)
    sections.append((name, "\n".join(buf).strip()))
    return title, tier, [(n, b) for n, b in sections if b]


def split_blocks(body):
    """Cut a section body into blocks at blank lines, keeping ``` fences in one piece."""
    blocks, cur, in_code = [], [], False
    for line in body.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        if not line.strip() and not in_code:
            if cur:
                blocks.append("\n".join(cur)); cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


# ----------------------------------------------------------------------------- oversize blocks
def greedy_join(atoms, sep, cap, count):
    """Group atoms into pieces of at most `cap` tokens (an atom larger than cap is hard-split by words)."""
    pieces, cur = [], []
    def flush():
        nonlocal cur
        if cur:
            pieces.append(sep.join(cur)); cur = []
    for a in atoms:
        if count(a) > cap:                                   # last resort: split by words
            flush()
            words, w = a.split(" "), []
            for word in words:
                if w and count(" ".join(w + [word])) > cap:
                    pieces.append(" ".join(w)); w = []
                w.append(word)
            if w:
                pieces.append(" ".join(w))
            continue
        if cur and count(sep.join(cur + [a])) > cap:
            flush()
        cur.append(a)
    flush()
    return pieces


def split_big_block(block, cap, count):
    """Split one block that is larger than `cap` tokens, in the way that hurts meaning least."""
    lines = block.splitlines()
    if FENCE.match(lines[0]):                                # code: split by lines, re-wrap each piece
        opener = lines[0]
        inner = [l for l in lines[1:] if not FENCE.match(l)]
        room = cap - count(opener) - 2
        indent = opener[:len(opener) - len(opener.lstrip())]          # code inside a list item is indented
        return [f"{opener}\n{p}\n{indent}```" for p in greedy_join(inner, "\n", max(room, 20), count)]
    if lines[0].lstrip().startswith("|") and len(lines) > 2:  # table: repeat the header in each piece
        head, rows = "\n".join(lines[:2]), lines[2:]
        room = cap - count(head) - 1
        return [head + "\n" + p for p in greedy_join(rows, "\n", max(room, 20), count)]
    atoms = []                                               # text / list: lines, then sentences
    for l in lines:
        atoms += [l] if count(l) <= cap else re.split(r"(?<=[.!?])\s+", l)
    return greedy_join(atoms, "\n", cap, count)


# ----------------------------------------------------------------------------- packing
def make_tail(units, overlap, count):
    """Last whole blocks of the previous chunk that fit in `overlap` tokens. If even the last block is
    too long, fall back to its last sentences (never cut code or tables in half)."""
    tail, tot = [], 0
    for prev in reversed(units):
        pt = count(prev)
        if tot + pt <= overlap:
            tail.insert(0, prev); tot += pt
            continue
        if not tail and not FENCE.match(prev) and not prev.lstrip().startswith("|"):
            sentences = re.split(r"(?<=[.!?])\s+", prev)
            keep = []
            for s in reversed(sentences):
                if tot + count(s) > overlap:
                    break
                keep.insert(0, s); tot += count(s)
            if keep:
                tail.insert(0, " ".join(keep))
        break
    return tail


def pack_section(blocks, target, maxtok, overlap, min_tokens, count):
    """Pack blocks into chunks. Returns a list of text bodies for one section."""
    units = []
    for b in blocks:
        units += [b] if count(b) <= maxtok else split_big_block(b, maxtok, count)
    units = [u for u in units if u.strip()]

    chunks = []                                              # each: {"units": [...], "n_overlap": int}
    cur, n_over = [], 0

    def size(us):
        return sum(count(u) for u in us) + 2 * max(len(us) - 1, 0)   # +2 ~ the blank line between blocks

    for u in units:
        t = count(u)
        too_big = size(cur) + t + 2 > target
        tiny_but_fits = size(cur) < min_tokens and size(cur) + t + 2 <= maxtok   # keep a lead-in paragraph with its code
        if cur and too_big and not tiny_but_fits:
            chunks.append({"units": cur, "n_overlap": n_over})
            tail = make_tail(cur, overlap, count)           # overlap = the end of the previous chunk
            cur, n_over = tail, len(tail)
        while cur and size(cur) + t + 2 > maxtok:            # never exceed the hard limit
            cur.pop(0); n_over = max(n_over - 1, 0)
        cur.append(u)
    if cur:
        chunks.append({"units": cur, "n_overlap": n_over})

    # a tiny last chunk (only overlap + a few words) is merged into the previous one if it fits
    if len(chunks) > 1:
        last, prev = chunks[-1], chunks[-2]
        fresh = last["units"][last["n_overlap"]:]
        if size(fresh) < min_tokens and size(prev["units"] + fresh) <= maxtok:
            prev["units"] = prev["units"] + fresh
            chunks.pop()
    return ["\n\n".join(c["units"]) for c in chunks]


def chunk_page(md, target, maxtok, overlap, min_tokens, count):
    """-> (title, tier, [(section_name, chunk_body), ...])"""
    title, tier, sections = split_sections(md)
    merged = []
    for name, body in sections:                              # tiny intro + next section -> one section
        if merged and count(merged[-1][1]) < min_tokens:
            pname, pbody = merged[-1]
            merged[-1] = (pname, f"{pbody}\n\n## {name}\n\n{body}")
        else:
            merged.append((name, body))
    sections = merged
    out = []
    for name, body in sections:
        header = f"{title} > {name}"
        budget = lambda n: n - count(header) - 4
        bodies = pack_section(split_blocks(body), budget(target), budget(maxtok), overlap, min_tokens, count)
        total = sum(count(b) for b in bodies)
        # a very short section is appended to the previous chunk of the page (keeps its heading)
        if out and total < min_tokens and len(bodies) == 1:
            pname, pbody = out[-1]
            merged = f"{pbody}\n\n## {name}\n\n{bodies[0]}"
            if count(f"{title} > {pname}\n\n{merged}") <= maxtok:
                out[-1] = (pname, merged)
                continue
        out += [(name, b) for b in bodies]
    return title, tier, out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default="outputs/clean_text_v3")
    ap.add_argument("url_map", nargs="?", default="outputs/url_map.json")
    ap.add_argument("dst", nargs="?", default="outputs/chunks.jsonl")
    ap.add_argument("--target", type=int, default=450, help="aim for this many tokens per chunk")
    ap.add_argument("--max", type=int, default=500, help="hard upper limit (model limit is 512)")
    ap.add_argument("--overlap", type=int, default=50, help="tokens repeated at the start of the next chunk")
    ap.add_argument("--min", type=int, default=80, help="merge pieces smaller than this")
    a = ap.parse_args()

    count = load_counter()
    urls = json.loads(pathlib.Path(a.url_map).read_text(encoding="utf-8")) if pathlib.Path(a.url_map).exists() else {}
    files = sorted(pathlib.Path(a.src).glob("*.md"))
    rows = []
    for f in files:
        title, tier, pieces = chunk_page(f.read_text(encoding="utf-8"), a.target, a.max, a.overlap, a.min, count)
        if not title.strip():                                # a page with an empty <h1>: build a title from its URL
            path = urls.get(f.stem, "").split("//", 1)[-1].split("/", 1)[-1].strip("/")
            title = path.replace("/", " / ").replace("_", " ").replace("-", " ") or f.stem
        for i, (section, body) in enumerate(pieces):
            text = f"{title} > {section}\n\n{body}"          # this is what gets embedded
            rows.append({
                "id": f"{f.stem}::{i:03d}",
                "text": text,
                "n_tokens": count(text),
                "source": f.stem,
                "title": title,
                "section": section,
                "url": urls.get(f.stem, ""),
                "tier": tier,
                "chunk_index": i,
            })
    out = pathlib.Path(a.dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = sorted(r["n_tokens"] for r in rows)
    print(f"{len(files)} pages -> {len(rows)} chunks  (saved to {out})")
    print(f"tokens per chunk: min {n[0]}, median {int(statistics.median(n))}, "
          f"p95 {n[int(len(n) * .95)]}, max {n[-1]}  (model limit 512)")
    print(f"chunks over {a.max}: {sum(x > a.max for x in n)} | under {a.min}: {sum(x < a.min for x in n)}")


if __name__ == "__main__":
    main()
