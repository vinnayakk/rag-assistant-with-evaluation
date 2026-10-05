# Corpus source

- **Company:** GitLab Inc. (public company, NASDAQ: GTLB)
- **Corpus:** GitLab Documentation (public product docs and help pages)
- **Site:** https://docs.gitlab.com
- **Sitemap used:** https://docs.gitlab.com/en-us/sitemap.xml (English pages only)
- **Robots.txt checked:** 2026-10-05. Allows crawling normal doc pages. It disallows
  `/review-mr`, `/upstream-review-mr`, and versioned paths like `/17.5/`.
  My script skips those paths.
- **Download date:** 2026-10-05
- **Pages in sitemap:** 3610 URLs in sitemap
- **Pages downloaded:** 150 (random sample, seed=42, from allowed English pages)
- **Pages kept after cleaning:** 148
- **Crawl behavior:** User-Agent identifies the project, 1.5 s delay between requests,
  stops if the server blocks 5 requests in a row.
- **Purpose:** personal learning project (RAG assistant with evaluation). Not redistributed.
- **License:** GitLab documentation is published openly at the URL above;
  <check and note the license/terms before sharing the data publicly>.

## Folder layout

- `outputs/raw_html/` 150 downloaded pages
- `outputs/clean_text/` first cleaning pass (plain text, 150 files)
- `outputs/clean_text_v2/` Markdown conversion (148 files)
- `outputs/clean_text_v3/` final cleaned corpus (148 files)
- `download.py`, `clean.py`, `tidy.py`: scripts that produce each stage
