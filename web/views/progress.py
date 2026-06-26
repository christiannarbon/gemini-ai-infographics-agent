from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from agent.models import ProgressStep

if TYPE_CHECKING:
    from web.services.jobs import AgentJob


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


# TODO(INFO-REV-UPD-1-0-T7): JobView is a general job presenter; consider views/jobs.py
class JobView:
    def __init__(self, job: AgentJob):
        self._job = job
        # Snapshot elapsed_seconds once at construction time for consistency
        self._elapsed_seconds = max(
            0, int((datetime.now(timezone.utc) - job.started_at).total_seconds())
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == "job":
            raise AttributeError(name)
        return getattr(self._job, name)

    @property
    def elapsed_seconds(self) -> int:
        return self._elapsed_seconds

    @property
    def wait_hint(self) -> str:
        if self._job.kind == "infographics":
            return "Image generation may take 1 to 3 minutes. The screen will automatically refresh."
        return "Article retrieval and summarization may take 30 to 90 seconds. The screen will automatically refresh."

    @property
    def slow_after_seconds(self) -> int:
        if self._job.kind == "infographics":
            return 240
        return 120

    @property
    def is_slow(self) -> bool:
        return (
            self._job.status == "running"
            and self.elapsed_seconds >= self.slow_after_seconds
        )

    @property
    def slow_message(self) -> str:
        if self._job.kind == "infographics":
            return "Image generation is taking longer than usual. If this continues for a few minutes, check the Agent Runtime logs and Gemini image model quota."
        return "Summarization is taking longer than usual. If this continues for a few minutes, check if the URL content can be retrieved and check the Agent Runtime logs."

    @property
    def show_estimated_progress(self) -> bool:
        return self._job.status == "running" and len(self._job.progress) <= 1

    @property
    def estimated_progress(self) -> list[ProgressStep]:
        if not self.show_estimated_progress:
            return []
        if self._job.kind == "infographics":
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
