import json, os, re, unicodedata

import rag

JUDGE_MODEL = os.environ.get("RAG_JUDGE_MODEL", "claude-sonnet-5-5")     # not the model that writes the answers (rag.LLM_MODEL)
VERDICTS = ["supported", "unsupported", "contradicted"]

JUDGE_SYSTEM = """You check whether an ANSWER is backed by the numbered SOURCES it was written from.

Do this:
1. Split the answer into separate factual claims. One fact per claim. Split sentences joined by "and" or a list into \
their parts. Keep numbers, names, versions and setting names exactly as the answer has them.
2. Decide each claim using ONLY the sources, never your own knowledge:
   - supported: the sources state it, or it follows directly from what they state without adding any fact.
   - unsupported: the sources do not say it. This holds even when the claim is true in the real world.
   - contradicted: a source says something different (another number, name, version, setting or condition).
3. For a supported claim give the number of the source and a quote copied EXACTLY, letter for letter, from that source \
(at most 25 words; use "..." to skip words). For any other claim give source 0 and an empty quote.

Rules:
- Ignore citation marks like [1] in the answer. They are not evidence; read the source text yourself.
- A sentence that only says something is missing from the sources ("the sources do not say how...") is not a claim.
- Do not judge whether the answer is complete, useful or well written. Only whether each claim is backed.
- Be strict about numbers, versions, names and settings: a different value is contradicted, not supported.
- If the answer contains no factual claims, return an empty list."""

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                # the order matters: the model writes these left to right, so it must find the quote BEFORE it decides
                "properties": {
                    "claim": {"type": "string", "description": "one fact from the answer, numbers and names unchanged"},
                    "source": {"type": "integer", "description": "number of the source that states it; 0 if none does"},
                    "quote": {"type": "string", "description": "words copied exactly from that source; empty if source is 0"},
                    "verdict": {"type": "string", "enum": VERDICTS},
                    "note": {"type": "string", "description": "for unsupported or contradicted: why, in a few words; else empty"},
                },
                "required": ["claim", "source", "quote", "verdict", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims"],
    "additionalProperties": False,
}


class JudgeError(Exception):
    """The judge did not give a usable verdict (cut off, refused, or not valid JSON). Not the same as 'unfaithful'."""


# ----------------------------------------------------------------------------- checking the judge's quotes
def squash(s):
    """Make two texts comparable: same quote marks, no markdown emphasis, one space between words, lower case."""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"})
    s = re.sub(r"[`*]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in(quote, text):
    """Are the words the judge 'copied' really in the source? Pieces separated by ... must each be there.
    Under 8 letters in total is too short to prove anything (a single common word would always be found)."""
    pieces = [squash(p) for p in re.split(r"\.\.\.|…", quote)]
    pieces = [p for p in pieces if p]
    if sum(len(p) for p in pieces) < 8:
        return False
    hay = squash(text)
    return all(p in hay for p in pieces)


def check_quotes(claims, chunks):
    """Keep a claim 'supported' only if its quote is in the source it names (or, failing that, in another source:
    then the source number is corrected). Anything else is downgraded to unsupported: the judge cannot vouch for itself."""
    out = []
    for c in claims:
        c = dict(c, downgraded=False, quote_found=None)
        n = c["source"] if isinstance(c["source"], int) else 0
        if c["quote"].strip():
            where = [n] if 1 <= n <= len(chunks) else []
            where += [i for i in range(1, len(chunks) + 1) if i not in where]
            hit = next((i for i in where if quote_in(c["quote"], chunks[i - 1]["text"])), None)
            c["quote_found"] = hit is not None
            if hit is not None:
                c["source"] = hit
        if c["verdict"] == "supported" and not c["quote_found"]:
            why = "the judge gave no quote" if not c["quote"].strip() else "the judge's quote is not in the sources"
            c.update(verdict="unsupported", downgraded=True, note=(why + ". " + c["note"]).strip())
        out.append(c)
    return out


def summarise(claims):
    n = len(claims)
    ok = sum(1 for c in claims if c["verdict"] == "supported")
    return {
        "verdict": "no_claims" if n == 0 else ("faithful" if ok == n else "unfaithful"),
        "score": None if n == 0 else ok / n,
        "n_claims": n, "n_supported": ok,
        "n_contradicted": sum(1 for c in claims if c["verdict"] == "contradicted"),
        "claims": claims,
    }


# ----------------------------------------------------------------------------- the judge call
def build_judge_message(question, chunks, answer):
    """The judge sees the sources exactly as the answering model saw them (same function), then the answer."""
    return f"{rag.build_user_message(question, chunks)}\n\n<answer>\n{answer}\n</answer>"


def judge_answer(question, chunks, answer, client, model=None, max_tokens=2500):
    """-> dict with verdict ('faithful' | 'unfaithful' | 'no_claims'), score, claims, usage. Raises JudgeError."""
    resp = client.messages.create(
        model=model or JUDGE_MODEL,
        max_tokens=max_tokens,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": build_judge_message(question, chunks, answer)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},      # the reply is JSON that fits SCHEMA
    )
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    if resp.stop_reason in ("max_tokens", "refusal"):
        raise JudgeError(f"the judge stopped early ({resp.stop_reason}); its JSON is not usable")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        claims = json.loads(text)["claims"]
    except (ValueError, KeyError, TypeError) as e:
        raise JudgeError(f"the judge's reply was not the expected JSON ({type(e).__name__}): {text[:200]!r}")
    result = summarise(check_quotes(claims, chunks))
    result["usage"] = usage
    result["model"] = model or JUDGE_MODEL
    return result


# ----------------------------------------------------------------------------- command line: try it on one answer
if __name__ == "__main__":
    import argparse, anthropic
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("answer")
    ap.add_argument("--mode", default=None, help="search mode that finds the sources (default: rag's default)")
    a = ap.parse_args()
    chunks = rag.search(a.question, k=5, mode=a.mode)
    r = judge_answer(a.question, chunks, a.answer, anthropic.Anthropic())
    print(f"{r['verdict']}: {r['n_supported']}/{r['n_claims']} claims supported ({r['model']})")
    for c in r["claims"]:
        print(f"  [{c['verdict']}] {c['claim']}" + (f"\n      source {c['source']}: \"{c['quote']}\"" if c["quote"] else "")
              + (f"\n      note: {c['note']}" if c["note"] else ""))
