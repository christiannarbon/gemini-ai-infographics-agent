from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from web.runtime import _display_error

if TYPE_CHECKING:
    from agent.models import SummaryResult
    from web.agent_client import AgentClient
    from web.services.jobs import AgentJob, JobStore
    from web.services.sessions import SessionStore

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(
        self,
        agent_client: AgentClient,
        job_store: JobStore,
        session_store: SessionStore,
    ):
        self._agent_client = agent_client
        self._job_store = job_store
        self._session_store = session_store
        self._tasks: set[asyncio.Task] = set()

    def start_summary(self, url: str) -> AgentJob:
        job = self._job_store.create(kind="summary", title="Summarizing article...")
        coro = self._run_summary_job(job.job_id, url)
        self._schedule_background_task(coro)
        return job

    def start_infographics(
        self, summary: SummaryResult, feedback: str = ""
    ) -> AgentJob:
        title = "Applying feedback..." if feedback else "Generating infographics..."
        job = self._job_store.create(
            kind="infographics", title=title, feedback=feedback
        )
        coro = self._run_infographics_job(job.job_id, summary, feedback)
        self._schedule_background_task(coro)
        return job

    def _schedule_background_task(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_summary_job(self, job_id: str, url: str) -> None:
        started = time.perf_counter()

        async def update_progress(progress: list) -> None:
            self._job_store.update(job_id, progress=progress)

        try:
            summary = await self._agent_client.summarize_url(
                url, on_progress=update_progress
            )
        except Exception as exc:
            logger.exception("Summary job failed: job_id=%s url=%s", job_id, url)
            self._job_store.update(job_id, status="failed", error=_display_error(exc))
            return

        self._session_store.set_summary(summary.session_id, summary)
        self._job_store.update(
            job_id,
            summary=summary,
            progress=summary.progress,
            status="done",
        )
        self._log_job_duration("summary", job_id, started)

    async def _run_infographics_job(
        self, job_id: str, summary: SummaryResult, feedback: str
    ) -> None:
        self._job_store.update(job_id, summary=summary)
        started = time.perf_counter()

        async def update_progress(progress: list) -> None:
            self._job_store.update(job_id, progress=progress)

        try:
            if feedback:
                infographics = await self._agent_client.regenerate_infographics(
                    summary,
                    feedback,
                    on_progress=update_progress,
                )
            else:
                infographics = await self._agent_client.generate_infographics(
                    summary,
                    on_progress=update_progress,
                )
        except Exception as exc:
            logger.exception(
                "Infographics job failed: job_id=%s session_id=%s",
                job_id,
                summary.session_id,
            )
            self._job_store.update(job_id, status="failed", error=_display_error(exc))
            return

        self._session_store.set_infographic(summary.session_id, infographics)
        self._job_store.update(
            job_id,
            infographics=infographics,
            progress=infographics.progress,
            status="done",
        )
        self._log_job_duration("infographics", job_id, started)

    def _log_job_duration(self, kind: str, job_id: str, started: float) -> None:
        logger.info(
            "job_duration kind=%s job_id=%s elapsed_seconds=%.3f",
            kind,
            job_id,
            time.perf_counter() - started,
        )
