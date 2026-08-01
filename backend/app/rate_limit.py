import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_attempts: dict[str, deque] = defaultdict(deque)


def is_rate_limited(key: str, max_attempts: int, window_seconds: float) -> bool:
    """Sliding-window check: has `key` already made `max_attempts` calls
    within the last `window_seconds`? Records the current attempt as a
    side effect when it isn't rate limited."""
    now = time.monotonic()
    with _lock:
        attempts = _attempts[key]
        while attempts and now - attempts[0] > window_seconds:
            attempts.popleft()
        if len(attempts) >= max_attempts:
            return True
        attempts.append(now)
        return False


def reset() -> None:
    """Test hook: clear all tracked attempts."""
    with _lock:
        _attempts.clear()
