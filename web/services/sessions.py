from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.models import GraphicResult, SummaryResult


class SessionStore:
    def __init__(self, max_size: int = 100, ttl_seconds: float = 3600.0):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        # Both stores are dicts keyed by session_id, and track timestamps of updates
        self._summaries: dict[str, SummaryResult] = {}
        self._infographics: dict[str, GraphicResult] = {}
        # We track the last updated timestamp per session_id to know when to evict
        self._last_accessed: dict[str, datetime] = {}

    def get_summary(self, session_id: str) -> SummaryResult | None:
        # Note: Accessing/reading a session updates its LRU timestamp in _last_accessed,
        # keeping active sessions from being evicted. This differs from JobStore's create-time TTL.
        summary = self._summaries.get(session_id)
        if summary:
            self._last_accessed[session_id] = datetime.now(timezone.utc)
        return summary

    def set_summary(self, session_id: str, summary: SummaryResult) -> None:
        self._summaries[session_id] = summary
        self._last_accessed[session_id] = datetime.now(timezone.utc)
        self._evict()

    def remove_summary(
        self, session_id: str, default: Any = None
    ) -> SummaryResult | None:
        val = self._summaries.pop(session_id, default)
        if session_id not in self._infographics:
            self._last_accessed.pop(session_id, None)
        return val

    def get_infographic(self, session_id: str) -> GraphicResult | None:
        # Note: Accessing/reading a session updates its LRU timestamp in _last_accessed,
        # keeping active sessions from being evicted. This differs from JobStore's create-time TTL.
        info = self._infographics.get(session_id)
        if info:
            self._last_accessed[session_id] = datetime.now(timezone.utc)
        return info

    def set_infographic(self, session_id: str, info: GraphicResult) -> None:
        self._infographics[session_id] = info
        self._last_accessed[session_id] = datetime.now(timezone.utc)
        self._evict()

    def remove_infographic(
        self, session_id: str, default: Any = None
    ) -> GraphicResult | None:
        val = self._infographics.pop(session_id, default)
        if session_id not in self._summaries:
            self._last_accessed.pop(session_id, None)
        return val

    def _evict(self) -> None:
        now = datetime.now(timezone.utc)
        # 1. Evict entries exceeding TTL
        for session_id, last_time in list(self._last_accessed.items()):
            age = (now - last_time).total_seconds()
            if age > self._ttl_seconds:
                self._summaries.pop(session_id, None)
                self._infographics.pop(session_id, None)
                self._last_accessed.pop(session_id, None)

        # 2. Evict oldest entries exceeding max size
        if len(self._last_accessed) > self._max_size:
            # Sort by last accessed timestamp ascending (oldest first)
            sorted_sessions = sorted(self._last_accessed.items(), key=lambda x: x[1])
            to_evict_count = len(sorted_sessions) - self._max_size
            for i in range(to_evict_count):
                session_id = sorted_sessions[i][0]
                self._summaries.pop(session_id, None)
                self._infographics.pop(session_id, None)
                self._last_accessed.pop(session_id, None)


class SessionSummaryDictWrapper:
    def __init__(self, store: SessionStore):
        self._store = store

    def __getitem__(self, session_id: str) -> SummaryResult:
        res = self._store.get_summary(session_id)
        if res is None:
            raise KeyError(session_id)
        return res

    def __setitem__(self, session_id: str, summary: SummaryResult) -> None:
        self._store.set_summary(session_id, summary)

    def __delitem__(self, session_id: str) -> None:
        if session_id not in self._store._summaries:
            raise KeyError(session_id)
        self._store.remove_summary(session_id)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._store._summaries

    def get(self, session_id: str, default: Any = None) -> SummaryResult | None:
        res = self._store.get_summary(session_id)
        return res if res is not None else default

    def pop(self, session_id: str, default: Any = None) -> SummaryResult | None:
        return self._store.remove_summary(session_id, default)

    def values(self):
        return self._store._summaries.values()

    def keys(self):
        return self._store._summaries.keys()

    def items(self):
        return self._store._summaries.items()


class SessionInfographicsDictWrapper:
    def __init__(self, store: SessionStore):
        self._store = store

    def __getitem__(self, session_id: str) -> GraphicResult:
        res = self._store.get_infographic(session_id)
        if res is None:
            raise KeyError(session_id)
        return res

    def __setitem__(self, session_id: str, info: GraphicResult) -> None:
        self._store.set_infographic(session_id, info)

    def __delitem__(self, session_id: str) -> None:
        if session_id not in self._store._infographics:
            raise KeyError(session_id)
        self._store.remove_infographic(session_id)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._store._infographics

    def get(self, session_id: str, default: Any = None) -> GraphicResult | None:
        res = self._store.get_infographic(session_id)
        return res if res is not None else default

    def pop(self, session_id: str, default: Any = None) -> GraphicResult | None:
        return self._store.remove_infographic(session_id, default)

    def values(self):
        return self._store._infographics.values()

    def keys(self):
        return self._store._infographics.keys()

    def items(self):
        return self._store._infographics.items()
