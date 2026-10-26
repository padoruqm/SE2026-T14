from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

ACTIVE_STATES = frozenset({"queued", "running"})


@dataclass(frozen=True, slots=True)
class JobError:
    code: str
    message: str


@dataclass(slots=True)
class Job:
    id: str
    type: str
    point_cloud_id: str
    state: str = "queued"
    progress: int | None = None
    result_id: str | None = None
    error: JobError | None = None


class JobStore:
    """In-memory job registry; jobs are lost when the process restarts."""

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
