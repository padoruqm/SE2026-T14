from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS = {
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
    JobState.RUNNING: frozenset(
        {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}
ACTIVE_STATES = frozenset({JobState.QUEUED, JobState.RUNNING})


@dataclass(frozen=True, slots=True)
class JobError:
    code: str
    message: str


@dataclass(slots=True)
class Job:
    id: str
    type: str
    point_cloud_id: str
    state: JobState = JobState.QUEUED
    progress: int | None = None
    result_id: str | None = None
    error: JobError | None = None

    def transition_to(
        self,
        state: JobState,
        *,
        progress: int | None = None,
        result_id: str | None = None,
        error: JobError | None = None,
    ) -> None:
        if state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Cannot transition a {self.state} job to {state}")
        if progress is not None and not 0 <= progress <= 100:
            raise ValueError("Job progress must be between 0 and 100")
        if state is JobState.SUCCEEDED and (
            progress != 100 or result_id is None or error is not None
        ):
            raise ValueError("A successful job requires a complete result")
        if state is JobState.FAILED and (error is None or result_id is not None):
            raise ValueError("A failed job requires an error and no result")
        if state in {JobState.QUEUED, JobState.RUNNING} and (
            result_id is not None or error is not None
        ):
            raise ValueError("An active job cannot have a result or error")

        self.state = state
        self.progress = progress
        self.result_id = result_id
        self.error = error


class JobStore:
    """In-memory job registry; jobs are lost when the process restarts.

    Jobs are never evicted, so the registry grows for the life of the process.
    That is acceptable for the MVP.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, job_type: str, point_cloud_id: str) -> Job:
        job = Job(id=f"job_{uuid4().hex}", type=job_type, point_cloud_id=point_cloud_id)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def has_active(self, job_type: str, point_cloud_id: str) -> bool:
        return any(
            job.type == job_type
            and job.point_cloud_id == point_cloud_id
            and job.state in ACTIVE_STATES
            for job in self._jobs.values()
        )
