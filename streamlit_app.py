import contextlib, os, pathlib, re

import streamlit as st

HERE = pathlib.Path(__file__).resolve().parent
MAX_CHARS = 500                                           # the longest question accepted (api.AskRequest says the same)
ALL_MODES = ("vector", "bm25", "hybrid", "hybrid_rerank")
EXAMPLES = [
    "How do I limit memory for Gitaly?",
    "Which executors does GitLab Runner support?",
    "Which security issues were fixed in GitLab 16.11.1?",
    "How can I stop people from overwriting or deleting a container image tag once it has been pushed?",
]
REPO_URL = "https://github.com/vinnayakk/rag-assistant-with-evaluation"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

st.set_page_config(page_title="GitLab docs assistant", page_icon="📖", layout="centered",
                   initial_sidebar_state="collapsed")


# --------------------------------------------------------------------------- settings
SECRETS_ERROR = False
SECRETS_FILES = (pathlib.Path.home() / ".streamlit" / "secrets.toml", pathlib.Path.cwd() / ".streamlit" / "secrets.toml")   # where Streamlit looks


def setting(name, default=None):
    
    global SECRETS_ERROR
    value = os.environ.get(name)
    if value is None:
        try:
            value = st.secrets[name]
        except KeyError:                                   # the file is fine, it just has no such key
            value = None
        except Exception as e:
            # Streamlit raises "secrets file not found" both when there is no file and when there is one it cannot parse,
            # so a file that exists next to a "not found" is the broken case.
            if not isinstance(e, FileNotFoundError) or any(f.exists() for f in SECRETS_FILES):
                SECRETS_ERROR = True
            value = None
    return default if value is None else str(value)


# rag.py and tracing.py read their settings from os.environ when they are imported (RAG_MODEL, for instance, is read once at
# import time). So everything they need is copied there BEFORE the imports below. This is why the imports are not at the top.
for _name in ("ANTHROPIC_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "RAG_MODEL",
              "RAG_RETRIEVAL", "RAG_CANDIDATES", "RAG_TRACING", "RAG_REQUEST_LOG", "RAG_DB", "RAG_RERANKER"):
    _value = setting(_name)
    if _value is not None:
        os.environ[_name] = _value

import anthropic                                           # noqa: E402
from fastapi import HTTPException                         # noqa: E402
from pydantic import ValidationError                      # noqa: E402

import api, app_backend, guard, metrics, rag, tracing     # noqa: E402
from chat_text import (check_api_key, link_citations, md_text, own_key_problem, peak_memory_mb,   # noqa: E402
                       quiet_watcher_log, safe_url)

quiet_watcher_log()          # hides ~100 harmless "No module named 'torchvision'" warnings per page load (see chat_text.py)


def make_guards():
    return guard.Guards(passcode=setting("APP_PASSCODE", ""),
                        daily_limit=guard.int_setting(setting("APP_DAILY_LIMIT"), 200),
                        max_questions=guard.int_setting(setting("APP_MAX_QUESTIONS"), 20))


def owner_pays():
    
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def allowed_modes():
    wanted = [m.strip() for m in setting("APP_MODES", ",".join(ALL_MODES)).split(",")]
    modes = [m for m in ALL_MODES if m in wanted]
    return modes or list(ALL_MODES)


# --------------------------------------------------------------------------- the page
def show_answer(e):
    
    if e.get("error"):
        st.error(e["error"])
        return
    r = e["resp"]
    st.markdown(link_citations(r["answer"], r["citations"]))
    if r["status"] == "refused":
        st.caption("Not found in the documentation this assistant has. Try rephrasing, or search docs.gitlab.com.")
    elif r["status"] == "clarifying":
        st.caption("The assistant needs a clearer question.")
    elif r["status"] == "uncited":
        st.warning("This answer has no source numbers, so there is nothing to check it against. "
                   "Do not rely on it without looking it up in the GitLab docs.")
    if r["invalid_citations"]:
        st.warning("The answer points to source number(s) " + ", ".join(map(str, r["invalid_citations"])) +
                   " that do not exist. Treat it with care.")
    if r["citations"]:
        items = []
        for c in r["citations"]:
            link = safe_url(c["url"])
            label = md_text(f"{c['title']} > {c['section']}")
            items.append(f"{c['n']}. [{label}]({link})" if link else f"{c['n']}. {label}")
        st.markdown("**Sources**\n\n" + "\n".join(items))        # one block, so the list is tight
    with st.expander("What the search found"):
        cited = {c["n"] for c in r["citations"]}
        st.caption("The pieces of documentation the model was shown, best match first. Scores that don't apply to "
                   "this search mode are left out.")
        items = []
        for h in r["retrieved"]:
            scores = ", ".join(f"{name} {h[name]:.3f}" for name in ("distance", "bm25", "rrf", "rerank_score")
                               if h.get(name) is not None)
            mark = " · **cited**" if h["rank"] in cited else ""
            items.append(f"{h['rank']}. {md_text(h['title'])} > {md_text(h['section'])}  \n{scores}{mark}")
        st.markdown("\n".join(items))
    u, t = r["usage"], r["timing_ms"]
    secs = (t["search"] + t["llm"]) / 1000
    st.caption(f"{r['mode']} search · {secs:.1f} s · {u['input_tokens'] + u['output_tokens']:,} tokens · "
               f"about {metrics.fmt_usd(e.get('cost'))}")


def ask_question(question, mode, guards, backend, own_key=None):
    
    ss = st.session_state
    entry = {"q": question, "mode": mode}                  # only ever stored when it is at most MAX_CHARS long (checked next)
    if len(question) > MAX_CHARS:                          # the chat box limits this in the browser; a script need not
        return {**entry, "error": f"Please keep the question under {MAX_CHARS} characters."}, False
    try:
        req = api.AskRequest(question=question, k=5, mode=mode)
    except ValidationError:
        return {**entry, "error": "Please ask a longer question (at least 3 characters)."}, False
    if own_key is None:
        if ss.asked >= guards.max_questions:
            return {**entry, "error": f"You have used your {guards.max_questions} questions for this session. "
                                      "Reload the page to start again, or use your own API key (sidebar)."}, False
        if backend["client"] is None:
            return {**entry, "error": "This app has no API key of its own. Enter your own Anthropic API key to ask questions."}, False
        if not guards.daily.take():
            return {**entry, "error": "The daily limit of questions for this app has been reached. Please come back tomorrow, "
                                      "or use your own API key (sidebar)."}, False
        ss.asked += 1
    else:
        ss.asked_own += 1

    def give_back():                                       # the question never reached the model: it does not count
        if own_key is None:
            guards.daily.give_back()
            ss.asked -= 1
        else:
            ss.asked_own -= 1

    try:
        if own_key is None:
            resp = api.ask(req, backend["client"])         # the same function POST /ask runs
        else:
            with anthropic.Anthropic(api_key=own_key) as client:      # this visitor's client; closed again straight after
                resp = api.ask(req, client)
    except HTTPException as exc:
        api.log.error("ask failed: %s %s", exc.status_code, exc.detail)
        if exc.status_code == 429:                         # refused before any work was done: give the question back
            give_back()
            who = "The language model is busy right now" if own_key is None else "Anthropic is rate-limiting this key"
            return {**entry, "error": f"{who}. Please try again in a minute."}, False
        if own_key is not None:
            named = re.search(r"\((\w+)\)", str(exc.detail))        # api.ask puts the error type's name in brackets
            text, forget = own_key_problem(named.group(1) if named else "")
            if forget:                                     # the key itself was refused: ask for a new one
                ss.api_key = None
                ss.key_problem = text
            return {**entry, "error": text}, False
        return {**entry, "error": "The language model could not be reached. Please try again later."}, False
    except Exception:
        api.log.exception("ask failed")
        return {**entry, "error": "Something went wrong while answering. Please try again."}, False
    resp = resp.model_dump()
    cost = metrics.cost_usd(rag.LLM_MODEL, resp["usage"]["input_tokens"], resp["usage"]["output_tokens"])
    return {**entry, "resp": resp, "cost": cost}, True


KEY_HELP = (
    "**Get a key.** Sign in to the [Claude Console](https://platform.claude.com/settings/keys), open **Settings > API keys** and click "
    "**Create key**. The key starts with `sk-ant-` and the Console shows it only once. Questions are billed to your Anthropic account, "
    "so it needs some credit.\n\n"
    "**Is it safe to paste it here?**\n"
    "- Your key goes from your browser to this app's server, and from there to Anthropic with each question. The server keeps it in "
    "memory for this visit only: it is not written to a file, a log or a trace, and it is gone when you reload or close the page.\n"
    "- You are still trusting whoever runs this app and the service it runs on. The code is public "
    f"([GitHub]({REPO_URL})), but you cannot see what is deployed. So use a key made just for this, "
    "and delete it in the Console when you are done. A monthly spend limit can be set under **Settings > Billing**.\n"
    "- Your questions are also kept in the app's request log (see About in the sidebar)."
)


def own_key_form(name, button="Use this key"):
    
    with st.form(name):
        raw = st.text_input("Your Anthropic API key", type="password", placeholder="sk-ant-...")
        sent = st.form_submit_button(button)
    if sent:
        key, problem = check_api_key(raw)
        if problem:
            st.error(problem)
        else:
            st.session_state.api_key = key
            st.rerun()


def key_gate():
    
    st.title("GitLab docs assistant")
    st.info("This demo does not pay for your questions. To ask one, enter your own Anthropic API key. "
            "A question costs roughly 0.3 to 0.4 US cents on your key.")
    if problem := st.session_state.pop("key_problem", None):
        st.error(problem)
    own_key_form("own_key_gate")
    with st.expander("Where do I get a key, and is it safe to paste it here?"):
        st.markdown(KEY_HELP)
    st.stop()


def passcode_gate(gate):
    
    st.title("GitLab docs assistant")
    with st.form("passcode"):
        code = st.text_input("Passcode", type="password")
        sent = st.form_submit_button("Continue")
    if sent:
        if gate.check(code) == "ok":
            st.session_state.unlocked = True
            st.rerun()
        st.error("That is not the passcode.")
    st.stop()


def sidebar(modes, guards):
    ss = st.session_state
    with st.sidebar:
        st.header("Settings")
        default = os.environ.get("RAG_RETRIEVAL")
        default = default if default in modes else ("hybrid" if "hybrid" in modes else modes[0])
        mode = st.selectbox("Search mode", modes, index=modes.index(default), key="mode",
                            help="How the documentation is searched. hybrid mixes keyword and meaning search "
                                 "and was the best mode on the project's test questions.")
        counter = st.empty()                               # redrawn after each question, so it is never one step behind
        if st.button("Clear the conversation"):
            ss.history = []
            st.rerun()
        if ss.api_key:
            st.caption("Questions are billed to your own API key. The key is kept for this visit only.")
            if st.button("Remove my key"):
                ss.api_key = None
                st.rerun()
        elif owner_pays():
            with st.expander("Use your own API key"):
                st.caption("Your questions then go on your Anthropic account, not the app's, and the app's limits do not apply to you.")
                own_key_form("own_key_sidebar")
        with st.expander("About this app"):
            sent_to = "Anthropic's API (to write the answer)" + (" and to Langfuse (tracing)" if tracing.enabled() else "")
            st.markdown(
                "Answers come only from a sample of 147 pages of the GitLab documentation. Each question is answered on "
                "its own; the assistant does not remember earlier ones.\n\n"
                f"**Privacy.** Your question is sent to {sent_to}. The server also keeps a log of questions with their "
                "timing and cost. Do not type secrets or personal data. If you enter your own API key, the server keeps it in "
                "memory for this visit only (not in a file, a log or a trace) and uses it only to call Anthropic.\n\n"
                f"Code and evaluation: [GitHub]({REPO_URL}).")
        if setting("APP_SHOW_MEMORY", "1") != "0" and (mb := peak_memory_mb()) is not None:
            st.caption(f"Peak memory of this app: {mb:,.0f} MB")
    return mode, counter


def show_count(counter, guards):
    ss = st.session_state
    if ss.api_key:
        counter.caption(f"Questions this session: {ss.asked_own} (on your own key)")
    else:
        counter.caption(f"Questions this session: {ss.asked} of {guards.max_questions}")


def main():
    if SECRETS_ERROR:
        st.error("The secrets file exists but could not be read, so the app will not start (a passcode in it would be ignored). "
                 "The owner needs to fix the TOML in .streamlit/secrets.toml or in the app's Secrets box.")
        st.stop()
    ss = st.session_state
    ss.setdefault("history", [])
    ss.setdefault("asked", 0)
    ss.setdefault("pending", None)
    ss.setdefault("api_key", None)                         # the visitor's own Anthropic key, for this visit only
    ss.setdefault("asked_own", 0)
    guards = guard.get_guards(make_guards)
    ss.setdefault("unlocked", not guards.gate.required)
    if not ss.unlocked:
        passcode_gate(guards.gate)
    if not ss.api_key and not owner_pays():
        key_gate()

    try:
        slow = st.spinner("Loading the search index and the embedding model. The first start takes a minute or two...")
        with (contextlib.nullcontext() if app_backend.ready() else slow):
            backend = app_backend.get_backend(HERE)
    except app_backend.SetupError as e:
        st.error(str(e))
        st.stop()
    except Exception:
        api.log.exception("start-up failed")
        st.error("The assistant could not start. The owner can see why in the app's logs.")
        st.stop()

    mode, counter = sidebar(allowed_modes(), guards)
    show_count(counter, guards)

    st.title("GitLab docs assistant")
    st.caption("Ask a question about GitLab. Answers are written from the GitLab documentation, with numbered sources "
               "you can open. Each question is answered on its own; earlier ones are not remembered.")

    if problem := ss.pop("key_problem", None):           # (when the app has no key of its own, key_gate shows this instead)
        st.error(problem)

    typed = st.chat_input("Ask about GitLab...", max_chars=MAX_CHARS)
    question = typed or ss.pending
    ss.pending = None

    for e in ss.history:
        with st.chat_message("user"):
            st.markdown(md_text(e["q"]))
        with st.chat_message("assistant"):
            show_answer(e)

    if not ss.history and not question:
        st.markdown("**Try one of these**")
        for i, text in enumerate(EXAMPLES):
            st.button(text, key=f"example{i}", on_click=lambda t=text: ss.update(pending=t), width="stretch")

    if question:
        used_own_key = bool(ss.api_key)
        with st.chat_message("user"):
            st.markdown(md_text(question[:MAX_CHARS]))
        with st.chat_message("assistant"):
            with st.spinner("Searching the docs and writing an answer..."):
                entry, keep = ask_question(question, mode, guards, backend, own_key=ss.api_key)
                if keep:
                    # stored INSIDE the spinner block: when the visitor clicks something while the model is still working, Streamlit
                    # stops this run at its next st.* call (the spinner ending is one), and the answer, which is already paid for,
                    # must be in the conversation by then.
                    ss.history.append(entry)
            show_answer(entry)
        show_count(counter, guards)
        if used_own_key and not ss.api_key:
            st.rerun()                                     # Anthropic refused the key: draw the page again without it, with the reason

    st.divider()
    st.caption(
        "Unofficial demo, not affiliated with GitLab. Answers are generated from the GitLab documentation, © GitLab Inc., "
        f"licensed [CC BY-SA 4.0]({LICENSE_URL}); the pages were cleaned and split into chunks for search (changes made), "
        "and the answers are adaptations under the same licence. Source: https://docs.gitlab.com. "
        "An AI can be wrong: check the linked sources.")


main()
