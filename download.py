import requests, time, pathlib, re, random
from urllib.parse import urlparse
from bs4 import BeautifulSoup

ROOT = "https://docs.gitlab.com"
SITEMAP = f"{ROOT}/en-us/sitemap.xml"           # English pages only
OUT = pathlib.Path("raw_html"); OUT.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "learning-project (your-email@example.com)"}
LIMIT = 150
MAX_BLOCKS_IN_A_ROW = 5                          # stop if the site starts refusing us

# 1. Read the sitemap and print what we found at each step
xml = requests.get(SITEMAP, headers=HEADERS, timeout=30)
xml.raise_for_status()
urls = [l.text.strip() for l in BeautifulSoup(xml.text, "xml").find_all("loc")]
print(len(urls), "URLs in sitemap")
print("examples:", urls[:3])

# 2. Respect robots.txt: skip review apps and versioned paths like /17.5/
def allowed(u):
    p = urlparse(u).path
    return u.startswith(ROOT) and not p.startswith(("/review-mr", "/upstream-review-mr")) \
           and not re.match(r"^/\d", p)

urls = sorted({u for u in urls if allowed(u)})
print(len(urls), "pages allowed")
random.seed(42)
urls = random.sample(urls, min(LIMIT, len(urls)))
print(len(urls), "pages to fetch")

# 3. Download politely, and stop if the server starts saying no
blocks = 0
for i, u in enumerate(urls, 1):
    name = (re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(u).path).strip("_") or "index")[:150] + ".html"
    path = OUT / name
    if path.exists():
        continue
    r = requests.get(u, headers=HEADERS, timeout=30)
    if r.status_code in (403, 429):
        blocks += 1
        print("BLOCKED", r.status_code, u)
        if blocks >= MAX_BLOCKS_IN_A_ROW:
            print("Server is refusing us. Stopping instead of pushing harder.")
            break
        time.sleep(10)
        continue
    if not r.ok:
        print("FAILED", r.status_code, u)
        continue
    blocks = 0
    path.write_text(r.text, encoding="utf-8")
    time.sleep(1.5)
    if i % 10 == 0:
        print(i, "done")