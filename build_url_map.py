"""Step 0: map each cleaned file back to its real page URL (for citations).
Reads the canonical URL stored inside every raw HTML page. No network needed.

Usage: python build_url_map.py outputs/raw_html outputs/url_map.json
"""
import json, pathlib, sys
from bs4 import BeautifulSoup

raw_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/raw_html")
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "outputs/url_map.json")

url_map, missing = {}, []
for f in sorted(raw_dir.glob("*.html")):
    soup = BeautifulSoup(f.read_text(encoding="utf-8"), "lxml")
    link = soup.find("link", rel="canonical")
    og = soup.find("meta", property="og:url")
    url = (link and link.get("href")) or (og and og.get("content"))
    if url:
        url_map[f.stem] = url
    else:
        missing.append(f.name)

out.write_text(json.dumps(url_map, indent=2), encoding="utf-8")
print(f"{len(url_map)} URLs saved to {out}; {len(missing)} pages had none: {missing}")
