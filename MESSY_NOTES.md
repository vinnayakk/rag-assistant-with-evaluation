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

## Evaluation set and retrieval recall (2026-10-07)

Q numbers in this section are the evaluation set's own (Q1 to Q51), not the 10-question
test's.

What I built:

- eval_questions.jsonl: 51 questions. 43 have a right page and "evidence" strings that must
  appear together in one retrieved chunk of that page. 8 have no page and cannot be scored by
  search: 3 corpus gaps (Q44 to Q46), 2 off-topic (Q47, Q48) and 3 vague or too broad (Q49,
  Q50, and Q51, which I wrote myself: "Which configurations for Linux packages are the most
  important and which ones can be ignored?", expected reply: a clarifying question).
- The 43 scored questions: direct 10, paraphrase 10, number 4, procedure 4, version 3,
  error-message 3, crowded 2, negation 2, false-premise 2, API 1, deep 1, table 1.
- eval_recall.py runs only the searches (no language model, no cost). For each mode it
  records the rank of the first chunk from the right page (page recall) and the rank at which
  the chunk that holds the evidence appears (evidence recall). `--validate` first checks that
  every page is in the database and every evidence string is inside one chunk of its page.
  Everything passed.
- The questions were written with the pages open, so they share words with the pages. In a
  first check BM25 alone found the right page at rank 1 for every question, so five were
  reworded to use fewer of the page's words (Q19, Q22, Q33, Q37, Q40). The set is still easy.

Results (43 scored questions, top 5, run on my MacBook):

| mode          | page recall@5 | evidence recall@5 | evidence recall@1 | evidence recall@10 | MRR  | median search |
| ------------- | ------------- | ----------------- | ----------------- | ------------------ | ---- | ------------- |
| vector        | 43/43         | 41/43             | 30/43             | 42/43              | 0.96 | 12 ms         |
| bm25          | 42/43         | 39/43             | 31/43             | 42/43              | 0.97 | 1 ms          |
| hybrid        | 43/43         | 42/43             | 34/43             | 43/43              | 0.96 | 13 ms         |
| hybrid_rerank | 42/43         | 41/43             | 35/43             | 41/43              | 0.98 | 270 ms        |

Findings:

- Page recall cannot tell the modes apart: 98 to 100% for all four at top 5 (the 95% interval
  for 42/43 is 88 to 100%). All it shows is that the right page is nearly always found. At
  rank 1 it is 40, 41, 40 and 42 of 43.
- Evidence recall separates them a little. Hybrid is best at top 5 (42/43) and top 10 (43/43);
  BM25 is weakest at top 5 (39/43). The gaps are one to three questions, so this is a lean,
  not a proof. Against vector (evidence at top 5): BM25 gained Q25 and lost Q22, Q40 and Q43;
  hybrid gained Q25 and lost none; hybrid+rerank gained Q25 and lost Q43.
- Vector's weak spot is near-duplicate patch-release pages (the same problem as Q6 in the
  10-question test). Q25 (the CVE fixed in 17.0.1): the right page came at rank 4 and the
  chunk with the CVE at rank 6. BM25 put the chunk with the CVE at rank 1 and hybrid at rank
  2, probably because the version number is a keyword.
- BM25's weak spots: question words that are not on the page, and pages with many similar
  chunks. Q22 (how an instance shows that a newer release is available): none of the page's
  chunks were in its top 10, because it matched "security" and "releases" on unrelated pages.
  Hybrid still found the page but moved it from rank 1 (vector) to rank 3. Q40 (labels API)
  and Q43 (Windows hosted runners): BM25 put the page's Introduction first but the section
  with the answer at rank 7 and rank 6. Hybrid had both at rank 1 and rank 3.
- The reranker is best at rank 1 (35/43, against 34 for hybrid and 30 for vector) but no
  better than hybrid at top 5 and worse at top 10 (41/43 against 43/43). It lost the right
  page on Q43: three SAST "Getting started" chunks went to the top and the Windows page fell to
  rank 6. Same pattern as the 10-question test, where it also moved the right chunk below
  unrelated ones.
- Q33 is scored as an evidence miss in every mode, but part of the fault is the question. The
  evidence string ("a replacement for Kaniko") is a table row in the page's Introduction
  chunk. The question ("which way of building images keeps my runners unprivileged?") is also
  answered by the first "Migrate from Kaniko to BuildKit" chunk ("BuildKit rootless is a
  secure alternative to Kaniko ... without privileged containers"). BM25 ranks that chunk first
  (checked); in the other modes a "Migrate" section is in the top 3, but the report does not
  say which of its two chunks. So evidence recall is probably understated by one question in
  every mode, and the order of the modes does not change. Not fixed: the format cannot accept
  two different chunks for one question. Changing the evidence to "without privileged
  containers" and re-running the four modes would fix it.
- Search time is the median of the search call only, after one warm-up search per mode. It is
  lower than the README's 60, 82 and 355 ms, which came from timing_ms in the 10-question
  test. I have not worked out why they differ. The first version of the report used the mean:
  vector's mean was 17 ms because of one 224 ms search (median 12 ms), so it now reports the
  median.

Mistakes in my own tooling:

- The first `eval_recall.py` wrote every mode to the same file names, so running the modes one
  at a time replaced the previous mode's results (I renamed the files by hand). Now each mode
  has its own files, `outputs/eval_recall_<mode>.md` and `.jsonl`, and the side-by-side report is
  `outputs/eval_recall_vector+bm25+hybrid+hybrid_rerank.md`, built with `--compare` from the
  saved .jsonl files without searching again. The file name is made from the modes in it, so
  one run cannot replace another's file.

Limits of this evaluation:

- Only 43 scored questions, written by me with the pages open. Page recall is saturated, so
  the numbers probably overstate how well search will do on real users' questions.
- Search only. It says whether the chunk with the answer was retrieved, not whether the model
  answered correctly with it. The 8 questions without a page are not scored at all.
- One right page and one evidence chunk per question. Some questions have more than one
  chunk that answers them (Q33).

Decision: no change. Hybrid stays the choice and the reranker stays off. This agrees with the
10-question test (hybrid best, reranker not helping), but the differences are one to three
questions out of 43.

## Answer evaluation and faithfulness judge (2026-10-07)

Q numbers in this section are the evaluation set's (Q1 to Q51) again.

What I built:

- `eval_answers.py`: for each of the 51 questions it searches (5 chunks), lets Claude Haiku
  4.5 write the answer with the same code as the API (`rag.answer`; the reply labels come
  from `api.status_of`), and records the reply type, whether the 5 chunks held the right
  page and the evidence string, and a faithfulness verdict. Each mode has its own files,
  `outputs/eval_answers_<mode>.jsonl` and `.md`; the side-by-side table is
  `outputs/eval_answers_vector+hybrid_rerank.md`, rebuilt with `--compare`.
- `judge.py`: the faithfulness judge. Faithful means every claim in the answer is backed by
  the 5 chunks the model was given. It does not mean correct: the chunks can be the wrong
  ones, and an answer can be faithful and incomplete. The judge is Claude Sonnet 5.5, not
  the model that wrote the answers (a model goes easy on its own writing). It splits the
  answer into claims, names the source of each and copies the words that back it; the code
  then checks that those words are really in that source, and a claim with an invented
  quote counts as unsupported. An answer is faithful only if all its claims are supported.
- Checks on the judge itself: a preflight before the real run (a true statement must come
  out faithful and a false one unfaithful); 5 control answers per mode, judged against the
  chunks of a different question, which must come out unfaithful; and a count of invented
  quotes. Result: 5 of 5 controls unfaithful in both modes, 0 invented quotes in about 300
  claims, 0 judge errors.
- `test_judge.py` and `test_eval_answers.py` run offline with a fake model server (no key).
  They cannot show whether the judge reads real answers well; so far the only check of
  that is my reading of the 5 flagged answers below.

Results (51 questions, top 5, run on my MacBook). Only vector and `hybrid_rerank` were run,
not hybrid on its own:

| measure                                      | vector                | hybrid_rerank          |
| -------------------------------------------- | --------------------- | ---------------------- |
| right kind of reply, all 51                  | 46/51 (90%)           | 47/51 (92%)            |
| answered, of the 43 the docs can answer      | 40/43                 | 41/43                  |
| refused or asked back, of the 7 that must be | 5/7                   | 5/7                    |
| 5 chunks held the right page (43)            | 43/43                 | 42/43                  |
| 5 chunks held the evidence (43)              | 41/43                 | 41/43                  |
| faithful answers                             | 37/40 (92%)           | 39/41 (95%)            |
| claims backed by the chunks                  | 149/152 (98%)         | 146/148 (99%)          |
| answers with a contradicted claim            | 1                     | 1                      |
| median search / answer / judge               | 90 / 1,440 / 3,138 ms | 361 / 1,414 / 2,995 ms |
| cost: answering / judging (with 5 controls)  | $0.12 / $0.48         | $0.13 / $0.47          |

The 95% intervals are 79 to 96% and 81 to 97% for the reply type, 80 to 97% and 84 to 99%
for faithful answers. They overlap almost entirely. The whole run cost about $1.20.
Answering took about 2,000 input tokens and 78 to 79 output tokens per question, over all
51 (88 or 89 over the answers that make claims; refusals are short). The README's "120 to
160 output tokens" came from the 10-question test. I have not worked out why the two differ.

Findings:

- The two modes cannot be told apart on these questions. Reply type differs by one
  question: `hybrid_rerank` gained Q25 and lost none. Faithful answers differ by two, with
  one more answer judged on one side (see the limits). A difference of this size is within
  what the judge's own noise and one rerun could change.
- Q25 (the CVE fixed in 17.0.1) is the one clear search effect and it matches the recall
  test: vector had the CVE chunk at rank 6, so the model saw "1-click account takeover" but
  no CVE number and refused. `hybrid_rerank` had it in the 5 chunks and answered CVE-2024-4835.
- The wrong replies are mostly not search failures:
  - Q42 (merge request title validation on the Free tier) and Q43 (Windows Server 2019
    hosted runners) are false-premise questions where the right reply is an answer that
    corrects the premise. All four replies (2 questions, 2 modes) were labelled "refused".
    In three of them the fixed refusal sentence was followed by the right correction (Q42
    in both modes: "Premium, Ultimate"; Q43 in vector: only Windows 2022 is listed). The
    fourth, `hybrid_rerank` on Q43, had not retrieved the page and could only say that
    the docs do not cover it. The first three are the same pattern as Q7 in the 10-question
    test: the content is right and the label is wrong. The cause is mostly the prompt: its
    rule 3 says to refuse with only the fixed sentence when the sources do not contain
    the answer, and no rule covers a question whose premise the sources correct.
  - Q51 (my question about important Linux package settings): both modes refused and
    explained why, instead of asking a clarifying question. Q49 and Q50 got the clarifying
    question in both.
  - Q48 (a haiku, off-topic): the model did not use the fixed sentence in either mode. Vector
    apologised without citing (labelled "uncited"); `hybrid_rerank` offered help (labelled
    "clarifying"). The same non-compliance with "reply with only this sentence" as before.
- Faithfulness is high in both modes: 37 of 40 and 39 of 41 answers, with 98 to 99% of the
  claims backed. The 5 answers the judge flagged, and what I think of each after reading
  the claim and the sources:
  - vector Q7 (fail fast testing): contradicted, and the judge is right. The answer says
    fail fast runs only the 100 specs for the changed file "rather than running the entire
    test suite". The page's table shows that the `rspec-complete` job still runs all 1000
    specs when the fail fast specs pass.
  - `hybrid_rerank` Q11 (CRIME): the claim is "CRIME requires both a vulnerable protocol
    configuration and data compression". The page says you might be vulnerable if you use
    SSL compression or SPDY, and its Nessus section says "one of two configurations ... known
    to be required". Not stated by the page, so the flag is real. "Contradicted" is the
    judge's strongest label; "unsupported" would also have been fair.
  - vector Q11: unsupported, borderline. The answer says Gzip is disabled in the NGINX files
    for both installation types. The page says GitLab mitigates CRIME "by deactivating Gzip
    when HTTPS is enabled" and then links the two NGINX files as "the sources of the files".
    A fair reading, but it does not say that Gzip is disabled in those files.
  - `hybrid_rerank` Q39 (pull policy): unsupported, borderline. The answer says the runner
    does not pull an image that is already stored locally under `if-not-present`. The chunk
    only recommends that policy "to avoid transferring data" for large images that rarely
    change; the mechanism is implied by its name, not stated.
  - vector Q19 (change failure rate): unsupported, but too strict. The page says the rate is
    measured "as the percentage of deployments that cause an incident" and gives an example
    whose rate is 0.3, so "0.3 is 30%" is a unit conversion. I would not call it a
    faithfulness failure. The judge passed the other 5 claims of this answer.
    So of the 5 flags, 2 are real, 2 are borderline and 1 is too strict. I checked only these
    5 against the sources, not the answers the judge passed, so I cannot say how many problems
    it missed.
- Q33 (which way of building images keeps runners unprivileged) is an evidence miss in every
  mode in the recall test. Both modes answered it correctly and faithfully ("BuildKit
  rootless keeps your runners unprivileged ... a direct replacement for Kaniko builds"), and
  the judge passed both. So the evidence string is the problem, not the search: recall is
  understated by one question in every mode. Both answers came mostly from the chunk labelled
  "Prerequisites" (rank 2 in vector, rank 1 in `hybrid_rerank`). It also holds the short
  "BuildKit rootless" section, because tiny sections are merged into a neighbour, so the
  citation label shows only the first heading.
- Search time is higher here than in the recall run: median 90 ms (vector) and 361 ms
  (`hybrid_rerank`), against 12 and 270 ms. Both runs did a warm-up search first, so model
  loading is not the reason. 361 ms agrees with the 355 ms from the 10-question test. My
  guess, untested: in the recall run the searches follow each other immediately, here each
  one comes right after a multi-second wait for the network. I have not checked it.

Mistakes and limits:

- Faithfulness is counted only over the answers actually given. A mode that refuses more
  has fewer answers to get wrong and looks more faithful. Here vector gave 41 answers
  (judged 40: Q48 had no claims) and `hybrid_rerank` gave 41 (judged 41), so the denominators
  are almost equal, but the table still cannot be read as "which mode is more faithful"
  without them.
- The judge is a language model and the SDK has no temperature setting, so a re-run can
  flip a borderline answer (Q11, Q39) in either direction. I ran each answer once.
- Hybrid on its own, the mode I chose in the notes above, was not part of this run. This
  compared vector with `hybrid_rerank`, so it says nothing yet about the decision to keep
  hybrid and the reranker off. One more mode costs about $0.60.
- 8 of the 51 questions have no page, and the reply type is the only check on them: 7 must
  be refused or asked back, and Q46 (a corpus gap) may also be answered. Whether the answers
  are right is not checked beyond the judge, and faithfulness does not catch a wrong answer
  built from the wrong chunks. The "my verdict" line in the `.md` files is for my own
  reading of each answer; the numbers above do not use it.
- Questions written with the pages open, and only 51 of them: the same limit as the recall
  test.

Decision: no change. The two modes cannot be separated on 51 questions, and the clearest
fixes are in the prompt (false premise, the fixed refusal sentence, broad questions that
are about a topic), not in search. I will not tune the judge's prompt to make the numbers
look better. If I add a rule (for example that arithmetic on stated numbers counts as
supported, which would clear Q19), I write it down first, re-judge all the compared modes
with the new prompt under a new `--out` prefix, and record it here.

## Next step after the answer evaluation (replaces the earlier ones)

- Run `python eval_answers.py --modes hybrid` so the mode I actually use has answer results
  too, then `--compare` to put the three modes side by side. About $0.60.
- Read the answers myself and fill in the "my verdict" lines, starting with a sample of the
  answers the judge passed (so far only the 5 flagged ones were checked), to see whether
  the judge misses problems.
- Prompt changes, one at a time, each re-run on all 51 questions: tell the model what to do
  with a false premise (answer with the correction and do not start with the refusal
  sentence), how to treat a question that is about a topic but too broad (clarifying
  question, Q51), and what to do with off-topic requests (Q48).
- Decide whether to fix Q33's evidence string ("without privileged containers") and re-run
  the recall test for the four modes.
- Add harder questions: written without the page open, or taken from real users, with more
  version and CVE questions and more pages that have many similar chunks (like the labels API).
- Then try, one at a time: bge-reranker-base, adding neighbouring chunks, a prompt rule to
  say when a list looks cut off, and hybrid with 8 to 10 chunks.

## Request log, dashboard and Langfuse traces (2026-10-09)

Q numbers in this section are the 10-question test's (Q3 and Q6) again.

What I built:

- `metrics.py`: one JSON line for every call to `POST /ask` in `outputs/requests.jsonl`: the
  question, search mode, reply type, tokens, cost, and the time of the search, the model call
  and the whole request. Cost is tokens times the prices in the file (Haiku 4.5: $1 per million
  input tokens, $5 per million output tokens, from the Anthropic pricing page, checked
  2026-10-08). A model that is not in the price table gets no cost instead of $0. A request
  whose model call failed is logged as an error and left out of the averages.
- `dashboard.py`: `/dashboard` (and `/stats` as JSON) shows mean, median and 95th percentile
  latency, cost per request and per 1,000 requests, a table by search mode and a bar chart of
  search time against model time. It reads the local file, so it needs no account. It has no
  login, so it stays on localhost.
- `tracing.py`: optional Langfuse tracing, one trace per request: `ask` > `search` (the chunks
  found, with their distance, bm25, rrf and rerank scores) + `llm` (the exact prompt, the
  answer, tokens and cost). It is off unless both keys are set, and a tracing problem cannot
  break an answer.
- `test_observability.py` runs offline, with a fake model server and a stand-in for Langfuse.

Results of the first real run: 30 requests, the 10 questions of `ten_questions.py` in each of
three modes, 5 chunks, Claude Haiku 4.5, 2026-10-09 17:41 to 17:44 UTC:

| mode          | requests | mean   | median | 95th pct | avg search | avg model call | cost per request | tokens in / out |
| ------------- | -------- | ------ | ------ | -------- | ---------- | -------------- | ---------------- | --------------- |
| vector        | 10       | 2.38 s | 1.92 s | 5.17 s   | 63 ms      | 2.32 s         | $0.0028          | 2,136 / 132     |
| hybrid        | 10       | 2.14 s | 1.67 s | 3.88 s   | 106 ms     | 2.03 s         | $0.0028          | 2,096 / 145     |
| hybrid_rerank | 10       | 2.76 s | 1.88 s | 8.50 s   | 756 ms     | 2.00 s         | $0.0026          | 1,965 / 129     |
| all           | 30       | 2.43 s | 1.80 s | 5.17 s   | 309 ms     | 2.12 s         | $0.0027          | 2,066 / 135     |

The 30 requests cost $0.0823 in total ($2.74 per 1,000 requests). Replies: 16 answered, 11
refused, 3 clarifying, no errors. Latency is the server's own time for `/ask` (search plus
model call), not the network or any queue.

Findings:

- Ten requests per mode are too few for a mean or a 95th percentile; with 10 requests the
  95th percentile is simply the slowest one. The slowest vector request was the first of the
  run (5.2 s, of which 5.1 s was the model call). The slowest hybrid_rerank request was 8.5 s,
  of which 4.3 s was search.
- That 4.3 s search was the first hybrid_rerank request. The other nine took 335 to 396 ms
  (361 ms on average, the same as the 361 ms of the answer run). Without the first request the
  average total is 2.12 s instead of 2.76 s. After I restarted the server for Langfuse, the
  first hybrid_rerank request again spent 3.7 s in search. This fits `api.py`, which loads the
  reranker at start-up only when the server's default mode is hybrid_rerank and otherwise on
  first use; I chose the mode per request. I have not timed the model load separately.
- The median is the number to quote: 1.67 to 1.92 s in all three modes. Speed does not
  separate the modes except for the reranker's search: about 0.36 s, against 0.06 s (vector)
  and 0.08 s (hybrid) when each mode's first request is left out.
- Cost is about the same in every mode, $0.0026 to $0.0028 per request. The differences come
  from the tokens in the 5 chunks and in the reply (2,136, 2,096 and 1,965 input tokens on
  average), and 10 requests per mode do not say more than that.
- The reply types agree with the 10-question test above. Q6 (security fixes in 16.11.1): vector
  refused, hybrid and hybrid_rerank answered. Q3 (push payload): vector and hybrid answered,
  hybrid_rerank refused. The cgroups question (Q7), the GitHub question (Q9) and the system
  hooks question (Q8) were refused in all three modes, and the vague one (Q10) got a clarifying
  question in all three. Q8 shows the run-to-run variation: before, hybrid_rerank answered it
  (partly); this time it refused.

What the traces showed (5 traced requests, 2026-10-09 19:03 to 19:30 UTC, Langfuse Cloud EU
region, SDK 4.17.0):

- Langfuse and my log agree on all 4 traces that arrived: tokens and cost are identical,
  timings are within 1 ms, and the `trace_id` in the log is the id Langfuse shows. That shows
  the numbers travel intact. It does not check the prices, because my code sends the cost to
  Langfuse. To check the price table I still have to compare the total with the Anthropic
  usage page.
- Q6, with the exact prompt in front of me. Vector: the model's 5 sources were the 16.10.3
  introduction, two 16.11.1 introductions, the 17.0.1 introduction and the 18.3.1 "Security
  fixes"; none of the 16.11.1 "Security fixes" chunks (the fix table and one per CVE). The
  first source, the 16.10.3 introduction, says "This patch release does not include any
  security fixes": it shares the question's words and means the opposite. The model started
  with the fixed refusal sentence and went on that the security issues "are not detailed in
  the provided documentation" and "may not have been listed at the time of the patch release
  announcement". That explanation is wrong. The page lists 5 fixes, but the model only sees
  its 5 chunks, so it blamed the documentation for a search failure. Hybrid: all 5 chunks came
  from the 16.11.1 page (2 introduction chunks and 3 "Security fixes" chunks, one of them
  the fix table), and the answer lists all 5 fixes with their severity (3 High, 2 Medium), as
  in the table.
- Q3, same method. Hybrid: the JSON chunk the model was given ends at `"ci_config_path": null,`
  and the rest of the payload is in the next chunk, which was not among the 5. The answer
  lists 15 top-level fields, `project` with its nested fields, and `commits` and
  `total_commits_count` (from the prose chunk). It opens with "the fields include:" and does
  not say that the list is cut off. This is the partial-list failure from before, now visible
  in the prompt itself. hybrid_rerank: the 5 chunks were three merge-request chunks, the Push
  events introduction (which ends at "Payload example:") and Work item events. The JSON chunk
  was missing, and the reply said that the sources mention push events but give no list of
  fields. This is the earlier finding that the reranker pushes the payload chunk below
  merge-request chunks.

Setup problem found on the way (certificates):

- The first traces did not arrive. The server log showed `CERTIFICATE_VERIFY_FAILED ... unable
  to get local issuer certificate` for cloud.langfuse.com, although start-up had said "connected
  to Langfuse". The Langfuse SDK uses two HTTP clients with two lists of trusted certificate
  authorities: the key check uses the `certifi` list, the trace sender uses Python's own list
  (or the file named in `OTEL_EXPORTER_OTLP_CERTIFICATE`). So the key check passed and every
  trace failed. Setting `OTEL_EXPORTER_OTLP_CERTIFICATE="$(python -c 'import certifi;
  print(certifi.where())')"` fixed it. I did not run the check that shows why my Python's own
  list fails. The first traced request was dropped after its retries failed and is not in
  Langfuse.
- Lesson: a start-up check must use the same path as the thing it checks. The check now tests
  the trace sender's certificate path as well and prints the fix when it fails; the README has
  a troubleshooting note, and `test_observability.py` reproduces the problem with a local HTTPS
  server.

Limits:

- 10 requests per mode, one run, the same 10 questions: means and 95th percentiles are not
  stable, and the reply types come from one run each.
- The cost comes from my price table, not from an invoice.
- 5 traced requests only. The dashboard has no login. A trace holds the question, the chunks
  and the answer: fine for GitLab's public documentation, but region, retention and masking
  need checking before private documents go through it.

Decision: no change. Hybrid stays the choice and the reranker stays off. The next steps above
stand.

## Chat page, own keys and deployment (2026-10-10)

What I built:

- `streamlit_app.py`: a chat page with example questions, a search-mode choice, answers with
  clickable `[n]` citations and a Sources list, and a "What the search found" list with each
  chunk's scores. It calls the same `api.ask` as `POST /ask`, so every question also lands in
  `requests.jsonl` and in the Langfuse trace. `guard.py` (limits), `app_backend.py` (loads the
  index and the embedding model once) and `chat_text.py` (key check, link and Markdown cleaning)
  are plain modules, so they can be tested without the page.
- `test_streamlit_app.py`: about 40 scenarios with Streamlit's `AppTest` and a fake model (own keys,
  limits, passcode, error messages, citations as links, every search mode). It needs no key.
- A copy of the search index committed as `data/chroma_db/` (1,461 chunks, 147 pages, about 29 MB),
  and the app deployed on Streamlit Community Cloud: https://rag-docs-assistant.streamlit.app/
- `.github/workflows/tests.yml`: runs the offline tests on every push and pull request.

Decisions:

- Visitors bring their own Anthropic key, instead of me paying for a public demo. Reason: I do not
  want to spend money on strangers' questions or look after a key that anyone could try to drain.
  The code keeps the other way too: if `ANTHROPIC_API_KEY` is set, the app pays and up to three
  limits apply (an optional passcode, 20 questions per browser session, 200 per day for the whole app).
- How the visitor's key is handled: it lives only in that visit's session memory on the server, a new
  client is made for each question, and it is never put in `os.environ`, a file, a log, the request
  log, a trace or the stored conversation. A key that Anthropic refuses is forgotten at once. The
  tests check each of these places. The cost is that a visitor has to trust the host with the key
  for a moment; the page says so and suggests a key made for the demo.
- The limits live in an ordinary module, not in `st.cache_resource`. An independent AI review of
  the page found 7 problems, and this one changed the design: Streamlit's server accepts a "clear cache"
  message from any visitor's browser, which would have reset the counters and given everyone a
  new daily allowance. The other six, all fixed: (1) a passcode lock-out shared by all visitors
  would let anyone lock the others out, so a wrong try now only costs one second; (2) questions
  that were turned away or failed were stored in the visitor's conversation, so anything a visitor
  typed could pile up in the server's memory, and only answered questions are stored now; (3) when a visitor
  clicked while the model was still working, Streamlit could stop the script before the answer
  (already paid for) was stored, so it is stored inside the spinner block; (4) a secrets file that
  exists but cannot be read was treated as "no secrets", which would have dropped a passcode, so
  the app now refuses to start; (5) text from the model and from the corpus was shown as Markdown
  and a set-up error showed a file path, so links are filtered and errors do not give paths;
  (6) Streamlit runs each visitor in its own thread, and the embedding model and the reranker
  could be called from several threads at once (Hugging Face tokenizers can fail with "Already
  borrowed" when they are), so both are now used behind a lock (`embedder.py`, `reranker.py`).

Lessons:

- My first version of the test named one specific search result, which is true on the smaller index
  I tested on and false on the real one, so it failed on my machine. The test now checks the page
  against its own "What the search found" list and does not depend on which chunk ranks where. It
  also has to work when `RAG_DB` is a relative path, which broke the test that starts the page in a
  child process.
- When running the page, the terminal printed `ModuleNotFoundError: No module named 'torchvision'`
  about 100 times per page load. It is harmless: Streamlit's file watcher looks through the modules
  `transformers` loads, which makes it import a few image processors (`*_fast`) that need
  torchvision, and this project does not use torchvision. I hide that one message with a filter on that one logger
  (`quiet_watcher_log()`); switching the watcher off would have hidden other things too.
- "Does the test fail when the code is wrong?" is a separate question from "does the test pass?".
  I broke the code on purpose 50 times (35 for the page, 3 for the log filter, 12 for the own-key
  feature) and each break now makes at least one test fail. Four of the 12 own-key breaks were not
  caught by my first tests (not checking that the key starts with `sk-ant-`, writing the key to the
  log when a call fails, storing the key in the conversation, and showing the key box as plain text
  instead of a password box); I added the missing checks until all were caught.

What the numbers say:

- Memory: 714 MB peak on my Mac. On the hosted app the sidebar read 1,208 MB after two questions
  (hybrid, then vector; read from my demo recording) and 1,483 MB after a `hybrid_rerank` question,
  which loads the reranker for the first time (+275 MB). In a Linux test the app alone was at about
  1 GB before any model was loaded and about 1.2 GB with random weights of the real models' size.
  I have not found the hosting limit stated exactly (quoted between about 1 GB and 2.7 GB); the app
  kept running at 1,483 MB, so the limit is not below that.
- Cost per question: $0.0037 (2,461 tokens in, 241 out) and $0.0026 (1,950 in, 129 out) in my request
  log, and $0.0032 (hybrid, 2,534 tokens) and $0.0023 (vector, 1,965 tokens) on the hosted page, 1.6 s
  each. The key page says "roughly 0.3 to 0.4 US cents"; these four questions are 0.23 to 0.37
  cents, so "roughly" is doing a little work. Four questions are not a measurement of the average.
- What I checked in Anthropic's documentation for the key page (2026-10-10): keys start with
  `sk-ant-`; a key is created under Settings > API keys in the Console at
  https://platform.claude.com/settings/keys; a spend limit is set under Settings > Billing.

The workflow (`tests.yml`):

- It runs every `test_*.py` (they are plain scripts that print "ok" lines and stop at the first
  wrong result) in Python 3.12, with `RAG_DB=data/chroma_db` and no secrets.
- It installs `requirements.txt` without `torch`, `sentence-transformers` and `transformers`: the
  tests use stand-ins for the embedding model and the reranker, so the largest download is not
  needed. I ran the same steps in a clean Python 3.12 environment: install about 70 s, all 8 test
  scripts pass in about 44 s.
- What it cannot tell me: it never calls the Claude API and never loads the real models, and it skips
  the part of `test_observability.py` that needs Langfuse (Langfuse is not in `requirements.txt`).
  It also does not stop Streamlit from deploying a push whose tests failed.
- `pip` prints a warning that `narwhals==2.27.0` (pinned in `requirements.txt`) was yanked. It is
  harmless so far and I have not changed the pin.

Limits:

- The hosted memory numbers come from a few questions by one visitor in all three modes. Several
  visitors at once were not tested and may push the peak higher. The hosted app was opened on a real
  phone (2026-10-10) and loaded fine; apart from that I only looked at the page in a headless browser
  at phone width.
- The live app depends on a free tier that can sleep when nobody uses it, and on a limit I could not
  confirm.

Open items:

- The answer test for plain hybrid (about $0.60) is still not run; the next steps in the section
  above stand.

Decision: no change to retrieval. Hybrid stays the choice, the reranker stays off, and the
evaluation numbers above are unchanged by this work.
