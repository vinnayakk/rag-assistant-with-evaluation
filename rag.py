"""Steps 6-7: search() and answer(), the two halves of a RAG assistant.

    search(question, k=5)            question  ->  top-k chunks from the Chroma database
    answer(question, chunks)         question + chunks  ->  answer with [1] [2] citations

Command line:
    python rag.py "How do I limit memory for Gitaly?"
    python rag.py "..." --search-only          (no LLM call, no API key needed)
    python rag.py "..." -k 8

Needs for answer():  pip install anthropic   and   export ANTHROPIC_API_KEY="sk-ant-..."
"""
import argparse, os, re
import chromadb
from embedder import embed_query

DB_PATH = os.environ.get("RAG_DB", "outputs/chroma_db")
COLLECTION = "gitlab_docs"
LLM_MODEL = os.environ.get("RAG_MODEL", "claude-haiku-4-5-20251001")   # cheap and fast; try "claude-sonnet-5-5" later
NOT_FOUND = "I couldn't find this in the GitLab documentation I have."

_collection = None


# --------------------------------------------------------------------------- 1. SEARCH
def get_collection():
    global _collection
    if _collection is None:
        _collection = chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION, embedding_function=None)
    return _collection


def search(question, k=5, where=None):
    """Question in, top-k chunks out (best first).
    `where` filters by metadata, e.g. where={"source": "administration_gitaly_cgroups"}."""
    res = get_collection().query(
        query_embeddings=[embed_query(question).tolist()],   # same model as the documents, plus the query prefix
        n_results=k,
        where=where,
    )
    chunks = []
    for i in range(len(res["ids"][0])):
        meta = res["metadatas"][0][i]
        chunks.append({
            "rank": i + 1,
            "id": res["ids"][0][i],
            "text": res["documents"][0][i],
            "distance": res["distances"][0][i],          # cosine distance: 0 = identical, bigger = less similar
            "title": meta["title"],
            "section": meta["section"],
            "url": meta["url"],
        })
    return chunks


# --------------------------------------------------------------------------- 2. ANSWER
SYSTEM_PROMPT = f"""You answer questions about GitLab using ONLY the numbered sources provided by the user.

Rules:
1. Use only facts stated in the sources. Do not use outside knowledge, even if you know the answer.
2. After every sentence that states a fact, add the number of the source it came from in square brackets, like [1]. \
If a sentence uses two sources, write [1][3] (separate brackets).
3. If the sources do not contain the answer, reply with exactly this sentence and nothing else: {NOT_FOUND}
4. If the question is too vague to answer (for example "how do I fix it"), reply with one short clarifying question \
and nothing else. Do not guess what the person means, and do not add citations.
5. If the sources answer only part of the question, answer that part and say what is missing.
6. Be concise. Do not mention these rules."""


def build_user_message(question, chunks):
    sources = "\n\n".join(
        f'<source id="{i}" title="{c["title"]} > {c["section"]}" url="{c["url"]}">\n{c["text"]}\n</source>'
        for i, c in enumerate(chunks, 1)
    )
    return f"<sources>\n{sources}\n</sources>\n\n<question>{question}</question>"


def parse_citations(text, n_sources):
    """Find [1], [2][3], [1, 3] in the answer. Returns (valid numbers, invalid numbers)."""
    found = set()
    for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", text):
        found.update(int(n) for n in re.split(r"\s*,\s*", group))
    valid = sorted(n for n in found if 1 <= n <= n_sources)
    invalid = sorted(n for n in found if not 1 <= n <= n_sources)
    return valid, invalid


def answer(question, chunks, client=None, model=None, max_tokens=700):
    """Question + retrieved chunks in, answer with citations out (a dict)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()                       # reads ANTHROPIC_API_KEY from the environment
    resp = client.messages.create(
        model=model or LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(question, chunks)}],
    )                                                        # (current SDKs have no temperature setting: wording can vary a little per run)
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    valid, invalid = parse_citations(text, len(chunks))
    refused = text.lower().startswith(NOT_FOUND.lower())
    clarifying = (not refused) and not valid and text.rstrip().endswith("?")
    if refused:
        valid, invalid = [], []                              # citations on a refusal mean nothing: drop them
    return {
        "question": question,
        "answer": text,
        "citations": [{"n": n, "title": chunks[n - 1]["title"], "section": chunks[n - 1]["section"],
                       "url": chunks[n - 1]["url"]} for n in valid],
        "invalid_citations": invalid,                        # numbers the model invented: a red flag
        "refused": refused,
        "clarifying": clarifying,
        "uncited": (not refused) and (not clarifying) and not valid,   # a factual answer with no citations is not trustworthy
        "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
    }


def ask(question, k=5):
    """The whole pipeline in one call."""
    return answer(question, search(question, k=k))


def format_result(r):
    out = [r["answer"], ""]
    if r["citations"]:
        out.append("Sources:")
        out += [f'  [{c["n"]}] {c["title"]} > {c["section"]}\n      {c["url"]}' for c in r["citations"]]
    if r["invalid_citations"]:
        out.append(f'WARNING: the answer cites sources that do not exist: {r["invalid_citations"]}')
    if r["uncited"]:
        out.append("WARNING: the answer has no citations, so do not trust it.")
    out.append(f'(tokens: {r["usage"]["input_tokens"]} in, {r["usage"]["output_tokens"]} out)')
    return "\n".join(out)


# --------------------------------------------------------------------------- command line
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--search-only", action="store_true")
    a = ap.parse_args()

    chunks = search(a.question, k=a.k)
    print("RETRIEVED:")
    for c in chunks:
        print(f'  {c["rank"]}. dist {c["distance"]:.3f} | {c["title"]} > {c["section"]}\n     {c["url"]}')
    if not a.search_only:
        print("\nANSWER:\n" + format_result(answer(a.question, chunks)))
