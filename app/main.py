"""astrolift-sample-function — a minimal HTTP function for Knative Serving.

Topology fixture R5 of the spec-42 validation campaign: ``kind = function``.
It is a small, dependency-light Flask app designed for fast cold start and
scale-to-zero. Knative routes a request to a freshly-spun pod (cold start),
the function computes a small JSON response, and the pod is reaped once idle.

The compute endpoint does a tiny, deterministic numeric job (sum of squares
+ primality of ``n``) so a request always exercises real CPU work and returns
a verifiable payload — enough to prove a cold-started function actually ran,
without pulling in heavy numeric deps that would slow the cold start.

Routes (the spec-42 §3.1 debug contract):
  GET  /compute?n=<int>   -> computed JSON ({n, sum_of_squares, is_prime, ...})
  POST /                  -> same compute, ``n`` taken from JSON/form body
  GET  /health            -> 200 readiness/liveness probe
  GET  /debug             -> diagnostic JSON (app, version, kind=function, ...)
"""

from __future__ import annotations

import datetime as _dt
import os
import socket
import time

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Process-level constants captured once at import (cheap; survives per-request).
# ``uptime_s`` is measured from import, which on Knative is effectively the
# cold-start instant for the serving pod.
# ---------------------------------------------------------------------------
APP_NAME = "sample-function"
WORKLOAD_KIND = "function"
_STARTED_AT = time.monotonic()
_HOSTNAME = socket.gethostname()

# Build/version metadata is injected at image build time (see Dockerfile +
# build.yml) and surfaced through /debug so a running pod can be traced back
# to the exact commit and image that produced it.
_VERSION = os.environ.get("GIT_SHA", "dev")
_IMAGE = os.environ.get("IMAGE_REF", "")
_BUILT_AT = os.environ.get("BUILT_AT", "")

# Non-secret env keys we are willing to echo in /debug. We never dump the full
# environment (it can carry injected binding secrets); we report presence of a
# curated allowlist plus the standard runtime knobs.
_ECHO_ENV_KEYS = ("LOG_LEVEL", "PORT", "GIT_SHA", "IMAGE_REF", "BUILT_AT")

app = Flask(__name__)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _is_prime(n: int) -> bool:
    """Trial-division primality for small ``n`` (input is clamped by caller)."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    divisor = 3
    while divisor * divisor <= n:
        if n % divisor == 0:
            return False
        divisor += 2
    return True


def _compute(n: int) -> dict[str, object]:
    """The function's actual work: a small, deterministic numeric result.

    ``n`` is clamped to ``[0, 100000]`` so a hostile/huge value can't turn a
    scale-to-zero function into a CPU sink on cold start.
    """
    n = max(0, min(n, 100_000))
    sum_of_squares = sum(i * i for i in range(1, n + 1))
    return {
        "n": n,
        "sum_of_squares": sum_of_squares,
        "sum_1_to_n": n * (n + 1) // 2,
        "is_prime": _is_prime(n),
        "computed_at": _now_iso(),
    }


def _parse_n(raw: object, *, default: int = 10) -> int:
    """Coerce a request-supplied ``n`` to int, falling back to ``default``."""
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@app.get("/compute")
def compute_get() -> object:
    n = _parse_n(request.args.get("n"))
    return jsonify(_compute(n))


@app.post("/")
def compute_post() -> object:
    # Accept ``n`` from a JSON body or a form post; both are common ways a
    # caller (or an event source) drives a function.
    payload = request.get_json(silent=True) or {}
    raw = payload.get("n") if isinstance(payload, dict) else None
    if raw is None:
        raw = request.form.get("n")
    return jsonify(_compute(_parse_n(raw)))


@app.get("/health")
def health() -> object:
    # Readiness/liveness probe target (healthcheck.kind="http", value="/health").
    # The function has no external dependencies, so "imported and serving" is
    # the complete readiness condition.
    return jsonify({"status": "ok"}), 200


@app.get("/debug")
def debug() -> object:
    # The spec-42 §3.1 diagnostic surface. ``env_seen`` reports only the
    # presence of allowlisted non-secret keys (values are not echoed), so the
    # endpoint is safe to expose on a sample fixture.
    env_seen = [key for key in _ECHO_ENV_KEYS if os.environ.get(key) is not None]
    return jsonify(
        {
            "app": APP_NAME,
            "version": _VERSION,
            "kind": WORKLOAD_KIND,
            "hostname": _HOSTNAME,
            "uptime_s": round(time.monotonic() - _STARTED_AT, 3),
            "now": _now_iso(),
            "env_seen": env_seen,
            "bindings": {},  # this fixture attaches no managed services
            "build": {
                "image": _IMAGE,
                "built_at": _BUILT_AT,
                "commit": _VERSION,
            },
        }
    )


def _log_startup_banner() -> None:
    """Structured one-line startup banner (spec-42 §3.1).

    Logged at import so it appears on every cold start, making the serving
    pod's logs immediately useful for tracing scale-from-zero events.
    """
    port = os.environ.get("PORT", "8080")
    app.logger.info(
        "startup app=%s kind=%s version=%s hostname=%s listen_port=%s bindings=none",
        APP_NAME,
        WORKLOAD_KIND,
        _VERSION,
        _HOSTNAME,
        port,
    )


_log_startup_banner()


if __name__ == "__main__":
    # Local/dev entrypoint only. In the container gunicorn imports ``app`` and
    # owns the socket; this block is for ``python -m app.main`` on a laptop.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
