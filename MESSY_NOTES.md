# Messy parts and decisions

## Corpus selection

- First tried Shopify Help Center. Only 45 of 150 requests succeeded; the rest returned
  403 Forbidden (server-side bot protection), even though robots.txt allowed the pages.
- Did not try to bypass the block. Switched to GitLab Docs, which served all pages.
- Lesson: test that a site actually serves you pages before committing to it.
- A first script bug also returned 0 pages: the main sitemap was an index of per-language
  sitemaps, so the English filter matched nothing. Fixed by using the English sitemap directly.

## Corpus profile (final, after exclusions)

- 147 pages (148 cleaned, minus 1 excluded), about 1.46M characters. Median 5,824 chars per
  page, min 579, max 115,736.
- 15 pages over 20K chars, 5 over 40K (largest: reference architecture for 25k users,
  webhook events, SAST). 25 pages under 1,500 chars.
- Mixed content: user guides (38), development (24), administration (17), CLI reference (14),
  CI (13), API (9), release notes (6), tutorials (5), Helm charts (4), others (17).
- 91 pages contain code blocks, 60 contain tables, 74 have a Tier/Offering line.
- After chunking: 1,461 chunks, 451,903 tokens in total. Tokens per chunk: median 333,
  min 29, p95 481, max 497 (model limit 512). Chunks per page: median 6, max 112
  (webhook events 112, 25k reference architecture 111, SAST 54).

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
- chunk.py: restored code-language labels (see chunking problems), merged tiny sections into
  a neighbour, and added a title fallback built from the URL for pages with an empty title.
- Excluded the page runner/agents: it has an empty title and its content is writing-style
  instructions for AI tools, not product documentation (9 chunks). It was also retrieved as
  noise for vague queries (3 of the top 5 results for "how do I fix it"). No script does
  this: it was one shell command, run before chunking:
  `mkdir -p outputs/excluded && mv outputs/clean_text_v3/runner_agents.md outputs/excluded/`

## Problems found while chunking

- Code-language labels (shell, yaml, json...) sat as separate lines before about 480 code
  blocks (313 of them indented inside list items). The chunker turns them back into proper fences.
- Many code blocks are indented inside list items, so any code-handling logic must allow for that.
- Tiny sections (like a short intro) made near-empty chunks, so they are merged into a
  neighbour (small chunks dropped from 50 to 12 in testing). 21 chunks are still under 80
  tokens; this is acceptable.
- Only about half of consecutive chunks share overlap text (394 of 766). A chunk that ends
  on a code block, a table, or a long single paragraph gets no overlap on purpose, rather
  than cutting it in half.
- Long code blocks and tables are split by lines (tables repeat their header row) because
  a single block can be larger than a chunk.
- 6 pages have no "##" headings, so they are split by size only.
- Checks run on the final chunks: max 497 tokens with the real model tokenizer (0 over 500),
  0 unclosed code blocks, 100% of line starts and ends from the pages present in chunks.

## Embedding, storage and retrieval findings

- Embedding model: BAAI/bge-small-en-v1.5 (384 numbers, reads up to 512 tokens, runs locally,
  free). Chroma's default MiniLM model truncates input at 256 word pieces, which would cut
  500-token chunks in half.
- Chunk settings: target 450 tokens, hard max 500, 50-token overlap, split at "##"
  headings, each chunk starts with "Page title > Section" and carries its page URL.
- Chroma store: cosine distance, 1,470 vectors at first build, all with norm 1. Embedding
  took 28 seconds on a MacBook.
- 6 pairs of chunks from different pages are near-identical (cosine above 0.98), all
  patch-release notes. Queries about those releases return near-duplicate results.
- The best chunk is not always ranked first: for "How do I limit memory for Gitaly?" the
  chunk that explains memory_bytes ranked 5th. With only the top 3 it would have been missed.
- Results often cluster on one page (the webhook question returned 5 chunks from one page,
  two of them the same section).
- Distance does not separate good from bad matches: a good match was 0.24, an irrelevant
  one 0.31, a relevant-but-unanswerable one 0.34, a vague one 0.36. A fixed distance
  cutoff would not catch unanswerable questions. The 10-question test agrees: good
  matches were 0.13 to 0.29, while the system-hooks gap, the GitHub question and the
  vague question were 0.28 to 0.40, so the ranges overlap.
- The sampled corpus has gaps: the system hooks page is not in it, so a question comparing
  project webhooks and system hooks cannot be answered. Evaluation questions must be
  chosen from pages that are actually in the corpus.

## Answer-generation findings

- The prompt numbers the sources and asks for [n] citations. The code checks the citations:
  a number that does not exist is flagged, and an answer with no citations is flagged.
- All 5 citations in the first Gitaly answer were checked against the source text and were
  accurate.
- Unanswerable question ("GitLab's stock price"): correct refusal.
- First version of the prompt failed on a vague question ("how do I fix it"): it refused,
  then added a speculative suggestion with a citation. Fixed with a stricter prompt: refuse
  with only the fallback line, or ask one clarifying question. A refusal now drops citations.
  After the fix the vague question returns only a clarifying question.
- The current Anthropic SDK has no temperature setting, so wording can vary a little
  between runs. This matters when comparing answers during evaluation.
- Cost per question: about 1,500 to 2,700 input tokens and under 300 output tokens.

## API and 10-question test (2026-10-06)

- Added a FastAPI endpoint POST /ask (api.py). The reply has one "status" (answered, refused,
  clarifying, uncited), the citations, every retrieved chunk with its distance, token counts
  and timing. Showing what was retrieved is what makes it possible to tell a retrieval
  failure from an answer failure. Offline tests (test_api.py) use a fake model, no API key.
- ten_questions.py sends 10 questions through the API and checks the reply type, whether the
  right page was retrieved and cited, and key words. Result: 8 of 10 passed the automatic
  checks. Reading the answers against the pages found 2 real failures and several weak passes.
  The automatic checks are not enough on their own: one failure was flagged for the wrong
  reason, and another was given the wrong label.

Real failures:

- Q6, "Which security issues were fixed in GitLab 16.11.1?": refused. The right page was
  retrieved, but only its two Introduction chunks. The six "Security fixes" chunks (fix table
  and one per CVE) were not in the top 5; near-duplicate patch-release pages (16.10.3,
  17.0.1, 18.3.1) took the other slots. The script called this a generation failure, but the
  model correctly refused given what it saw. It is a retrieval failure, and the check only
  looks at the page, not the chunk.
- Q3, "What fields does the payload of a push event webhook contain?": the answer looked
  complete but stopped at `project`. The same JSON example continues in later chunks
  (commits, total_commits_count, repository) that were not retrieved, and the model did not
  say the list was cut off. The script flagged it only because of one key word I chose.

Weak passes:

- Q7 (admin UI toggle for cgroups, a false premise): the content is right (configured in
  gitlab.rb, no UI option), but the reply starts with "I couldn't find this", which is
  misleading because it did find the answer.
- Q10 (vague question): the clarifying question offered options taken from unrelated
  retrieved chunks (Security Review Flow, MCP), so retrieval noise leaked into it.
- Q2: facts right, but the setup steps cite the "Delete an immutable rule" section rather
  than the section that explains creating a rule.
- Q1: 2 of 5 retrieval slots went to a reference-architecture page, and the answer does not
  say where the setting goes.
- Q4 and Q5: several top-5 slots were repeated "Git requirements for non-Docker executors"
  chunks.
- Citations show only the "##" section, so text under a "###" sub-heading carries its parent's
  label (Q5 cites "Selecting the executor" for the Docker and Kubernetes executor text).
- Refusals often add an explanation after the fixed sentence, although the prompt says
  "nothing else". The code drops the citations, but a leftover "[4]" stays in the text.
- Passed without problems I could find: Q4, Q5, Q8 (corpus gap, refused), Q9 (GitHub
  password, refused).

## Remaining problems (not fixed)

- Images are lost; only alt text remains (35 placeholders in 20 pages). Some pages
  rely on diagrams, so answers about them will be incomplete.
- About 25 short pages (under 1,500 chars) are mostly links or one idea; may retrieve poorly.
- Release notes and CLI reference pages are repetitive and similar to each other. This caused
  a real failure (Q6): near-duplicate pages crowd out the chunk that has the answer.
- Long code and JSON examples are cut across chunks, so one answer can need 2 or 3 chunks and
  a missing chunk gives a silently incomplete answer (Q3).
- Content reflects the docs as of 2026-10-05 (latest version); older versions were excluded.
- Download used a random sample of 150 pages, so topics are covered unevenly.
- Retrieval is noisy for vague questions and can return several chunks from one page.
- The model does not always follow the "refuse with only this sentence" rule.

## Decisions

- Kept: English docs, current version only, pages over 300 chars.
- Dropped: review apps, versioned paths, 2 stub pages, the runner/agents page (moved to
  outputs/excluded/ with a shell command, not by a script).
- Keep page title and absolute URL with each chunk, for citations.
- Local embedding model and Chroma for storage; Claude Haiku (claude-haiku-4-5-20251001) for
  answers by default, switchable with the RAG_MODEL setting.
- Licence: GitLab documentation is published under CC BY-SA 4.0 (checked 2026-10-06). The
  whole outputs/ folder (raw HTML, cleaned text, chunks, database, test results) stays in
  .gitignore anyway: it is rebuilt with download.py, so the repo holds only my code and notes.
  If I ever publish the cleaned text, chunks or test results, they are adaptations of GitLab's
  text, so they need attribution to GitLab and the same CC BY-SA 4.0 licence, separate from
  the MIT licence on the code.

## Next step

- Build an evaluation set: about 25 questions with known correct pages (all from pages in
  the corpus), plus unanswerable and vague questions. Record the expected section or chunk
  too, not only the page. Measure how often the right page and the right chunk are in the
  top 3 and top 5, and whether refusals behave correctly.
- Then test changes one at a time: retrieving more chunks (k=10 for Q3 and Q6 first), adding
  the neighbouring chunks of each hit, keyword matching for version numbers like 16.11.1
  (hybrid search), re-ranking, chunk size and overlap, and a different model.

## Hybrid search and reranking (2026-10-06)

- Added keyword search (BM25, own code in bm25.py), merged with vector search by
  Reciprocal Rank Fusion (1/(60+rank)), and an optional reranker
  (cross-encoder/ms-marco-MiniLM-L6-v2) that re-orders the top 30 candidates. rag.py has
  four modes: vector, bm25, hybrid, hybrid_rerank. Vector is still the default.
- ten_questions.py now has an "evidence" check: text that must be in the retrieved chunks
  for any model to answer. compare_retrieval.py runs only the searches (no language model).

Evidence found, 7 questions that have evidence:

- top 5: vector 4, bm25 3, hybrid 5, hybrid+rerank 4.
- top 10: vector 5, bm25 5, hybrid 6, hybrid+rerank 5.
  Automatic checks on all 10 questions (top 5): vector 7, bm25 6, hybrid 8, hybrid+rerank 7.
  One question on 10 is within noise (wording varies between runs; no temperature setting).

What changed (each claim checked against the cleaned pages):

- Q6 security fixes in 16.11.1: the page lists 5 fixes. Vector refused; hybrid listed all 5.
  BM25 alone listed 4 and left out Path Traversal, the most severe one (CVSS 8.5).
  Hybrid+rerank listed only the two medium issues and left out all three High ones. Both
  partial answers were worded as if complete.
- Q3 push payload: the example on the page has 19 top-level fields. Vector listed 15 and
  stopped at `project`; hybrid listed 17 (it added `commits` and `total_commits_count` from
  the prose chunk) but not `push_options` or `repository`. Neither said the list was partial.
  BM25 and hybrid+rerank refused. The reranker dropped the Push events chunk that vector
  search had ranked first, in favour of three merge-request chunks.
- Q5: BM25 alone misread the compatibility table ("Kubernetes does not support services";
  the table says it does). No automatic check caught it.
- Q1: the docs example says "# 20 GB" next to 32212254720 bytes, which is 30 GiB. Hybrid
  answers copied "20 GB" faithfully; BM25's answer silently wrote "30 GB" (right, but not what
  the page says, and it did not mention the page is wrong).
- Q8: only hybrid+rerank gave a partial answer, and it was faithful: the page says system
  webhooks are documented at /administration/system_hooks/. But it ended with "I couldn't
  find this", so the reply contradicts itself, and it is labelled "answered".
- Q2: the creation steps are in the "Prerequisites" chunk and are identical to the delete
  steps, which is why the strict evidence check fails in most modes.
- Q4, Q7, Q9, Q10: no real change. Q10's clarifying question still offers options taken from
  irrelevant retrieved chunks.

Findings:

- Hybrid was best on this set; BM25 alone and the reranker did not help. BM25 finds version
  numbers (Q6) but adds noise on a page with 100+ similar chunks (Q3: merge-request chunks
  match "events", "payload", "fields"). Vector top 10 found the Q3 payload tail at rank 9;
  hybrid top 10 did not.
- The reranker moved the Q3 payload chunk below three merge-request chunks and put two
  Windows-executor developer pages above the executor list (Q4). My guess is that a model
  trained on web passages scores JSON, tables and release notes poorly; this is untested, as
  is bge-reranker-base.
- Evidence checks for Q2 and Q3 are strict: Q2's creation steps are under "Prerequisites"
  and the question did not need them.
- Speed: search median 60 ms vector, 82 ms hybrid, 355 ms with reranker; the model call
  takes about 2 s. compare_retrieval timings include model loading, so use timing_ms in the
  .jsonl files instead.
- Most dangerous failure, and no check detects it yet: a partial list shown as a full list
  (Q3, Q6).

Decision: use hybrid for further tests (RAG_RETRIEVAL=hybrid); reranker off for now.

## Repo review before publishing (2026-10-06)

Problems found:

- My draft README said the API key could go in .env, but no code loads .env. The key must be exported
  (`export ANTHROPIC_API_KEY=...`). The .env line in .gitignore is still useful as a safety net.
- .DS_Store (macOS) was committed and not ignored. Added to .gitignore and removed from git.
- download.py sends a placeholder contact (your-email@example.com) in its User-Agent. Not
  changed: it only matters when download.py runs again, and it does not break anything.
  Worth replacing with a real contact before re-running. The 150 pages in this project were
  fetched with the placeholder.
- requirements.txt (pip freeze) held 4 packages nothing uses: gh (an unrelated package, not
  GitHub's CLI), GitPython, gitdb and smmap. Removed. Everything else is a dependency of what
  the code imports.
- compare_retrieval.py times the first search of each mode, which includes loading the models,
  so its "avg search time" row is too high. Not changed: it does not affect the evidence
  results. The search times in the README come from timing_ms in the ten_questions .jsonl
  files. A warm-up search per mode before the loop would fix it.
- The pipeline needs one extra command (moving runner_agents.md), now written in the README.
- Re-running download.py can give a different 150 pages, because the sitemap changes over
  time. The numbers in the README come from the 2026-10-05 download.

## Next step (replaces the earlier one)

- Build the evaluation set: about 25 questions with evidence strings, plus unanswerable and
  vague ones; measure the hit rate at top 3, 5 and 10 and score the answers.
- Then try, one at a time: bge-reranker-base, adding neighbouring chunks, a prompt rule to
  say when a list looks cut off, and hybrid with 8 to 10 chunks.
