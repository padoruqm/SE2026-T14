from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.processing import ProcessingContext, ProcessingResult
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
)
from las_fixtures import build_las

# Source point cloud: X 0-100, Y 0-50, Z 10-20 (from build_las below).
SOURCE = build_las(
    point_count=1000,
    min_xyz=(500000.0, 2000000.0, 10.0),
    max_xyz=(500100.0, 2000050.0, 20.0),
)
REGION = {
    "minX": 500010.0,
    "minY": 2000010.0,
    "minZ": 10.0,
    "maxX": 500030.0,
    "maxY": 2000040.0,
    "maxZ": 20.0,
}


class FakeCrop:
    """Writes a cropped file and the summary PdalCropProcessor writes."""

    key = "fake-crop"
    input_schema: Mapping[str, object] = {"type": "object"}

    def __init__(self, point_count: int = 120, error: Exception | None = None) -> None:
        self.point_count = point_count
        self.error = error
        self.calls: list[tuple[Path, Mapping[str, object]]] = []

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        self.calls.append((context.input_path, parameters))
        if self.error is not None:
            raise self.error
        out = context.output_directory
        out.mkdir()
        fmt = parameters["output_format"]
        b = parameters["bounds"]
        (out / f"cropped.{fmt}").write_bytes(
            build_las(
                point_count=self.point_count,
                min_xyz=(b["minX"], b["minY"], 12.0),
                max_xyz=(b["maxX"], b["maxY"], 18.0),
            )
        )
        summary = out / "metadata.json"
        summary.write_text(
            json.dumps(
                {
                    "point_count": self.point_count,
                    "bounds": {
                        "minX": b["minX"],
                        "minY": b["minY"],
                        "minZ": 12.0,
                        "maxX": b["maxX"],
                        "maxY": b["maxY"],
                        "maxZ": 18.0,
                    },
                    "crs": "EPSG:32648",
                }
            ),
            encoding="utf-8",
        )
        return ProcessingResult(out, summary)


class FakeConvert:
    """Writes Potree-like viewer files; can wait for a signal to test running jobs."""

    key = "fake-convert"
    input_schema: Mapping[str, object] = {"type": "object"}

    def __init__(self, error: Exception | None = None, hold: bool = False) -> None:
        self.error = error
        self.inputs: list[Path] = []
        self.started = threading.Event()
        self.release = threading.Event()
        if not hold:
            self.release.set()

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        self.inputs.append(context.input_path)
        self.started.set()
        if context.progress_callback is not None:
            context.progress_callback(50)
        if not self.release.wait(timeout=5):
            raise TimeoutError("test converter was not released")
        if self.error is not None:
            raise self.error
        out = context.output_directory
        out.mkdir()
        metadata = out / "metadata.json"
        metadata.write_text('{"version": "2.0"}', encoding="utf-8")
        (out / "octree.bin").write_bytes(b"octree")
        return ProcessingResult(out, metadata)


class CropJobTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name).resolve()
        self.settings = Settings(storage_root=self.root, max_upload_bytes=1024 * 1024)

    def _client(self, crop: FakeCrop | None = None, convert: FakeConvert | None = None):
        self.crop = crop or FakeCrop()
        self.convert = convert or FakeConvert()
        client = TestClient(
            create_app(self.settings, self.convert, crop_processor=self.crop),
            raise_server_exceptions=False,
        )
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def _upload(self, client: TestClient, name: str = "survey.las") -> str:
        response = client.post("/api/upload", files={"file": (name, SOURCE)})
        self.assertEqual(201, response.status_code)
        return response.json()["id"]

    def _crop(self, client: TestClient, point_cloud_id: str, **body: object):
        payload = {"bounds": REGION, **body}
        return client.post(f"/api/pointcloud/{point_cloud_id}/crop", json=payload)

    def _wait(self, client: TestClient, job_id: str) -> dict:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/job/{job_id}").json()
            if job["state"] in ("succeeded", "failed", "cancelled"):
                return job
            time.sleep(0.01)
        self.fail("job did not finish")

    def _entries(self, folder: str) -> list[str]:
        path = self.root / folder
        return sorted(p.name for p in path.iterdir()) if path.is_dir() else []

    def test_a_crop_creates_a_new_point_cloud_and_leaves_the_source_alone(self) -> None:
        client = self._client()
        source_id = self._upload(client)
        source_before = (self.root / "uploads" / f"{source_id}.las").read_bytes()

        response = self._crop(client, source_id)

        self.assertEqual(202, response.status_code)
        job = response.json()
        self.assertEqual("crop", job["type"])
        self.assertEqual("queued", job["state"])
        finished = self._wait(client, job["id"])
        self.assertEqual("succeeded", finished["state"])
        self.assertEqual(100, finished["progress"])
        result_id = finished["resultId"]
        self.assertNotEqual(source_id, result_id)

        detail = client.get(f"/api/pointcloud/{result_id}").json()
        self.assertEqual("ready", detail["status"])
        self.assertEqual(source_id, detail["sourceId"])
        self.assertEqual("survey-crop.laz", detail["filename"])
        self.assertEqual(120, detail["metadata"]["pointCount"])
        self.assertEqual(500010.0, detail["metadata"]["bounds"]["minX"])
        self.assertEqual(
            f"/api/pointcloud/{result_id}/viewer/metadata.json", detail["viewerUrl"]
        )
        self.assertEqual(200, client.get(detail["viewerUrl"]).status_code)
        self.assertEqual(f"{result_id}.laz", self.storage_file(result_id).name)

        self.assertEqual(
            source_before, (self.root / "uploads" / f"{source_id}.las").read_bytes()
        )
        self.assertEqual(
            "uploaded", client.get(f"/api/pointcloud/{source_id}").json()["status"]
        )

    def storage_file(self, dataset_id: str) -> Path:
        return next((self.root / "uploads").glob(f"{dataset_id}.*"))

    def test_passes_the_region_and_format_to_the_crop_and_converts_its_output(
        self,
    ) -> None:
        client = self._client()
        source_id = self._upload(client)

        job = self._crop(client, source_id, outputFormat="las").json()
        self._wait(client, job["id"])

        source, parameters = self.crop.calls[0]
        self.assertEqual(f"{source_id}.las", source.name)
        self.assertEqual({"bounds": REGION, "output_format": "las"}, dict(parameters))
        self.assertEqual("cropped.las", self.convert.inputs[0].name)

    def test_laz_is_the_default_output_format(self) -> None:
        client = self._client()
        source_id = self._upload(client)

        job = self._crop(client, source_id).json()
        self._wait(client, job["id"])

        self.assertEqual("laz", self.crop.calls[0][1]["output_format"])

    def test_reports_progress_while_converting_the_result(self) -> None:
        convert = FakeConvert(hold=True)
        client = self._client(convert=convert)
        source_id = self._upload(client)
        job = self._crop(client, source_id).json()

        self.assertTrue(convert.started.wait(timeout=2))
        time.sleep(0.05)
        running = client.get(f"/api/job/{job['id']}").json()
        convert.release.set()

        self.assertEqual("running", running["state"])
        self.assertGreater(running["progress"], 40)
        self.assertLess(running["progress"], 100)
        self.assertEqual("succeeded", self._wait(client, job["id"])["state"])

    def test_a_region_with_no_points_fails_with_empty_result(self) -> None:
        client = self._client(crop=FakeCrop(point_count=0))
        source_id = self._upload(client)

        finished = self._wait(client, self._crop(client, source_id).json()["id"])

        self.assertEqual("failed", finished["state"])
        self.assertEqual("EMPTY_RESULT", finished["error"]["code"])
        self.assertIsNone(finished["resultId"])
        self.assertEqual([], self.convert.inputs)

    def test_failures_report_a_code_and_leave_no_files(self) -> None:
        for name, crop, convert, code in (
            (
                "bad input",
                FakeCrop(error=ProcessingInputError("bad")),
                None,
                "INVALID_POINT_CLOUD",
            ),
            (
                "pdal crashed",
                FakeCrop(error=ProcessorExecutionError("x", 1, "/secret")),
                None,
                "INTERNAL_ERROR",
            ),
            (
                "pdal timeout",
                FakeCrop(error=ProcessorTimeoutError("slow")),
                None,
                "INTERNAL_ERROR",
            ),
            (
                "convert failed",
                None,
                FakeConvert(error=ProcessorExecutionError("x", 1, "")),
                "INTERNAL_ERROR",
            ),
            (
                "unexpected",
                FakeCrop(error=RuntimeError("/secret/path")),
                None,
                "INTERNAL_ERROR",
            ),
        ):
            with self.subTest(name=name):
                client = self._client(crop=crop, convert=convert)
                source_id = self._upload(client)
                uploads_before = self._entries("uploads")
                metadata_before = self._entries("metadata")

                finished = self._wait(
                    client, self._crop(client, source_id).json()["id"]
                )

                self.assertEqual("failed", finished["state"])
                self.assertEqual(code, finished["error"]["code"])
                self.assertNotIn("secret", json.dumps(finished))
                self.assertEqual(uploads_before, self._entries("uploads"))
                self.assertEqual(metadata_before, self._entries("metadata"))
                self.assertEqual(
                    [], [n for n in self._entries("converted") if n.startswith(".")]
                )

    def test_several_crops_of_the_same_point_cloud_are_allowed(self) -> None:
        client = self._client()
        source_id = self._upload(client)

        first = self._wait(client, self._crop(client, source_id).json()["id"])
        second = self._wait(client, self._crop(client, source_id).json()["id"])

        self.assertEqual("succeeded", second["state"])
        self.assertNotEqual(first["resultId"], second["resultId"])

    def test_a_crop_result_can_be_cropped_again(self) -> None:
        client = self._client()
        source_id = self._upload(client)
        first = self._wait(client, self._crop(client, source_id).json()["id"])

        again = self._crop(
            client,
            first["resultId"],
            bounds={
                "minX": 500015.0,
                "minY": 2000015.0,
                "minZ": 12.0,
                "maxX": 500025.0,
                "maxY": 2000035.0,
                "maxZ": 18.0,
            },
        )
        finished = self._wait(client, again.json()["id"])

        self.assertEqual("succeeded", finished["state"])
        detail = client.get(f"/api/pointcloud/{finished['resultId']}").json()
        self.assertEqual(first["resultId"], detail["sourceId"])


if __name__ == "__main__":
    unittest.main()
