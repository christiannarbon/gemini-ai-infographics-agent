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


def _estimated_progress_steps(
    elapsed_seconds: int, milestones: list[tuple[int, str]]
) -> list[ProgressStep]:
    steps: list[ProgressStep] = []
    for index, (starts_at, label) in enumerate(milestones):
        next_starts_at = (
            milestones[index + 1][0] if index + 1 < len(milestones) else None
        )
        if elapsed_seconds < starts_at:
            status = "pending"
        elif next_starts_at is not None and elapsed_seconds >= next_starts_at:
            status = "done"
        else:
            status = "running"
        detail = "Estimated step. The actual result will be reflected after Agent Runtime completes."
        steps.append(ProgressStep(label, status, detail))
    return steps


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

    @property
    def elapsed_seconds(self) -> int:
        return max(
            0, int((datetime.now(timezone.utc) - self.started_at).total_seconds())
        )

    @property
    def wait_hint(self) -> str:
        if self.kind == "infographics":
            return "Image generation may take 1 to 3 minutes. The screen will automatically refresh."
        return "Article retrieval and summarization may take 30 to 90 seconds. The screen will automatically refresh."

    @property
    def slow_after_seconds(self) -> int:
        if self.kind == "infographics":
            return 240
        return 120

    @property
    def is_slow(self) -> bool:
        return (
            self.status == "running" and self.elapsed_seconds >= self.slow_after_seconds
        )

    @property
    def slow_message(self) -> str:
        if self.kind == "infographics":
            return "Image generation is taking longer than usual. If this continues for a few minutes, check the Agent Runtime logs and Gemini image model quota."
        return "Summarization is taking longer than usual. If this continues for a few minutes, check if the URL content can be retrieved and check the Agent Runtime logs."

    @property
    def show_estimated_progress(self) -> bool:
        return self.status == "running" and len(self.progress) <= 1

    @property
    def estimated_progress(self) -> list[ProgressStep]:
        if not self.show_estimated_progress:
            return []
        if self.kind == "infographics":
            milestones = [
                (0, "Sending summary to Agent Runtime"),
                (10, "Agent deciding style and layout plan"),
                (30, "Generating image with Gemini"),
                (80, "Saving artifacts to Cloud Storage"),
                (105, "Preparing signed URL and returning response"),
            ]
        else:
            milestones = [
                (0, "Sending summarization workflow to Agent Runtime"),
                (12, "Retrieving article body"),
                (35, "Generating 3-line summary and key points"),
                (60, "Verifying JSON contract and returning response"),
            ]
        return _estimated_progress_steps(self.elapsed_seconds, milestones)


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
