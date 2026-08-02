"""Shared (cross-process) cost-budget ledger backed by Redis.

Enforces the same daily-spend / request-count accounting as the in-process
:class:`~brompt.config.BudgetConfig` counters, but stored in Redis so that
multiple client instances, processes and replicas agree on the same budget.

Design
------
* Keys are date-scoped: ``<prefix>:<YYYY-MM-DD>:spent`` and
  ``<prefix>:<YYYY-MM-DD>:count`` with a ~49 hour TTL, so a new calendar day
  starts a fresh budget and stale keys expire without any cleanup job.
* ``add_cost`` is atomic via a Redis pipeline (``INCRBYFLOAT`` + ``INCR`` +
  ``EXPIRE``) — no Lua scripting, so it works with fakeredis and restricted
  Redis deployments alike.

Usage
-----
``BudgetConfig(max_daily_cost=..., backend=RedisBudgetLedger.from_url(url))``
"""

from __future__ import annotations

import datetime
from typing import Optional

try:
    import redis as _redis

    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _REDIS_AVAILABLE = False
    _redis = None  # type: ignore[assignment]

_KEY_TTL_SECONDS = 49 * 3600  # ~2 days, covers the longest day + margin


def _day_stamp(now: Optional[datetime.datetime] = None) -> str:
    return (now or datetime.datetime.now()).strftime("%Y-%m-%d")


class RedisBudgetLedger:
    """Redis-backed :class:`~brompt.config.BudgetBackend`."""

    def __init__(self, redis_client, key_prefix: str = "brompt:budget"):
        if _redis is None:
            raise ImportError(
                "The 'redis' package is required for RedisBudgetLedger. "
                "Install it with `pip install redis`."
            )
        self._client = redis_client
        self._prefix = key_prefix.rstrip(":")

    @classmethod
    def from_url(cls, url: str, key_prefix: str = "brompt:budget") -> "RedisBudgetLedger":
        if _redis is None:
            raise ImportError(
                "The 'redis' package is required for RedisBudgetLedger. "
                "Install it with `pip install redis`."
            )
        client = _redis.from_url(url)
        return cls(client, key_prefix=key_prefix)

    def _spent_key(self, day: Optional[str] = None) -> str:
        return f"{self._prefix}:{day or _day_stamp()}:spent"

    def _count_key(self, day: Optional[str] = None) -> str:
        return f"{self._prefix}:{day or _day_stamp()}:count"

    def spent(self) -> float:
        raw = self._client.get(self._spent_key())
        return float(raw) if raw is not None else 0.0

    def count(self) -> int:
        raw = self._client.get(self._count_key())
        return int(raw) if raw is not None else 0

    def add_cost(self, cost: float) -> None:
        day = _day_stamp()
        pipe = self._client.pipeline()
        pipe.incrbyfloat(self._spent_key(day), float(cost))
        pipe.incr(self._count_key(day))
        pipe.expire(self._spent_key(day), _KEY_TTL_SECONDS)
        pipe.expire(self._count_key(day), _KEY_TTL_SECONDS)
        pipe.execute()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # pragma: no cover - best effort
            pass
