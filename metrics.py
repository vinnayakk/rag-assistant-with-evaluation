import json, math, os, pathlib, statistics, threading, uuid
from datetime import datetime, timezone
PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),        # also matches the dated id claude-haiku-4-5-20251001
    "claude-sonnet-5-5": (2.00, 10.00),
}

_lock = threading.Lock()                      # /ask runs in a thread pool: two requests can finish at the same moment


def log_path():
    return pathlib.Path(os.environ.get("RAG_REQUEST_LOG", "outputs/requests.jsonl"))


# ----------------------------------------------------------------------------- cost
def cost_usd(model, input_tokens, output_tokens):
    """Dollars for one call, or None when the model is not in the price table (None is not the same as free)."""
    if input_tokens is None or output_tokens is None:
        return None
    key = max((k for k in PRICES_PER_MTOK if str(model).startswith(k)), key=len, default=None)    # longest prefix wins
    if key is None:
        return None
    p_in, p_out = PRICES_PER_MTOK[key]
    return input_tokens / 1e6 * p_in + output_tokens / 1e6 * p_out


def cost_parts(model, input_tokens, output_tokens):
    """The same split into input / output / total, which is the shape Langfuse's cost_details wants. None if unpriced."""
    c = cost_usd(model, input_tokens, output_tokens)
    if c is None:
        return None
    key = max((k for k in PRICES_PER_MTOK if str(model).startswith(k)), key=len)
    p_in, p_out = PRICES_PER_MTOK[key]
    return {"input": input_tokens / 1e6 * p_in, "output": output_tokens / 1e6 * p_out, "total": c}


# ----------------------------------------------------------------------------- the log
def log_request(path=None, **fields):
    """Append one line. Never raises: a full disk or a bad path must not turn an answered question into an error."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "id": uuid.uuid4().hex[:12], **fields}
    path = pathlib.Path(path) if path else log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with _lock, path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as e:
        print(f"warning: could not write the request log {path}: {e}")
    return rec


def read_log(path=None):
    """-> (records, number of unreadable lines). A half-written or hand-edited line is skipped, not fatal."""
    path = pathlib.Path(path) if path else log_path()
    if not path.exists():
        return [], 0
    records, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if not isinstance(r, dict):
                raise ValueError
            records.append(r)
        except ValueError:
            bad += 1
    return records, bad


def select(records, mode=None, last=None):
    """Narrow to one search mode and/or the most recent N requests (in the order they were logged)."""
    if mode:
        records = [r for r in records if r.get("mode") == mode]
    return records[-last:] if last else records


# ----------------------------------------------------------------------------- the numbers
def percentile(values, p):
    """Nearest-rank percentile: the smallest value that at least p% of the values are at or below."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def _nums(records, key):
    return [r[key] for r in records if isinstance(r.get(key), (int, float))]


def _mean(values):
    return statistics.fmean(values) if values else None


def summarise(records):
    """Averages over a list of log records. Anything that cannot be computed is None, never a made-up zero."""
    done = [r for r in records if r.get("status") != "error"]
    total = _nums(done, "total_ms")
    costs = _nums(done, "cost_usd")
    statuses = {}
    for r in records:
        statuses[r.get("status", "?")] = statuses.get(r.get("status", "?"), 0) + 1
    return {
        "requests": len(records),
        "errors": len(records) - len(done),
        "statuses": statuses,
        "first_ts": records[0].get("ts") if records else None,
        "last_ts": records[-1].get("ts") if records else None,
        "latency_ms": {
            "mean": _mean(total), "median": statistics.median(total) if total else None, "p95": percentile(total, 95),
            "search_mean": _mean(_nums(done, "search_ms")), "llm_mean": _mean(_nums(done, "llm_ms")),
        },
        "cost_usd": {
            "mean": _mean(costs), "total": sum(costs) if costs else None,
            "per_1000": _mean(costs) * 1000 if costs else None,
            "unpriced": len(done) - len(costs),                       # answered requests whose model has no price
        },
        "tokens": {"input_mean": _mean(_nums(done, "input_tokens")), "output_mean": _mean(_nums(done, "output_tokens"))},
    }


def summarise_by_mode(records):
    modes = {}
    for r in records:
        modes.setdefault(r.get("mode") or "?", []).append(r)
    return {m: summarise(rs) for m, rs in sorted(modes.items(), key=lambda kv: -len(kv[1]))}


# ----------------------------------------------------------------------------- terminal view
def fmt_ms(v):
    return "-" if v is None else (f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.0f} ms")


def fmt_usd(v, digits=4):
    return "-" if v is None else f"${v:.{digits}f}"


if __name__ == "__main__":
    recs, bad = read_log()
    if not recs:
        raise SystemExit(f"{log_path()} has no requests yet. Start the server and ask something (see dashboard.py).")
    for name, s in [("all", summarise(recs)), *summarise_by_mode(recs).items()]:
        lat, cost = s["latency_ms"], s["cost_usd"]
        print(f"{name:14} {s['requests']:4} requests ({s['errors']} errors) | latency mean {fmt_ms(lat['mean'])}, "
              f"median {fmt_ms(lat['median'])}, p95 {fmt_ms(lat['p95'])} (search {fmt_ms(lat['search_mean'])}, "
              f"model {fmt_ms(lat['llm_mean'])}) | cost mean {fmt_usd(cost['mean'])}, total {fmt_usd(cost['total'])}")
    if bad:
        print(f"({bad} unreadable lines skipped)")
