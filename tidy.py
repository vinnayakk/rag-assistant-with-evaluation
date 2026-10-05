import pathlib, re, sys

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "clean_text_v2")
DST = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "clean_text_v3")
DST.mkdir(exist_ok=True)
BASE = "https://docs.gitlab.com"
MIN_CHARS = 300            # drop only true stubs

kept = dropped = 0
for f in sorted(SRC.glob("*.md")):
    t = f.read_text(encoding="utf-8")

    # 1. header block "# Title / '/' / --- / # Title" -> single title
    t = re.sub(r"\A(# .+)\n\n/\n\n---\n\n", r"\1\n\n", t)      # drop breadcrumb "/" and rule
    m = re.match(r"\A# (.+)\n\n# (.+)\n", t)                         # drop repeated title
    if m and m.group(1).replace("`", "") == m.group(2).replace("`", ""):
        t = "# " + m.group(1) + "\n" + t[m.end():]

    # 2. image-inside-link ([![alt](img)](img)) -> plain alt text
    t = re.sub(r"\[!\[([^\]]*)\]\([^)]*\)\]\([^)]*\)", r"[Image: \1]", t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"[Image: \1]", t)

    # 3. relative links -> absolute (keeps the link target for citations)
    t = re.sub(r"\]\((/[^)]*)\)", lambda m: f"]({BASE}{m.group(1)})", t)

    # 4. Tier / Offering bullets -> one metadata line
    t = re.sub(r"\* Tier: (.+)\n\* Offering: (.+)\n", r"Tier: \1 | Offering: \2\n", t)

    t = re.sub(r"\n{3,}", "\n\n", t).strip() + "\n"

    if len(t) < MIN_CHARS:
        dropped += 1
        print("DROPPED (stub):", f.name, len(t), "chars")
        continue
    (DST / f.name).write_text(t, encoding="utf-8")
    kept += 1
print(f"kept {kept}, dropped {dropped}")