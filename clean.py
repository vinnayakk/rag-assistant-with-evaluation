import pathlib, re
from bs4 import BeautifulSoup
from markdownify import markdownify as md

SRC, DST = pathlib.Path("outputs/raw_html"), pathlib.Path("outputs/clean_text_v2")
DST.mkdir(parents=True, exist_ok=True)
MIN_CHARS = 300

for f in SRC.glob("*.html"):
    soup = BeautifulSoup(f.read_text(encoding="utf-8"), "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    title = (soup.find("h1") or soup.title).get_text(strip=True)

    text = md(str(main), heading_style="ATX", code_language="")
    text = re.sub(r"Was this page helpful\?\s*(Yes\s*)?(No\s*)?", "", text)   # feedback widget
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < MIN_CHARS:
        print("SKIPPED (too short):", f.name)
        continue
    (DST / (f.stem + ".md")).write_text(f"# {title}\n\n{text}\n", encoding="utf-8")