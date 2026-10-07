# Retrieval evaluation: 43 questions that have a page (8 more have none and are not scored here)

Page recall = the right page is among the top k chunks. Evidence recall = the chunk with the answer is. The interval is a 95% Wilson interval for page recall: with this few questions it is wide, so a gap between two modes smaller than the intervals is not evidence of anything on its own.

## Headline: top 5

| mode | page recall@5 | 95% interval | evidence recall@5 | MRR | median search |
|---|---|---|---|---|---|
| vector | **43/43 (100%)** | 92% to 100% | 41/43 (95%) | 0.96 | 12 ms |
| bm25 | **42/43 (98%)** | 88% to 100% | 39/43 (91%) | 0.97 | 1 ms |
| hybrid | **43/43 (100%)** | 92% to 100% | 42/43 (98%) | 0.96 | 13 ms |
| hybrid_rerank | **42/43 (98%)** | 88% to 100% | 41/43 (95%) | 0.98 | 270 ms |

Search time is the median over the questions (the middle one), so one slow search cannot distort it. It is the search only: no model loading, no answer.

## Page recall at different k

| mode | @1 | @3 | @5 | @10 |
|---|---|---|---|---|
| vector | 93% | 98% | 100% | 100% |
| bm25 | 95% | 98% | 98% | 98% |
| hybrid | 93% | 100% | 100% | 100% |
| hybrid_rerank | 98% | 98% | 98% | 100% |

## Evidence recall at different k (43 questions have evidence strings)

| mode | @1 | @3 | @5 | @10 |
|---|---|---|---|---|
| vector | 70% | 88% | 95% | 98% |
| bm25 | 72% | 84% | 91% | 98% |
| hybrid | 79% | 95% | 98% | 100% |
| hybrid_rerank | 81% | 95% | 95% | 95% |

## Page recall@5 by type of question

| type | n | vector | bm25 | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| api | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| crowded | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| deep | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| direct | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| error-message | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| false-premise | 2 | 2/2 | 2/2 | 2/2 | 1/2 |
| negation | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| number | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| paraphrase | 10 | 10/10 | 9/10 | 10/10 | 10/10 |
| procedure | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| table | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| version | 3 | 3/3 | 3/3 | 3/3 | 3/3 |

## Question by question against `vector`: page recall@5

Counting questions that changed is the fair way to compare two modes on the same questions. If a mode gains 3 and loses 3, it is not better, just different.

| mode | gained | lost | questions gained | questions lost |
|---|---|---|---|---|
| bm25 | 0 | 1 | - | Q22 |
| hybrid | 0 | 0 | - | - |
| hybrid_rerank | 0 | 1 | - | Q43 |

## Question by question against `vector`: evidence recall@5

| mode | gained | lost | questions gained | questions lost |
|---|---|---|---|---|
| bm25 | 1 | 3 | Q25 | Q22, Q40, Q43 |
| hybrid | 1 | 0 | Q25 | - |
| hybrid_rerank | 1 | 1 | Q25 | Q43 |

## Where the modes differ, or any mode misses

Each cell is: rank of the first chunk from the right page / rank at which the answer chunk has appeared. `-` means not in the top results at all; `n/a` means the question has no evidence strings. 23 questions are not listed because every mode ranks them the same and finds them in the top 5.

| question | type | vector | bm25 | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| Q3 | number | 1 / 2 | 1 / 5 | 1 / 2 | 1 / 1 |
| Q7 | direct | 1 / 1 | 1 / 2 | 1 / 1 | 1 / 1 |
| Q8 | direct | 1 / 2 | 1 / 1 | 1 / 1 | 1 / 1 |
| Q11 | direct | 1 / 1 | 1 / 2 | 1 / 1 | 1 / 2 |
| Q14 | direct | 1 / 2 | 1 / 1 | 1 / 1 | 1 / 1 |
| Q15 | direct | 1 / 1 | 1 / 2 | 1 / 1 | 1 / 2 |
| Q18 | paraphrase | 1 / 1 | 1 / 2 | 1 / 1 | 1 / 1 |
| Q19 | paraphrase | 1 / 2 | 1 / 4 | 1 / 2 | 1 / 1 |
| Q22 | paraphrase | 1 / 1 | - / - | 3 / 3 | 1 / 1 |
| Q23 | negation | 1 / 2 | 1 / 1 | 1 / 1 | 1 / 2 |
| Q24 | deep | 1 / 4 | 1 / 1 | 1 / 1 | 1 / 1 |
| Q25 | version | 4 / 6 | 1 / 1 | 1 / 2 | 1 / 3 |
| Q29 | crowded | 1 / 3 | 1 / 1 | 1 / 1 | 1 / 1 |
| Q32 | paraphrase | 2 / 2 | 1 / 1 | 2 / 2 | 1 / 1 |
| Q33 | table | 1 / - | 1 / 8 | 1 / 7 | 1 / - |
| Q37 | paraphrase | 2 / 3 | 2 / 2 | 2 / 2 | 1 / 1 |
| Q38 | direct | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 2 |
| Q40 | api | 1 / 1 | 1 / 7 | 1 / 1 | 1 / 1 |
| Q42 | false-premise | 1 / 5 | 1 / 4 | 1 / 5 | 1 / 3 |
| Q43 | false-premise | 1 / 4 | 1 / 6 | 1 / 3 | 6 / - |

## Misses at top 5 (right page not found)

**vector**: 0 missed

**bm25**: 1 missed: Q22
- Q22 (paraphrase) How does my instance tell me that a newer release, or a security fix, is available?
  - wanted /administration/settings/usage_statistics/
  - got: /development/gitlab_shell/process > Security releases; /development/gitlab_shell/process > Security releases; /releases/patches/patch-release-gitlab-16-10-3-released > Introduction

**hybrid**: 0 missed

**hybrid_rerank**: 1 missed: Q43
- Q43 (false-premise) How do I enable Windows Server 2019 hosted runners on GitLab.com?
  - wanted /ci/runners/hosted_runners/windows/ (found later, at rank 6)
  - got: /user/application_security/sast > Getting started; /user/application_security/sast > Getting started; /user/application_security/sast > Getting started

## Misses at top 5 (right page found, the chunk with the answer not)

**vector**: 2: Q25, Q33
- Q25 (version) Which CVE covers the 1-click account takeover through the Web IDE fixed in GitLab 17.0.1?
  - right page at rank 4, the answer chunk at rank 6
  - got: /releases/patches/patch-release-gitlab-18-3-1-released > Security fixes; /releases/patches/patch-release-gitlab-18-3-1-released > Security fixes; /releases/patches/patch-release-gitlab-16-11-1-released > Security fixes
- Q33 (table) I am moving off Kaniko. Which way of building images keeps my runners unprivileged?
  - right page at rank 1, the answer chunk not in the top results
  - got: /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit; /ci/docker/using_buildkit > Prerequisites; /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit

**bm25**: 3: Q33, Q40, Q43
- Q33 (table) I am moving off Kaniko. Which way of building images keeps my runners unprivileged?
  - right page at rank 1, the answer chunk at rank 8
  - got: /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit; /tutorials/issue_triage_complex_group > Next steps; /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit
- Q40 (api) How can I turn a label that belongs to one project into one the whole group can use, through the REST API?
  - right page at rank 1, the answer chunk at rank 7
  - got: /api/labels > Introduction; /user/packages/package_registry/enterprise_structure_tutorial > Set up a top-level group; /releases/19/gitlab-19-3-released > Co-created contributions
- Q43 (false-premise) How do I enable Windows Server 2019 hosted runners on GitLab.com?
  - right page at rank 1, the answer chunk at rank 6
  - got: /ci/runners/hosted_runners/windows > Introduction; /ci/runners/hosted_runners/windows > Supported shell; /runner/development/add-windows-version > Infrastructure

**hybrid**: 1: Q33
- Q33 (table) I am moving off Kaniko. Which way of building images keeps my runners unprivileged?
  - right page at rank 1, the answer chunk at rank 7
  - got: /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit; /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit; /ci/docker/using_buildkit > Prerequisites

**hybrid_rerank**: 1: Q33
- Q33 (table) I am moving off Kaniko. Which way of building images keeps my runners unprivileged?
  - right page at rank 1, the answer chunk not in the top results
  - got: /ci/docker/using_buildkit > Prerequisites; /ci/docker/using_buildkit > Troubleshooting; /ci/docker/using_buildkit > Migrate from Kaniko to BuildKit

