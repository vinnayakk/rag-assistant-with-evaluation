# Five wrong answers and why they went wrong

These come from the 51-question run of 2026-10-07: vector search and hybrid + reranker, 5 chunks each, answers by
Claude Haiku 4.5, checked against the expected reply type and by the faithfulness judge (Claude Sonnet 5.5). The raw
data is in `outputs/eval_answers_vector.jsonl` and `outputs/eval_answers_hybrid_rerank.jsonl`; Q numbers are the numbers
in `eval_questions.jsonl`. I picked five with five different causes, one for each stage where an answer can go wrong:
search, the reranker, the prompt, and the model twice (a made-up example, and a joined-up claim).

| # | Question | Mode | What the user would see | Where it went wrong |
| - | -------- | ---- | ----------------------- | ------------------- |
| 1 | Q25: which CVE covers the Web IDE account takeover fixed in 17.0.1? | vector | "I couldn't find this" | Search: near-duplicate release pages filled the top 5 |
| 2 | Q43: how do I enable Windows Server 2019 hosted runners? | hybrid + reranker | "I couldn't find this" | Reranker: moved the right page from rank 1 to rank 6 |
| 3 | Q42: how do I turn on merge request title validation on the Free tier? | both | "I couldn't find this", then the right answer | Prompt: no rule for a wrong premise |
| 4 | Q7: how does fail fast testing decide which specs to run? | vector | a correct answer plus a wrong example | Model: added a detail the page contradicts |
| 5 | Q11: how does GitLab protect against the CRIME vulnerability? | hybrid + reranker | a correct answer plus one overconfident sentence | Model: joined two statements into a claim no source makes |

Cases 1 to 3 were caught because the reply type was not the expected one. Cases 4 and 5 were caught only by the judge:
the reply type was "answered", the citations were valid, and nothing in the output looked wrong.

## How to investigate a wrong answer (with a Langfuse trace)

Every `/ask` request is one trace (see `tracing.py`): `ask` > `search` + `llm`. Four questions, in this order, find the
stage that failed:

1. **`search` output:** is the page that holds the answer in the list, and at which rank? If not, it is a search problem
   and nothing the model does can fix it. Each hit also carries the scores that put it there: `distance` (vector,
   smaller is closer), `bm25` (keywords, bigger is better), `rrf` (the fused order) and `rerank_score`. A `null` means
   that search did not return the chunk, so in hybrid mode it shows which of the two searches found it.
2. **`llm` input:** is the fact the answer needs in the text of the 5 chunks the model was given? (The full prompt is
   there.) A fact that is present but unused points at the prompt or the model.
3. **`llm` output:** what did the model actually say, and which claim is not in the input?
4. **Compare with another mode:** the same question under `vector` and `hybrid_rerank` shows whether the cause is search
   or the model. If the chunks differ and the answers differ, it is search; if the chunks match and the answers differ, it
   is the model.

The five write-ups below follow that order.

## 1. Q25 (vector): the right chunk was 6th, and the model refused correctly

**Question:** "Which CVE covers the 1-click account takeover through the Web IDE fixed in GitLab 17.0.1?"
**Expected:** an answer (CVE-2024-4835). **Got:** "I couldn't find this in the GitLab documentation I have", followed by
the observation that source 4 names the fix but gives no CVE number.

**Why:** the five chunks vector search returned were all "Security fixes" sections of patch-release pages: 18.3.1 (three
of them), 16.11.1 and 17.0.1. These pages share their layout and much of their wording, so a question about one of them
matches all of them. The 17.0.1 chunk at rank 4 is the table of fix titles (it contains "1-click account takeover via XSS
leveraging the VS code editor (Web IDE)", but no CVE number). The chunk that has the CVE text came 6th and was cut off by
`k=5`. The model read what it was given and refused, which was the right thing to do with those five chunks.

**Evidence:** in the search-only test the CVE chunk was at rank 6 for vector, rank 1 for BM25, rank 2 for hybrid and rank
3 for hybrid + reranker. With hybrid + reranker the chunk was in the model's 5 and the answer was `CVE-2024-4835 [3]`.
A version number and a CVE id are exact strings, which keyword search is good at and embeddings are not.

**What to change:** hybrid search already fixes it (it is the mode I use). Untested: collapse near-identical release-note
chunks into one before taking the top 5.

**In the trace:** the `search` output lists four patch-release pages and the `llm` input has no `CVE-` text for 17.0.1.

## 2. Q43 (hybrid + reranker): the reranker pushed the right page out of the top 5

**Question:** "How do I enable Windows Server 2019 hosted runners on GitLab.com?" The page only lists Windows 2022, so a good
answer says that. **Got:** "I couldn't find this", and the model mentioned Windows in a runner development document.

**Why:** the model was given three chunks from the SAST page ("Getting started") and two from "add-windows-version", a
GitLab Runner developer page. The hosted Windows runners page was not among them. Before reranking, the same search (hybrid)
had that page at rank 1 and its evidence chunk at rank 3; after reranking the page was at rank 6. The SAST chunk contains
"hosted runners for GitLab.com", "enabled by default" and "GitLab Runner on Windows Runners are not supported", so it repeats
most of the question's words, while the right page's first chunk has "Windows" and "hosted" but not "enable".

**Untested guess:** the reranker (`ms-marco-MiniLM`, trained on web passages) rewards chunks that repeat the question's
words. The same reranker moved the right chunk down in the 10-question test.

**What to change:** keep the reranker off (it is off). To test one change at a time: `BAAI/bge-reranker-base`, or rerank
only the top 10 instead of the top 30, and re-run the 51 questions.

**In the trace:** compare the `search` output of this trace with the one for the same question under `hybrid`. The
candidates are the same; only the order differs, which puts the blame on the reranker.

## 3. Q42 (both modes): "I couldn't find this", and then the answer

**Question:** "How do I turn on merge request title validation on the Free tier?" The feature is Premium and Ultimate only
(the page says "Tier: Premium, Ultimate"), so a good answer corrects the question. **Got (vector):** "I couldn't find this
in the GitLab documentation I have. However, the documentation indicates that merge request title validation is a Premium,
Ultimate feature [5], which means it is not available on the Free tier." Hybrid + reranker did the same (and also named GitLab Dedicated).

**Why:** all five chunks were from the right page, and the correction is right. The prompt's rule 3 says that when the sources
do not contain the answer the model must reply with the fixed sentence "and nothing else". The sources contain no steps for the
Free tier, so the model refused, and then added the explanation anyway (the prompt says not to; the model often does it). The
reply opens with a sentence that says the answer was not found and goes on to give it. The code counts it as `refused` and
drops the citations. The prompt has no rule for "the sources show that the question's premise is wrong".

**What to change (untested):** a prompt rule: if the sources show that the thing asked about is not available, say so and give
the reason, with citations; use the fixed sentence only when the sources say nothing on the topic. The risk is that the model
starts explaining on the unanswerable questions (Q44 to Q47), so re-run all 51 and check those four.

**In the trace:** nothing is missing from the `llm` input. That is the clue: right chunks, right facts, wrong label. It is the
prompt, not the search.

## 4. Q7 (vector): a correct answer with a wrong example added

**Question:** "How does fail fast testing decide which specs to run?" **Got:** the right first paragraph (the template maps
changed files to their spec files using the `tff` gem, `[1]`), then: "For example, if you change `app/models/example.rb`, fail fast
testing will only run the 100 specs related to that model, rather than running the entire test suite. [2]"

**Why:** the example is not true to the page. Source 2 is a table with two jobs side by side. The
`rspec-rails-modified-path-specs` column says "Runs 100 specs for `example.rb`", and the `rspec-complete` column, in the same
row, says "Runs all 1000 specs". The first chunk also says fail fast runs the relevant specs "before the rest of the suite runs".
The model took one column of the table and described it as the whole behaviour. The question did not ask for an example. The
judge marked the claim "contradicted", and I agree: reading the table, the full suite still runs.

**What to change (untested):** add to the prompt "answer only what is asked; do not add examples". A table with several columns
is also a place where models often read one column only.

**In the trace:** the facts are in the `llm` input, so search is fine. The wrong sentence is in the output and the table that
contradicts it is in source 2 of the input, which makes it quick to check by hand.

## 5. Q11 (hybrid + reranker): two statements joined into a claim no source makes

**Question:** "How does GitLab protect against the CRIME vulnerability?" **Got:** the main answer is supported (GitLab deactivates
Gzip when HTTPS is enabled, and the default compression level in the NGINX SPDY module is 0). Then: "Since CRIME requires both a
vulnerable protocol configuration and data compression (the 'C' in CRIME), disabling compression effectively neutralizes the
vulnerability even when SPDY is advertised. [2][3]"

**Why:** one chunk says a system "might be vulnerable ... if you use SSL Compression (for example, Gzip) or SPDY (which optionally
uses compression)", and says "CRIME relies on compression (the 'C')". A third chunk (a Nessus scanner report) says the service
"has one of two configurations that are known to be required for the CRIME attack: SSL/TLS compression is enabled. TLS advertises
the SPDY protocol earlier than version 4." The model fused these into "requires both A and B", which no source says, and the Nessus
text lists the two as alternatives. The judge labelled the claim "contradicted"; "unsupported" would have been a fair label too.

This is the weakest of the five and I include it for what it shows: **faithful is not the same as true, and unfaithful is not the
same as false.** The sentence is a plausible inference that sounds like a summary, which is why it passes a reader's quick check.
The judge can only say that no source states it.

**What to change (untested):** a prompt rule not to combine statements from different sources into a new claim, and to quote
conditions ("one of", "both") as the source words them.

**In the trace:** the `llm` input has all three chunks (sources 2 and 3 are the ones cited). Search worked.

## What I would do next, in order

1. Run `python eval_answers.py --modes hybrid` so the mode I actually use is in the comparison (about $0.60).
2. Change the prompt for cases 3 to 5 (false premise, no extra examples, no joined claims), one rule at a time, and re-run all
   51 questions after each. Cases 1 and 2 are search problems and the prompt cannot fix them.
3. Re-judge every mode compared under the same judge prompt (see `eval_answers.py --rejudge`). A better score from a changed
   judge proves nothing.

## Also seen (not written up)

- Q51 (a broad question I wrote): both modes refused instead of asking a clarifying question; the prompt's clarifying rule only
  mentions very vague questions like "how do I fix it".
- Q48 (an off-topic request, a haiku): neither mode used the fixed refusal sentence.
- 10-question test (see MESSY_NOTES.md): the push-event payload answer stopped at `project` because the JSON example is cut
  across chunks and the missing chunks were not retrieved (case: an incomplete list presented as complete), and the security
  fixes in 16.11.1 were refused because near-duplicate patch pages took the slots (the same cause as case 1).
