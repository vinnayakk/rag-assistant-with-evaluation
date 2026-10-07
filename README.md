# RAG Assistant with Evaluation

Ask a question about GitLab's documentation and get an answer with numbered
citations, or an honest "I couldn't find this" when the docs don't say. Search
combines meaning (vector) and exact words (BM25), with an optional reranker, and
every change is measured on the same set of questions before it is trusted.

## The problem

A first RAG pipeline answers most easy questions and fails quietly on the rest.
Testing this one on real documentation showed three kinds of quiet failure:
the right page was retrieved but not the chunk that held the answer, near-identical
release-note pages crowded each other out, and a partial list was presented as a
complete one. None of these show up if you only read the answers that look fine.
This project isn't just an assistant. It's an assistant with a test harness that
says whether the right text reached the model, separately from whether the model
used it well.

## How it works

```
docs.gitlab.com (150 random English pages)
        │  download.py
        ▼
raw HTML ── clean.py + tidy.py ──► Markdown (147 pages after one exclusion)
        │  chunk.py: ~450 tokens, 50 overlap, split at "##" headings
        ▼
1,461 chunks ── embedder.py (bge-small-en-v1.5) ──► Chroma
                                                      │
question ──► vector search ─┐                         │
         └─► BM25 keywords ─┴─► Reciprocal Rank Fusion ─► (optional reranker) ─► top 5
        ▼
Claude Haiku 4.5, sources numbered ──► cited answer | "I couldn't find this" | clarifying question
        ▼
FastAPI: POST /ask
```

1. `download.py`, `clean.py`, `tidy.py` fetch the pages, convert HTML to Markdown
   and tidy the result (see "Messy parts" below). `build_url_map.py` records each
   page's real URL for citations.
2. `chunk.py` splits pages at headings and packs paragraphs, lists, tables and
   code blocks into chunks of about 450 tokens (hard limit 500, counted with the
   embedding model's own tokenizer). `check_chunks.py` verifies size, code fences,
   overlap and that no text was lost.
3. `embedder.py` and `embed_store.py` embed every chunk with
   `BAAI/bge-small-en-v1.5` and store the vectors in Chroma.
4. `rag.py` has four search modes: `vector`, `bm25`, `hybrid` and `hybrid_rerank`.
   `bm25.py` is a from-scratch keyword search that keeps version numbers like
   `16.11.1` and names like `memory_bytes` whole. Hybrid merges both result lists
   with Reciprocal Rank Fusion. `reranker.py` re-orders the best 30 candidates
   with a cross-encoder. `answer()` numbers the sources, asks Claude for `[n]`
   citations, and flags invented citations and uncited answers.
5. `api.py` (FastAPI) exposes this as `POST /ask`. The reply says what kind of
   answer it is (`answered`, `refused`, `clarifying`, `uncited`) and includes every
   retrieved chunk with its scores, so a bad answer can be traced to its cause.
6. `ten_questions.py` and `compare_retrieval.py` are the first test harness (10 questions).
   `eval_questions.jsonl` holds 51 questions; `eval_recall.py` scores search on them (no
   model, no cost) and `eval_answers.py` runs the whole pipeline and checks every answer
   with a faithfulness judge (`judge.py`). `query.py` is a quick vector-search-only
   command for looking at what the database returns.

## Evaluation

Two rounds: 10 questions through the whole pipeline, then 51 questions that score search
and answers separately.

### Round 1: 10 questions

**Method:** 10 questions written from pages that are actually in the corpus: a
single fact, a paraphrase, a deep page, a list, a comparison, near-duplicate pages,
a false premise, a corpus gap, an off-topic question and a vague one. Each question
that has an answer also has an "evidence" string: text that must be in the retrieved
chunks for any model to answer correctly. That separates search failures from model
failures. `compare_retrieval.py` runs only the searches (no model, no cost), and
`ten_questions.py` runs the full pipeline through the API.

**Evidence found** (7 questions that have evidence):

| Search mode       | Top 5   | Top 10  | Automatic checks, all 10 questions (top 5) |
| ----------------- | ------- | ------- | ------------------------------------------ |
| vector            | 4/7     | 5/7     | 7/10                                       |
| bm25              | 3/7     | 5/7     | 6/10                                       |
| **hybrid**        | **5/7** | **6/7** | **8/10**                                   |
| hybrid + reranker | 4/7     | 5/7     | 7/10                                       |

With 10 questions, one question is 10 points, and the model's wording varies from
run to run, so read this as direction, not proof. Reading the answers against the
source pages showed more than the scores do:

- **Security fixes in 16.11.1** (the main failure): vector search refused, because
  only the page's two introduction chunks were retrieved. Hybrid listed all 5 fixes
  correctly. BM25 alone listed 4 and left out the most severe one (Path Traversal,
  CVSS 8.5). Hybrid + reranker listed only 2, both medium severity, and left out all
  three high-severity ones. Both partial lists were worded as if complete.
- **Push event payload:** the example has 19 top-level fields. Vector search's
  answer listed 15 and stopped at `project`; hybrid listed 17. Neither said the
  list was partial.
- **Executor comparison:** BM25 alone misread the compatibility table and said the
  Kubernetes executor does not support services. The table says it does. No
  automatic check caught this.
- **Reranker:** it moved the push-payload chunk down below three merge-request
  chunks, and put two Windows-executor developer pages above the executor list.
  Untested guess: this web-passage-trained model scores JSON, tables and release
  notes poorly.

### Round 2: 51 questions

**Method:** `eval_questions.jsonl` has 51 questions. 43 have a right page and an
"evidence" string that must appear in one retrieved chunk of that page. 8 have no page
(3 corpus gaps, 2 off-topic, 3 vague or too broad). I wrote them with the pages open, so
they share words with the pages and are easier than real users' questions. Q numbers
below are the numbers in that file. Two separate tests:

1. **Search** (`eval_recall.py`, no model, no cost): is the chunk that holds the answer in
   the top k results?
2. **Answers** (`eval_answers.py`): run the whole pipeline, compare the kind of reply
   (answered, refused, asked back) with the expected one, and ask a judge model whether
   every claim in the answer is backed by the 5 chunks the model was given. This is
   **faithfulness**, not correctness: an answer built from the wrong chunks can be
   faithful and wrong. The judge (Claude Sonnet 5.5, not the model that writes the
   answers) lists the claims and copies the words that back each one, and the code checks
   that those words are really in the chunk. As a check on the judge, answers judged
   against another question's chunks must come out unfaithful: 5 of 5 did, in both modes.

**Search** (43 scored questions):

| Search mode       | Right page, top 5 | Evidence, rank 1 | Evidence, top 5 | Evidence, top 10 |
| ----------------- | ----------------- | ---------------- | --------------- | ---------------- |
| vector            | 43/43             | 30/43            | 41/43           | 42/43            |
| bm25              | 42/43             | 31/43            | 39/43           | 42/43            |
| **hybrid**        | 43/43             | 34/43            | **42/43**       | **43/43**        |
| hybrid + reranker | 42/43             | **35/43**        | 41/43           | 41/43            |

**Answers** (all 51 questions, 5 chunks each; plain hybrid was not run):

| Measure                                      | vector      | hybrid + reranker |
| -------------------------------------------- | ----------- | ----------------- |
| Right kind of reply                          | 46/51 (90%) | 47/51 (92%)       |
| Answered, of the 43 the docs can answer      | 40/43       | 41/43             |
| Refused or asked back, of the 7 that must be | 5/7         | 5/7               |
| Faithful answers                             | 37/40 (92%) | 39/41 (95%)       |
| Claims backed by the chunks                  | 149/152     | 146/148           |

- The modes are hard to tell apart. Page recall is 98 to 100% for all four. Hybrid is
  best at evidence top 5 and top 10, and the reranker at rank 1, but the gaps are one to
  three questions. The two answer rows differ by one or two questions, and the 95%
  intervals overlap (reply type 79 to 96% and 81 to 97%).
- Q25 (which CVE was fixed in 17.0.1) is the one clear search effect. In vector search the
  chunk with the CVE was at rank 6, so the model saw the issue but no CVE number and
  refused. Hybrid + reranker had it in the top 5 and answered correctly.
- Most wrong replies are not search failures. Two false-premise questions (Q42, Q43) were
  labelled "refused" in both modes. In three of those four replies the fixed refusal
  sentence was followed by the right correction (for example that the feature is Premium
  and Ultimate only); the fourth had not retrieved the page. The prompt has no rule for a
  question whose premise the docs correct. A broad question (Q51) was refused instead of
  getting a clarifying question, and an off-topic request (Q48) did not get the fixed
  sentence in either mode.
- The judge flagged 5 answers. Reading them against the chunks: 2 are real errors (a fail
  fast testing answer said only 100 specs run when the page shows the complete job still
  runs all 1000; a CRIME answer said two conditions are needed when the page says one of
  two), 2 are borderline inferences and 1 is too strict ("0.3 is 30%"). I only read those
  5, not the answers it passed.
- Faithfulness is counted over the answers actually given, so a mode that refuses more
  has fewer chances to be wrong. Here both modes gave 41 answers.
- The whole run cost about $1.20 (about $0.60 per mode, 80% of it for the judge).

## Results

- 147 pages and 1,461 chunks (median 333 tokens, max 497; model limit 512).
- The failing question (security fixes in 16.11.1) is fixed by hybrid search.
- Hybrid was the best mode on this set; BM25 alone and the reranker did not help.
- On 51 questions, vector and hybrid + reranker gave 46 and 47 right kinds of reply and
  37 of 40 and 39 of 41 faithful answers: no difference I can show (see Round 2).
- Search takes a median of 60 ms (vector), 82 ms (hybrid) and 355 ms (with the
  reranker) in the 10-question test, and 90 ms (vector) and 361 ms (with the reranker) in
  the 51-question answer test. The model call takes 1.4 to 2 s, so the reranker adds 15 to
  25% to the wait. A search-only run, with nothing in between, was faster (12 ms and
  270 ms); I have not found out why.
- About 2,000 input tokens per question. Output was 120 to 160 tokens in the 10-question
  test and 78 on average over the 51 (refusals are short).
- Offline tests (`test_rag.py`, `test_api.py`, `test_hybrid.py`, `test_eval_recall.py`,
  `test_judge.py`, `test_eval_answers.py`) need no API key and no network. They use a fake
  model server and a stored vector as the query.

## Stack

Python · Chroma · sentence-transformers (`BAAI/bge-small-en-v1.5`,
`cross-encoder/ms-marco-MiniLM-L6-v2`) · own BM25 · Anthropic Claude Haiku 4.5
(answers) and Sonnet 5.5 (faithfulness judge) · FastAPI · BeautifulSoup + markdownify

## How to run

```bash
git clone https://github.com/vinnayakk/rag-assistant-with-evaluation && cd rag-assistant-with-evaluation
python3 -m venv .venv-rag && source .venv-rag/bin/activate     # Python 3.12 or newer
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."     # only needed to get answers; the code does not read .env

# build the data (about 150 pages, polite 1.5 s delay, stops if the site blocks you)
python download.py
python clean.py
python tidy.py outputs/clean_text_v2 outputs/clean_text_v3
# one extra command: I left out a page with an empty title whose content is writing-style
# instructions for AI tools, not product docs. If your sample contains it, move it aside:
mkdir -p outputs/excluded && mv outputs/clean_text_v3/runner_agents.md outputs/excluded/ 2>/dev/null || true
python build_url_map.py outputs/raw_html outputs/url_map.json
python chunk.py outputs/clean_text_v3 outputs/url_map.json outputs/chunks.jsonl
python check_chunks.py outputs/chunks.jsonl outputs/clean_text_v3
python embed_store.py outputs/chunks.jsonl outputs/chroma_db --reset

# ask a question
python rag.py "How do I limit memory for Gitaly?" --mode hybrid

# serve it
RAG_RETRIEVAL=hybrid uvicorn api:app           # then open http://127.0.0.1:8000/docs
curl -s localhost:8000/ask -H 'content-type: application/json' \
     -d '{"question": "Which executors does GitLab Runner support?"}'

# test and evaluate
RAG_DB=outputs/chroma_db python test_hybrid.py     # also test_rag.py, test_api.py
RAG_DB=outputs/chroma_db python test_eval_recall.py   # also test_eval_answers.py; test_judge.py needs no database
python compare_retrieval.py -k 10                  # 10 questions: search only, free
python ten_questions.py --mode hybrid              # 10 questions: full pipeline, needs the server running
python eval_recall.py --validate                   # 51 questions: check the file against the database
python eval_recall.py                              # search only, all four modes, free
python eval_answers.py --limit 3 --modes vector    # trial: 3 questions, a few cents
python eval_answers.py                             # vector and hybrid_rerank on all 51: about $1.20
```

`eval_answers.py` writes one set of files per mode (`outputs/eval_answers_<mode>.jsonl` and
`.md`). `--compare` rebuilds the results table from them without any model call.

An abridged reply from the last `curl`:

```json
{
  "mode": "hybrid",
  "status": "answered",
  "answer": "GitLab Runner supports the following executors [2]: Kubernetes, Docker, Docker Autoscaler, Instance ...",
  "citations": [
    {
      "n": 2,
      "title": "Executors",
      "section": "Introduction",
      "url": "https://docs.gitlab.com/runner/executors/"
    }
  ],
  "retrieved": [
    {
      "rank": 2,
      "title": "Executors",
      "section": "Introduction",
      "distance": 0.131,
      "bm25": 12.526,
      "rrf": 0.031
    }
  ],
  "timing_ms": { "search": 82, "llm": 2006 }
}
```

The sitemap changes over time, so a new download can give a different 150 pages than the
ones behind the numbers in this README (downloaded 2026-10-05; see [SOURCE.md](SOURCE.md)).
The default search mode is `vector`; set `RAG_RETRIEVAL=hybrid` (or pass `mode` in
the request) to change it. `RAG_MODEL` changes the answering model and
`RAG_RERANKER` the reranker (for example `BAAI/bge-reranker-base`).

## Messy parts of real documentation

The full list, with numbers and the decisions I made, is in [MESSY_NOTES.md](MESSY_NOTES.md).

- The first text extraction left about 9,300 punctuation-only lines, flattened
  tables and a "Was this page helpful?" widget on every page. Converting HTML to
  Markdown and a tidy step fixed most of it.
- Code-language labels (`shell`, `yaml`) sat on their own line before about 480
  code blocks, many indented inside list items, so the chunker has to restore them.
- Long JSON examples are cut across chunks, so one question can need 2 or 3 of them.
- Six pairs of chunks from different release-note pages are near-identical.
- The distance between a question and its best chunk can't tell a good match from
  a bad one (good 0.13 to 0.29, off-topic and vague 0.28 to 0.43), so a fixed
  cut-off would not catch unanswerable questions.
- The first site I tried (Shopify Help Center) blocked about 70% of requests with
  403 errors despite a permissive `robots.txt`. I didn't try to bypass it and
  switched to GitLab Docs.

## Known limitations and next steps

- 51 questions, one run each, written by me with the pages open. A difference of one to
  three questions is noise, and the modes can't be separated on this set. The next step is
  harder questions: written without the page open or taken from real users, with more
  version and CVE questions.
- The answer test compared vector with hybrid + reranker. Plain hybrid, the mode I
  chose, has no answer results yet (about $0.60 to run).
- The prompt has no rule for a question whose premise the docs correct (it refuses first
  and then corrects), and the model does not always follow the fixed sentence for
  off-topic requests or ask a clarifying question for a broad one.
- A partial list presented as a full list (the payload and the security fixes
  above) isn't detected by any check yet. Ideas: a prompt rule to say when a list
  looks cut off, and adding each hit's neighbouring chunks.
- Only one reranker was tried. A different one (`BAAI/bge-reranker-base`) is
  untested.
- The faithfulness judge is a language model, run once per answer, so a borderline
  answer can flip between runs. It checks an answer against the chunks, not against the
  truth, and I checked only the 5 answers it flagged. Correctness is still read by hand.
  Some evidence checks are strict (the push-payload tail; the "create a rule" steps; Q33,
  where another chunk also answers the question).
- Images are lost; only alt text remains (35 placeholders in 20 pages).
- The 150 pages are a random sample, so some topics are missing (for example the
  system hooks page).
- Answers vary slightly between runs because the SDK has no temperature setting, and
  the model doesn't always obey "reply with only this sentence" on refusals.

## Data and licence

The GitLab documentation is not included in this repository (`outputs/` is
git-ignored). `download.py` fetches it from docs.gitlab.com; run it yourself. GitLab
publishes its documentation under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
(it moved to that licence in 2018, see this
[merge request](https://gitlab.com/gitlab-org/gitlab-runner/-/merge_requests/893)).
The documentation text is © GitLab Inc.; anything built from it and redistributed (cleaned
text, chunks, test output) needs that attribution and the same licence. Details of what I
crawled and how are in [SOURCE.md](SOURCE.md). This is an independent learning project, not
affiliated with GitLab.

## License

Code: MIT, see [LICENSE](LICENSE). The GitLab documentation keeps its own licence (above).
