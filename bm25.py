import math, re
from collections import Counter, defaultdict

import numpy as np

STOP = set("""a an the is are was were be been being do does did how what which who whom when where why i you we they it its
of to in on for with and or not can could should would may might my your our this that these those there here from by as
at about into than then so if will""".split())
TOKEN = re.compile(r"[a-z0-9]+(?:[._\-/][a-z0-9]+)*")      # 'memory_bytes', '16.11.1', 'etc/gitlab/gitlab.rb' stay in one piece
LINK_TARGET = re.compile(r"\(https?://[^)\s]*\)")            # '(https://docs.gitlab.com/...)' is noise; the link TEXT stays


def _fold(word):
    """Tiny plural folding: 'executors' and 'executor' count as the same word. (Not a real stemmer.)"""
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text):
    """'Set memory_bytes in /etc/gitlab/gitlab.rb' -> ['set', 'memory_bytes', 'memory', 'byte', 'etc/gitlab/gitlab.rb', ...]
    Words with . _ - / are kept whole AND split into parts, so the question 'limit memory' still finds 'memory_bytes'
    while the question '16.11.1' finds exactly '16.11.1' (pure-number parts like '16' are dropped: too common)."""
    out = []
    for tok in TOKEN.findall(LINK_TARGET.sub("", text.lower())):
        parts = re.split(r"[._\-/]", tok)
        if len(parts) > 1:
            out.append(tok)
            out += [_fold(p) for p in parts if p and not p.isdigit() and p not in STOP]
        elif tok not in STOP:
            out.append(_fold(tok))
    return out


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        """docs: list of strings."""
        self.k1, self.b = k1, b
        tokens = [tokenize(d) for d in docs]
        self.n = len(docs)
        self.dl = np.array([len(t) for t in tokens], dtype=float)
        self.avgdl = self.dl.mean() if self.n else 1.0
        self.postings = defaultdict(list)                    # word -> [(chunk number, count), ...]
        for i, toks in enumerate(tokens):
            for w, c in Counter(toks).items():
                self.postings[w].append((i, c))
        self.idf = {w: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.postings.items()}

    def scores(self, query):
        """Score of every chunk for this query (0 = shares no word with it)."""
        s = np.zeros(self.n)
        for w in set(tokenize(query)):
            for i, tf in self.postings.get(w, ()):
                s[i] += self.idf[w] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
        return s

    def top(self, query, n, allowed=None):
        """-> [(chunk number, score)] best first, only chunks with score > 0. `allowed`: optional set of chunk numbers."""
        s = self.scores(query)
        if allowed is not None:
            mask = np.zeros(self.n, dtype=bool)
            mask[list(allowed)] = True
            s = np.where(mask, s, 0.0)
        order = np.argsort(-s, kind="stable")[:n]
        return [(int(i), float(s[i])) for i in order if s[i] > 0]
