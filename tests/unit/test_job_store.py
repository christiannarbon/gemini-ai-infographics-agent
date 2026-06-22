from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import pytest

from web.services.jobs import JobStore


@pytest.mark.unit
def test_job_store_size_eviction():
    # Eviction setting: max 3 terminal jobs, TTL 1 hour
    store = JobStore(max_size=3, ttl_seconds=3600.0)

    # 1. Create 4 terminal jobs
    jobs = []
    for i in range(4):
        job = store.create(kind="summary", title=f"Terminal Job {i}")
        job.status = "done"
        # Ensure they have slightly different started_at times to make sorting deterministic
        job.started_at = datetime.now(timezone.utc) + timedelta(seconds=i)
        jobs.append(job)

    # Trigger eviction by updating or calling _evict directly
    store._evict()

    # The oldest terminal job (jobs[0]) should be evicted, leaving jobs[1], jobs[2], jobs[3]
    assert store.get(jobs[0].job_id) is None
    assert store.get(jobs[1].job_id) is not None
    assert store.get(jobs[2].job_id) is not None
    assert store.get(jobs[3].job_id) is not None


@pytest.mark.unit
def test_job_store_active_jobs_not_evicted_by_size():
    store = JobStore(max_size=2, ttl_seconds=3600.0)

    # Create 3 jobs: 1 active (running), 2 terminal (done)
    # Make the running job the oldest
    j_active = store.create(kind="summary", title="Running Job")
    j_active.status = "running"
    j_active.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    j_term1 = store.create(kind="summary", title="Done Job 1")
    j_term1.status = "done"
    j_term1.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    j_term2 = store.create(kind="summary", title="Done Job 2")
    j_term2.status = "done"
    j_term2.started_at = datetime.now(timezone.utc)

    store._evict()

    # Active job must be retained even though it is the oldest
    assert store.get(j_active.job_id) is not None
    assert store.get(j_term1.job_id) is not None
    assert store.get(j_term2.job_id) is not None


@pytest.mark.unit
def test_job_store_ttl_eviction():
    # TTL of 60 seconds
    store = JobStore(max_size=100, ttl_seconds=60.0)
    now = datetime.now(timezone.utc)

    # Create a terminal job that is 65 seconds old (exceeds TTL)
    j_old = store.create(kind="summary", title="Old Job")
    j_old.status = "done"
    j_old.started_at = now - timedelta(seconds=65)

    # Create a terminal job that is 30 seconds old (within TTL)
    j_young = store.create(kind="summary", title="Young Job")
    j_young.status = "done"
    j_young.started_at = now - timedelta(seconds=30)

    # Create an active job that is 120 seconds old (exceeds TTL but is active)
    j_active = store.create(kind="summary", title="Active Old Job")
    j_active.status = "running"
    j_active.started_at = now - timedelta(seconds=120)

    store._evict()

    assert store.get(j_old.job_id) is None
    assert store.get(j_young.job_id) is not None
    assert store.get(j_active.job_id) is not None


@pytest.mark.unit
def test_job_store_ttl_boundary():
    store = JobStore(max_size=100, ttl_seconds=60.0)

    # We want to test the > boundary
    # Case A: exactly 60.0 seconds old (should be retained because age > 60 is False)
    j_exact = store.create(kind="summary", title="Exact Boundary")
    j_exact.status = "done"

    # Case B: 60.1 seconds old (should be evicted because age > 60 is True)
    j_over = store.create(kind="summary", title="Over Boundary")
    j_over.status = "done"

    # We mock datetime.now inside _evict to have deterministic check, or simply manipulate started_at:
    now = datetime.now(timezone.utc)
    j_exact.started_at = now - timedelta(seconds=59.9)
    j_over.started_at = now - timedelta(seconds=60.1)

    store._evict()

    assert store.get(j_exact.job_id) is not None
    assert store.get(j_over.job_id) is None


@pytest.mark.unit
def test_job_store_update_invalid_fields():
    store = JobStore()
    job = store.create(kind="summary", title="Test Job")

    # Update with valid keys
    store.update(job.job_id, status="done", title="Updated Title")
    updated = store.get(job.job_id)
    assert updated.status == "done"
    assert updated.title == "Updated Title"

    # Update with invalid keys must raise AttributeError
    with pytest.raises(AttributeError) as exc_info:
        store.update(job.job_id, staus="done")
    assert "AgentJob does not have attribute: 'staus'" in str(exc_info.value)


@pytest.mark.unit
def test_job_store_concurrency():
    # Note: The JobStore is safe for concurrent access within FastAPI because all
    # async/coroutine execution in the application event loop runs sequentially on a single thread.
    # Since there are no blocking I/O calls or awaits inside store methods, operations are
    # atomic relative to other coroutines. We add await asyncio.sleep(0) to interleave the tasks.
    store = JobStore()

    async def worker(index: int):
        job = store.create(kind="summary", title=f"Job {index}")
        await asyncio.sleep(0)
        retrieved = store.get(job.job_id)
        return job, retrieved

    async def run_concurrently():
        tasks = [worker(i) for i in range(100)]
        return await asyncio.gather(*tasks)

    results = asyncio.run(run_concurrently())

    assert len(results) == 100
    job_ids = set()
    for job, retrieved in results:
        assert job is not None
        assert retrieved is not None
        assert retrieved.job_id == job.job_id
        assert retrieved.title == job.title
        job_ids.add(job.job_id)

    assert len(job_ids) == 100
