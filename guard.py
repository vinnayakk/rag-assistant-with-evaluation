import hmac, threading, time
from datetime import datetime, timezone


class DailyCounter:
    """How many questions the whole app has taken today (UTC). Shared by every visitor, so it needs a lock."""

    def __init__(self, limit, today=None):
        self.limit = limit
        self._today = today or (lambda: datetime.now(timezone.utc).date())      # a function, so tests can change the day
        self._day = self._today()
        self._used = 0
        self._lock = threading.Lock()

    def _roll(self):
        if self._today() != self._day:                                          # a new day: start from zero
            self._day, self._used = self._today(), 0

    def take(self):
        """Use one question. False (and nothing used) when today's limit is reached. limit 0 or less means no limit."""
        with self._lock:
            self._roll()
            if self.limit > 0 and self._used >= self.limit:
                return False
            self._used += 1
            return True

    def give_back(self):
        """Return a question that was taken but never reached the model (the model's service said 'slow down' before it did any work)."""
        with self._lock:
            self._roll()
            self._used = max(0, self._used - 1)

    def used(self):
        with self._lock:
            self._roll()
            return self._used


class PasscodeGate:


    def __init__(self, passcode, fail_delay_s=1.0, sleep=time.sleep):
        self.passcode = passcode or ""
        self.fail_delay_s, self._sleep = fail_delay_s, sleep

    @property
    def required(self):
        return bool(self.passcode)

    def check(self, given):
        """-> 'ok' or 'wrong'. With no passcode set everything is 'ok'."""
        if not self.required:
            return "ok"
        # compare_digest takes the same time however many characters match; it wants bytes for non-ASCII text
        if hmac.compare_digest((given or "").encode("utf-8"), self.passcode.encode("utf-8")):
            return "ok"
        self._sleep(self.fail_delay_s)
        return "wrong"


class Guards:
    """Everything the page checks before it spends money, built once per process."""

    def __init__(self, passcode, daily_limit, max_questions):
        self.gate = PasscodeGate(passcode)
        self.daily = DailyCounter(daily_limit)
        self.max_questions = max_questions


_guards = None
_guards_lock = threading.Lock()


def get_guards(make):
    
    global _guards
    with _guards_lock:
        if _guards is None:
            _guards = make()
        return _guards


def reset():
    """Forget the guards (tests only)."""
    global _guards
    with _guards_lock:
        _guards = None


def int_setting(raw, default):
    
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default
