# Messy parts and decisions

## Corpus selection

- First tried Shopify Help Center. Only 45 of 150 requests succeeded; the rest returned
  403 Forbidden (server-side bot protection), even though robots.txt allowed the pages.
- Did not try to bypass the block. Switched to GitLab Docs, which served all pages.
- Lesson: test that a site actually serves you pages before committing to it.
- A first script bug also returned 0 pages: the main sitemap was an index of per-language
  sitemaps, so the English filter matched nothing. Fixed by using the English sitemap directly.

## Corpus profile (final, clean_text_v3)

- 148 files, about 1.47M characters. Median 5,776 chars per file, min 579, max 115,736.
- 15 files over 20K chars, 5 over 40K (largest: reference architecture for 25k users,
  webhook events, SAST). 25 files under 1,500 chars.
- Mixed content: user guides (38), development (24), administration (17), CLI reference (14),
  CI (13), API (9), release notes (6), tutorials (5), Helm charts (4), others.
- 92 files contain code blocks, 60 contain tables, 74 have a Tier/Offering line.

## Problems found in pass 1 (get_text("\n"))

1. Inline code and links split onto separate lines (about 9,300 punctuation-only lines).
2. Title repeated twice with a stray "/" breadcrumb between.
3. "Was this page helpful? Yes No" widget at the end of all 150 pages.
4. Tier/Offering labels split across lines.
5. Version-history notes broken into one-word lines (30 files).
6. Tables flattened (cells lost their column), code blocks lost structure.
7. 4 files under 500 bytes: stub pages ("This document was moved...") or bare link indexes.

## Fixes applied

- clean.py: switched to HTML to Markdown (markdownify). Fixed 1, 3, 5, 6. Skipped 2 stubs
  under 300 chars (MCP tools page, Data Science index).
- tidy.py: removed breadcrumb and duplicate title, merged Tier/Offering into one line,
  made relative links absolute, replaced image links with "[Image: alt text]".

## Remaining problems (not fixed)

- Images are lost; only alt text remains (35 placeholders in 20 files). Some pages
  rely on diagrams, so answers about them will be incomplete.
- Very long pages (5 over 40K chars) need chunking; one embedding for a whole page
  will blur many topics.
- 6 files have no "##" headings, so heading-based chunking will not split them.
- About 25 short pages (under 1,500 chars) are mostly links or one idea; may retrieve poorly.
- Release notes and CLI reference pages are repetitive and similar to each other, which
  may cause near-duplicate retrieval results.
- Content reflects the docs as of 2026-10-05 (latest version); older versions were excluded.
- 1 harmless stray "/" line in runner_agents.md.
- Download used a random sample of 150 pages, so topics are covered unevenly.

## Decisions

- Kept: English docs, current version only, pages over 300 chars.
- Dropped: review apps, versioned paths, 2 stub pages.
- Keep page title and absolute URL with each chunk later, for citations.

## Next step

- Chunk by "##" headings (about 500 to 800 tokens, small overlap), then embed.
