import atexit, os, pathlib, shutil, tempfile, threading
import anthropic
import rag, tracing


class SetupError(Exception):
    pass


def find_database(here):
    explicit = os.environ.get("RAG_DB")
    if explicit:
        if not (pathlib.Path(explicit) / "chroma.sqlite3").exists():
            tracing.log.error("RAG_DB points to %r but there is no Chroma database there", explicit)
            raise SetupError("RAG_DB is set, but there is no Chroma database at that path. The owner can see which in the app's logs.")
        return explicit, False
    here = pathlib.Path(here)
    for sub, committed in (("outputs/chroma_db", False), ("data/chroma_db", True)):
        if (here / sub / "chroma.sqlite3").exists():
            return str(here / sub), committed
    raise SetupError("No search index found. Expected outputs/chroma_db (made by embed_store.py) or data/chroma_db "
                     "(the copy you commit for deployment).")


_backend = None
_lock = threading.Lock()


def ready():
    return _backend is not None


def get_backend(here):
    global _backend
    with _lock:
        if _backend is None:
            db, committed = find_database(here)
            if committed:
                # Chroma writes small files next to its database when it opens it. Work on a copy so the checked-out code is never written to.
                tmp = tempfile.mkdtemp(prefix="chroma_")
                atexit.register(shutil.rmtree, tmp, ignore_errors=True)
                db = shutil.copytree(db, os.path.join(tmp, "chroma_db"))
            if rag.DB_PATH != db:
                rag.DB_PATH, rag._collection, rag._corpus = db, None, None
            rag.get_collection()
            rag.embed_query("warm up")                     # loads the embedding model now, not on the first question
            rag.get_corpus()
            # the reranker model (hybrid_rerank only) loads on its first use; see APP_MODES in DEPLOY.md if memory is tight
            client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
            tracing.init()
            atexit.register(tracing.shutdown)              # send the traces still waiting when the app stops
            _backend = {"client": client}
        return _backend


def reset():
    """Forget the backend (tests only)."""
    global _backend
    with _lock:
        _backend = None