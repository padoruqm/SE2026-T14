from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.jobs.runner import ConvertJobRunner
from app.jobs.store import Job, JobError, JobState, JobStore
from app.storage.local import LocalDatasetStorage


class JobStateTest(unittest.TestCase):
    def _job(self) -> Job:
        return Job(id="job_test", type="convert", point_cloud_id="pc_test")

    def test_job_follows_queued_running_succeeded_transitions(self) -> None:
        job = self._job()

        job.transition_to(JobState.RUNNING)
        job.transition_to(
            JobState.SUCCEEDED,
            progress=100,
            result_id="pc_test",
        )

        self.assertEqual(JobState.SUCCEEDED, job.state)
        self.assertEqual(100, job.progress)
        self.assertEqual("pc_test", job.result_id)
        self.assertIsNone(job.error)

    def test_failed_job_requires_an_error_and_has_no_result(self) -> None:
        job = self._job()
        job.transition_to(JobState.RUNNING)

        job.transition_to(
            JobState.FAILED,
            error=JobError(code="INTERNAL_ERROR", message="Conversion failed"),
        )

        self.assertEqual(JobState.FAILED, job.state)
        self.assertIsNone(job.result_id)
        self.assertEqual("INTERNAL_ERROR", job.error.code)

    def test_job_rejects_skipped_and_reversed_transitions(self) -> None:
        job = self._job()

        with self.assertRaises(ValueError):
            job.transition_to(
                JobState.SUCCEEDED,
                progress=100,
                result_id="pc_test",
            )

        job.transition_to(JobState.RUNNING)
        with self.assertRaises(ValueError):
            job.transition_to(JobState.QUEUED)

    def test_terminal_job_cannot_transition_again(self) -> None:
        job = self._job()
        job.transition_to(
            JobState.CANCELLED,
        )

        with self.assertRaises(ValueError):
            job.transition_to(JobState.RUNNING)

    def test_job_rejects_invalid_progress_and_incomplete_success(self) -> None:
        job = self._job()
        job.transition_to(JobState.RUNNING)

        with self.assertRaises(ValueError):
            job.transition_to(JobState.SUCCEEDED, progress=99, result_id="pc_test")
        with self.assertRaises(ValueError):
            job.transition_to(JobState.RUNNING, progress=101)

    def test_job_store_detects_queued_and_running_jobs_as_active(self) -> None:
        store = JobStore()
        job = store.create("convert", "pc_test")

        self.assertTrue(store.has_active("convert", "pc_test"))
        job.transition_to(JobState.RUNNING)
        self.assertTrue(store.has_active("convert", "pc_test"))
        job.transition_to(
            JobState.SUCCEEDED,
            progress=100,
            result_id="pc_test",
        )
        self.assertFalse(store.has_active("convert", "pc_test"))

    def test_runner_rejects_nonpositive_worker_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = LocalDatasetStorage(Path(temporary_directory), 1024)

            with self.assertRaisesRegex(ValueError, "at least one"):
                ConvertJobRunner(storage, object(), JobStore(), workers=0)


if __name__ == "__main__":
    unittest.main()
