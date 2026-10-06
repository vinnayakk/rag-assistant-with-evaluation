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
- **Pages downloaded:** 150 (random sample, seed=42, from allowed English pages). The sitemap
  changes over time, so running `download.py` again can give a different 150 pages.
- **Pages kept after cleaning:** 148 (2 stubs under 300 characters dropped)
- **Pages in the final corpus:** 147 (I moved `runner_agents.md` to `outputs/excluded/` with a shell command,
  not a script: empty title, and its content is writing-style instructions for AI tools, not
  product docs)
- **Crawl behavior:** User-Agent names the project (the contact address in it is a placeholder), 1.5 s delay between requests,
  stops if the server blocks 5 requests in a row.
- **Purpose:** personal learning project (RAG assistant with evaluation). The downloaded
  pages are not redistributed: `outputs/` is in `.gitignore`.
- **License:** GitLab documentation is published under
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) (checked 2026-10-06).
  Attribution: documentation text is © GitLab Inc. If I ever publish cleaned text, chunks or
  test output that contains it, they are adaptations, so they need that attribution and the same
  CC BY-SA 4.0 licence. The code in this repository is MIT (see `LICENSE`).
  Not affiliated with GitLab.

## Folder layout (all inside `outputs/`, none of it is in git)

- `raw_html/` 150 downloaded pages (`download.py`)
- `clean_text_v2/` Markdown conversion, 148 files (`clean.py`)
- `clean_text_v3/` final cleaned corpus, 147 files after the exclusion (`tidy.py`)
- `excluded/` pages I removed from the corpus (`runner_agents.md`)
- `url_map.json` real URL of each page, for citations (`build_url_map.py`)
- `chunks.jsonl` 1,461 chunks (`chunk.py`)
- `chroma_db/` the vector database (`embed_store.py`)
- `ten_questions_*.md` / `.jsonl`, `compare_retrieval.md` evaluation results

An earlier plain-text pass (`clean_text/`, 150 files) was replaced by the Markdown conversion
and is not produced by the current scripts.
