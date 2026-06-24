"""Tests for the transient-failure retry policy used for serverless deps."""

import importlib

import pytest


@pytest.fixture
def fast_resilience(monkeypatch):
    """Reload the resilience module with a zero-backoff, small-attempt budget so
    retry behavior can be asserted without real sleeps."""
    monkeypatch.setenv("OPENMEMORY_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("OPENMEMORY_RETRY_INITIAL_WAIT", "0")
    monkeypatch.setenv("OPENMEMORY_RETRY_MAX_WAIT", "0")
    import app.utils.resilience as resilience

    return importlib.reload(resilience)


def test_is_transient_matches_connection_error_types(fast_resilience):
    assert fast_resilience.is_transient(ConnectionError("connection refused"))
    assert fast_resilience.is_transient(TimeoutError("timed out"))
    assert fast_resilience.is_transient(OSError("no route to host"))


def test_is_transient_matches_message_substrings(fast_resilience):
    # A generic exception type still counts when the message is connection-flavored.
    assert fast_resilience.is_transient(Exception("503 Service Unavailable"))
    assert fast_resilience.is_transient(RuntimeError("Max retries exceeded with url"))
    assert fast_resilience.is_transient(Exception("could not connect to server"))


def test_is_transient_rejects_logic_errors(fast_resilience):
    assert not fast_resilience.is_transient(ValueError("invalid memory id"))
    assert not fast_resilience.is_transient(KeyError("results"))
    assert not fast_resilience.is_transient(Exception("404 not found"))


def test_call_with_retry_recovers_after_transient_failures(fast_resilience):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("connection refused")
        return "ok"

    assert fast_resilience.call_with_retry(flaky) == "ok"
    assert calls["n"] == 3


def test_call_with_retry_does_not_retry_logic_errors(fast_resilience):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ValueError("invalid memory id")

    with pytest.raises(ValueError):
        fast_resilience.call_with_retry(boom)
    assert calls["n"] == 1  # surfaced immediately, no replay


def test_call_with_retry_reraises_original_after_exhausting_budget(fast_resilience):
    calls = {"n": 0}

    def always_down():
        calls["n"] += 1
        raise ConnectionError("connection refused")

    with pytest.raises(ConnectionError):
        fast_resilience.call_with_retry(always_down)
    assert calls["n"] == 4  # OPENMEMORY_RETRY_ATTEMPTS


def test_call_with_retry_forwards_args_and_kwargs(fast_resilience):
    def add(a, b, *, c=0):
        return a + b + c

    assert fast_resilience.call_with_retry(add, 1, 2, c=3) == 6
