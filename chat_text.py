import logging, re, sys
from urllib.parse import urlsplit

_CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)        # fenced blocks and `inline code`: markdown must not be touched inside
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")           # [1]  [1, 3]
_IMAGE = re.compile(r"!\[([^\]\n]*)\]\([^)\n]*\)")          # ![alt](address)
_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*([^)\s]*)[^)\n]*\)")   # [text](address)
_REFDEF = re.compile(r"^[ \t]*\[[^\]\n]+\]:[ \t]*\S.*$", re.M)  # [name]: address   (the other way to write a link)
LINK_HOSTS = ("docs.gitlab.com", "about.gitlab.com", "gitlab.com")      # links the model may write itself


def outside_code(text, fn):
    
    parts = _CODE.split(text)                              # the code pieces are the odd positions
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))


def md_text(s):
    
    return re.sub(r"([\\`*_{}\[\]()<>#+!|~$])", r"\\\1", str(s))


def safe_url(url):
   
    if not str(url).startswith(("http://", "https://")):
        return None
    return str(url).replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _plain_link(m):
    
    text, url = m.group(1), m.group(2)
    try:
        parts = urlsplit(url)
        trusted = parts.scheme == "https" and (parts.hostname or "").lower() in LINK_HOSTS
    except ValueError:
        trusted = False
    if trusted:
        return m.group(0)
    return f"{text} (`{url.replace('`', '')}`)" if url else text


def tame_links(text):
    
    text = _IMAGE.sub(lambda m: m.group(1), text)
    text = _REFDEF.sub("", text)
    return _LINK.sub(_plain_link, text)


def link_citations(text, citations):
    
    urls = {c["n"]: safe_url(c["url"]) for c in citations}

    def one(m):
        nums = [int(n) for n in re.split(r"\s*,\s*", m.group(1))]
        return ", ".join(f"[[{n}]]({urls[n]})" if urls.get(n) else f"\\[{n}\\]" for n in nums)

    def prose(p):
        p = re.sub(r"(?<!\\)\$", r"\\$", p)
        return tame_links(_CITE.sub(one, p))

    return outside_code(text, prose)


def check_api_key(raw):
    
    key = (raw or "").strip()
    if not key:
        return None, "Please paste your Anthropic API key."
    if not key.isascii() or any(ch.isspace() for ch in key) or len(key) > 300:
        return None, "That does not look like an API key: it should be one piece of text with no spaces or line breaks."
    if not key.startswith("sk-ant-") or len(key) < 20:
        return None, "That does not look like an Anthropic API key. Keys start with sk-ant-."
    return key, None


def own_key_problem(error_name):
    
    if error_name == "AuthenticationError":
        return "Anthropic did not accept this key. Please check it and enter it again.", True
    if error_name == "PermissionDeniedError":
        return "Anthropic says this key is not allowed to do that. Check the key's permissions in the Claude Console.", False
    if error_name == "BadRequestError":
        return ("Anthropic rejected the request. One common reason is an account with no credit left: "
                "look under Settings > Billing in the Claude Console."), False
    return "The language model could not be reached. Please try again later.", False


class _TorchvisionNoise(logging.Filter):

    def filter(self, record):
        err = record.exc_info[1] if record.exc_info else None
        return not (isinstance(err, ModuleNotFoundError) and err.name == "torchvision")


def quiet_watcher_log():
   
    log = logging.getLogger("streamlit.watcher.local_sources_watcher")
    if not any(isinstance(f, _TorchvisionNoise) for f in log.filters):
        log.addFilter(_TorchvisionNoise())


def peak_memory_mb():
   
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024     # macOS counts bytes, Linux counts KB
