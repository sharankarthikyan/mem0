"""
Transient-failure retry helpers for serverless dependencies.

When OpenMemory runs on Railway (or any platform) with Qdrant and Postgres as
serverless services that scale to zero, the first request after an idle period
must wake those services. While a dependency cold-starts, connection attempts
are refused or time out for a few seconds. Without retries the dependent MCP
request fails immediately even though the dependency would have been ready a
moment later.

This module provides a single retry policy, tuned for cold-start windows:
exponential backoff over a bounded total time, retrying ONLY on transient
connection/timeout errors — never on application/logic errors. That distinction
matters for non-idempotent operations (e.g. mem0 ``add``): a connection error
means the request never reached the server, so replaying it is safe; a logic
error is surfaced immediately without a replay.

All knobs are env-tunable so the budget can be matched to a deployment's cold
start latency and the calling MCP client's request timeout:
  OPENMEMORY_RETRY_ATTEMPTS      max attempts (default 7)
  OPENMEMORY_RETRY_INITIAL_WAIT  first backoff in seconds (default 0.5)
  OPENMEMORY_RETRY_MAX_WAIT      cap per backoff in seconds (default 8.0)
With the defaults the total wait before giving up is ~30s.
"""

import logging
import os
import socket

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = int(os.environ.get("OPENMEMORY_RETRY_ATTEMPTS", "7"))
_RETRY_INITIAL_WAIT = float(os.environ.get("OPENMEMORY_RETRY_INITIAL_WAIT", "0.5"))
_RETRY_MAX_WAIT = float(os.environ.get("OPENMEMORY_RETRY_MAX_WAIT", "8.0"))


# --- Transient exception detection -----------------------------------------
# Dependency client libraries are optional/duck-typed here: import what is
# available and fall back to message matching so we stay robust to mem0 wrapping
# the underlying driver exception in its own type.

def _collect_transient_types():
    types = [ConnectionError, TimeoutError, socket.timeout, socket.gaierror, OSError]

    try:
        import psycopg2  # type: ignore

        types.append(psycopg2.OperationalError)
        types.append(psycopg2.InterfaceError)
    except Exception:  # pragma: no cover - driver optional
        pass

    try:
        from sqlalchemy.exc import OperationalError, InterfaceError, DBAPIError  # type: ignore

        types.extend([OperationalError, InterfaceError, DBAPIError])
    except Exception:  # pragma: no cover
        pass

    try:
        import httpx  # type: ignore

        types.extend([httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError])
    except Exception:  # pragma: no cover
        pass

    try:
        import requests  # type: ignore

        types.append(requests.exceptions.ConnectionError)
        types.append(requests.exceptions.Timeout)
    except Exception:  # pragma: no cover
        pass

    try:
        from qdrant_client.http.exceptions import ResponseHandlingException  # type: ignore

        types.append(ResponseHandlingException)
    except Exception:  # pragma: no cover
        pass

    return tuple(types)


_TRANSIENT_TYPES = _collect_transient_types()

# Substrings that signal a connection/cold-start failure even when wrapped in a
# generic exception type. Lower-cased before matching.
_TRANSIENT_MESSAGES = (
    "connection refused",
    "connection reset",
    "connection aborted",
    "connection closed",
    "could not connect",
    "failed to connect",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "name or service not known",
    "no route to host",
    "max retries exceeded",
    "server disconnected",
    "broken pipe",
    "503 service unavailable",
    "502 bad gateway",
    "504 gateway timeout",
)


def is_transient(exc: BaseException) -> bool:
    """True if ``exc`` looks like a recoverable cold-start/connection failure.

    Matches on known driver exception types OR a connection-flavored message.
    Deliberately conservative: anything that is not clearly transient is treated
    as a real error and surfaced without a retry.
    """
    if isinstance(exc, _TRANSIENT_TYPES):
        return True
    message = str(exc).lower()
    return any(token in message for token in _TRANSIENT_MESSAGES)


# --- Retry policy ----------------------------------------------------------

# Shared tenacity decorator. reraise=True so the ORIGINAL exception propagates
# after the budget is exhausted (callers keep their existing except handling).
transient_retry = retry(
    retry=retry_if_exception(is_transient),
    wait=wait_exponential(multiplier=_RETRY_INITIAL_WAIT, max=_RETRY_MAX_WAIT),
    stop=stop_after_attempt(_RETRY_ATTEMPTS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


def call_with_retry(func, *args, **kwargs):
    """Invoke ``func(*args, **kwargs)`` under the transient retry policy.

    Use at call sites where decorating the target function is not practical
    (e.g. methods on a third-party client instance like the mem0 memory client).
    """
    wrapped = transient_retry(func)
    return wrapped(*args, **kwargs)
