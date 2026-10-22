from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import yaml

from app.core import errors
from app.core.config import Settings
from app.main import create_app

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi" / "openapi.yaml"


def _properties(schema: dict) -> set[str]:
    return set(schema["properties"])


class OpenApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
        cls.temporary_directory = tempfile.TemporaryDirectory()
        settings = Settings(
            storage_root=Path(cls.temporary_directory.name), max_upload_bytes=1024
        )
        app = create_app(settings)
        cls.implemented = app.openapi()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_upload_route_is_documented_in_the_contract(self) -> None:
        self.assertIn("/api/upload", self.spec["paths"])
        self.assertIn("/api/upload", self.implemented["paths"])

    def test_upload_declares_the_same_success_and_error_statuses(self) -> None:
        contract = self.spec["paths"]["/api/upload"]["post"]["responses"]
        implemented = self.implemented["paths"]["/api/upload"]["post"]["responses"]

        for status in ("201", "413", "415", "422"):
            self.assertIn(status, contract)
            self.assertIn(status, implemented)

    def test_point_cloud_response_has_the_contract_fields(self) -> None:
        contract = self.spec["components"]["schemas"]["PointCloud"]
        implemented = self.implemented["components"]["schemas"]["PointCloudResponse"]

        self.assertEqual(_properties(contract), _properties(implemented))
        contract_metadata = self.spec["components"]["schemas"]["PointCloudMetadata"]
        implemented_metadata = self.implemented["components"]["schemas"][
            "PointCloudMetadata"
        ]
        self.assertEqual(_properties(contract_metadata), _properties(implemented_metadata))
        self.assertEqual(
            _properties(self.spec["components"]["schemas"]["Bounds"]),
            _properties(self.implemented["components"]["schemas"]["Bounds"]),
        )

    def test_error_envelope_matches_the_contract(self) -> None:
        contract = self.spec["components"]["schemas"]["ErrorResponse"]["properties"]
        implemented = self.implemented["components"]["schemas"]

        self.assertEqual({"error"}, set(contract))
        self.assertEqual(
            _properties(contract["error"]), _properties(implemented["ErrorBody"])
        )

    def test_every_backend_error_code_is_in_the_contract(self) -> None:
        documented = set(self.spec["components"]["schemas"]["ErrorCode"]["enum"])
        raised = {
            cls.code
            for _, cls in inspect.getmembers(errors, inspect.isclass)
            if issubclass(cls, errors.AppError)
        }
        raised |= set(errors._HTTP_STATUS_CODES.values())
        raised |= {"VALIDATION_ERROR"}

        self.assertLessEqual(raised, documented)
