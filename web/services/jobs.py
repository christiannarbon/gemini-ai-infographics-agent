from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional, TYPE_CHECKING
from uuid import uuid4

from agent.models import ProgressStep

if TYPE_CHECKING:
    from agent.models import GraphicResult, SummaryResult

JobKind = Literal["summary", "infographics"]
JobStatus = Literal["running", "done", "failed"]


@dataclass
class AgentJob:
    job_id: str
    kind: JobKind
    title: str
    status: JobStatus = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    progress: list[ProgressStep] = field(default_factory=list)
    summary: Optional[SummaryResult] = None
    infographics: Optional[GraphicResult] = None
    feedback: str = ""
    error: str = ""


class JobStore:
    def __init__(self, max_size: int = 100, ttl_seconds: float = 3600.0):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._jobs: dict[str, AgentJob] = {}

    def create(self, kind: JobKind, title: str, feedback: str = "") -> AgentJob:
        job_id = f"{kind}-{uuid4().hex}"
        job = AgentJob(job_id=job_id, kind=kind, title=title, feedback=feedback)
        self._jobs[job_id] = job
        self._evict()
        return job

    def get(self, job_id: str) -> AgentJob | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        job = self.get(job_id)
        if job:
            for k, v in fields.items():
                if not hasattr(job, k):
                    raise AttributeError(f"AgentJob does not have attribute: '{k}'")
                setattr(job, k, v)
            if "status" in fields:
                self._evict()

    def _evict(self) -> None:
        # Note: Running jobs are intentionally unbounded because they are few and short-lived in normal operation.
        # TODO(INFO-REV-UPD-1-0-T6): running jobs are not bounded; add a max-age force-fail if stuck jobs become a problem
        now = datetime.now(timezone.utc)
        terminal_jobs = []
        for job in list(self._jobs.values()):
            if job.status in ("done", "failed"):
                # Check TTL
                age = (now - job.started_at).total_seconds()
                if age > self._ttl_seconds:
                    self._jobs.pop(job.job_id, None)
                else:
                    terminal_jobs.append(job)

        # Check Max Size
        if len(terminal_jobs) > self._max_size:
            # Sort by started_at ascending (oldest first)
            terminal_jobs.sort(key=lambda j: j.started_at)
            to_evict_count = len(terminal_jobs) - self._max_size
            for i in range(to_evict_count):
                job = terminal_jobs[i]
                self._jobs.pop(job.job_id, None)

    # Dictionary interface wrapper for compatibility with tests & legacy code
    def __setitem__(self, job_id: str, job: AgentJob) -> None:
        self._jobs[job_id] = job
        self._evict()

    def pop(self, job_id: str, default: Any = None) -> AgentJob | None:
        return self._jobs.pop(job_id, default)
