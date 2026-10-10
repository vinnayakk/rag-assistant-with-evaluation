import contextlib, logging, os, socket, ssl
from urllib.parse import urlparse

log = logging.getLogger("uvicorn.error")          # the same terminal as uvicorn's own messages

_client = None                                    # the Langfuse client, or None when tracing is off


# ----------------------------------------------------------------------------- start-up and shut-down
def _tls_problem(base_url):
    u = urlparse(base_url)
    if u.scheme != "https" or not u.hostname:
        return None                                   # plain http (a local test server): there is no certificate to check
    cafile = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE") or os.environ.get("OTEL_EXPORTER_OTLP_CERTIFICATE") or None
    try:
        context = ssl.create_default_context(cafile=cafile)      # cafile=None means: Python's own list, as the sender does
        with socket.create_connection((u.hostname, u.port or 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=u.hostname):
                pass
    except ssl.SSLCertVerificationError as e:         # must come before OSError: it is a kind of OSError
        return "cert", e.verify_message or str(e)
    except (OSError, ValueError) as e:
        return "other", f"{type(e).__name__}: {e}"
    return None


def init():
    """Call once when the server starts. Returns True when traces will be sent. Says in the log which it is, and why."""
    global _client
    _client = None
    if os.environ.get("RAG_TRACING", "").strip().lower() in ("0", "off", "false", "no"):
        log.info("tracing is off (RAG_TRACING=0)")
        return False
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        log.info("tracing is off: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to turn it on")
        return False
    try:
        from langfuse import Langfuse
    except ImportError:
        log.warning("tracing is off: the langfuse package is not installed (pip install langfuse)")
        return False
    try:
        client = Langfuse()                       # reads the LANGFUSE_* settings from the environment
    except Exception as e:
        log.warning("tracing is off: could not create the Langfuse client (%s: %s)", type(e).__name__, e)
        return False
    # Two checks at start-up, so that a wrong key, a wrong region or a certificate problem shows up NOW, not as silently missing
    # traces. The first one proves the keys and the region; the second proves the trace sender can verify Langfuse's certificate.
    keys_ok = False
    try:
        keys_ok = bool(client.auth_check())
        if not keys_ok:
            log.warning("tracing is on, but Langfuse did not accept the keys: check the keys and LANGFUSE_BASE_URL (region)")
    except Exception as e:                        # no network, bad URL, ...: keep serving, just without traces
        log.warning("tracing is on, but Langfuse could not be reached (%s: %s); traces may be lost", type(e).__name__, e)
    if keys_ok:
        problem = _tls_problem(getattr(client, "_base_url", None) or os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))
        if problem is None:
            log.info("tracing is on: connected to Langfuse")
        elif problem[0] == "cert":
            log.warning("tracing is on and Langfuse accepted the keys, but traces will probably NOT arrive: this Python cannot verify "
                        "Langfuse's certificate (%s). Fix, then restart: export OTEL_EXPORTER_OTLP_CERTIFICATE=\"$(python -c "
                        "'import certifi; print(certifi.where())')\"   (see the README, Observability)", problem[1])
        else:
            log.warning("tracing is on and Langfuse accepted the keys, but the trace sender could not open its own connection "
                        "(%s); traces may be lost", problem[1])
    _client = client
    return True


def shutdown():
    """Send what is still waiting. The SDK sends in batches in the background, so without this the last traces can be lost."""
    if _client is not None:
        try:
            _client.shutdown()
        except Exception as e:
            log.warning("could not flush traces: %s", e)


def enabled():
    return _client is not None


# ----------------------------------------------------------------------------- what api.py uses
class _Off:
    """Stands in for a Langfuse span when tracing is off: same calls, nothing happens."""
    id = None

    def update(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Trace:
    """One request. Make child steps with step() and generation(); both work as `with ... as s:` and have s.update(...)."""

    def __init__(self, root=None):
        self._root = root
        self.id = _client.get_current_trace_id() if (_client is not None and root is not None) else None

    def update(self, **kwargs):
        """Fill in the request's own output once it is known, for example output={"answer": ..., "status": ...}."""
        if self._root is not None:
            self._root.update(**kwargs)

    def step(self, name, as_type="span", **kwargs):
        if _client is None:
            return _Off()
        return _client.start_as_current_observation(name=name, as_type=as_type, **kwargs)

    def generation(self, name, model, **kwargs):
        """A call to a language model. Pass input=..., then g.update(output=..., usage_details=..., cost_details=...)."""
        return self.step(name, "generation", model=model, **kwargs)


@contextlib.contextmanager
def trace(name, input=None, mode=None):
    """The request as a whole: `with tracing.trace("ask", input=..., mode=...) as t:` ... and t.step(...) inside it.
    `mode` becomes a tag and metadata on every step, so the Langfuse trace list can be filtered by search mode."""
    if _client is None:
        yield Trace()
        return
    from langfuse import propagate_attributes
    attrs = dict(trace_name=name)
    if mode:
        attrs.update(tags=[mode], metadata={"mode": mode})
    with propagate_attributes(**attrs):           # must be set before the steps are created: they inherit it
        with _client.start_as_current_observation(name=name, as_type="span", input=input) as root:
            yield Trace(root)
