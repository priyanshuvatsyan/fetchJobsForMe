"""Cooperative cancellation shared by every portal fetch."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancel = threading.Event()
_hold = threading.Event()
_token = 0


def arm() -> int:
    """Start a new fetch generation. Older workers should leave their loops."""
    global _token
    with _lock:
        _token += 1
        current = _token
    _cancel.clear()
    _hold.clear()
    return current


def cancel() -> None:
    """Stop in-flight portal work and do not auto-start it again."""
    _cancel.set()
    _hold.set()


def cancelled() -> bool:
    return _cancel.is_set()


def held() -> bool:
    return _hold.is_set()


def token() -> int:
    with _lock:
        return _token


def stale(started: int) -> bool:
    """True when this run was stopped or a newer refresh replaced it."""
    return cancelled() or token() != started


def pause(seconds: float) -> bool:
    """Wait up to `seconds`. Return True if the fetch was cancelled while waiting."""
    if seconds <= 0:
        return cancelled()
    return _cancel.wait(timeout=seconds)
