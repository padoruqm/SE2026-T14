"""VT-057: change the upload limit at runtime without editing code.

Each test checks the business outcome (the limit actually used by uploads),
not only the HTTP status code.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from las_fixtures import build_las

ADMIN_TOKEN = "vt057-admin-secret"
START_LIMIT = 4096
LIMIT_MIN = 1
LIMIT_MAX = 1024 * 1024 * 1024  # 1 GiB
LAS_BYTES = build_las()  # 227 bytes, a valid LAS file


class RuntimeConfigApiTest(unittest.TestCase):
    def _client(self, admin_token: str | None = ADMIN_TOKEN) -> TestClient:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        environment = {
            "APP_STORAGE_ROOT": temporary_directory.name,
            "APP_MAX_UPLOAD_BYTES": str(START_LIMIT),
        }
        if admin_token is not None:
            environment["APP_ADMIN_TOKEN"] = admin_token
        with mock.patch.dict(os.environ, environment, clear=False):
            if admin_token is None:
                os.environ.pop("APP_ADMIN_TOKEN", None)
            settings = Settings.from_environment()
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        self.addCleanup(client.close)
        return client

    def _limit(self, client: TestClient) -> int:
        response = client.get("/api/config")
        self.assertEqual(200, response.status_code)
        return response.json()["maxUploadBytes"]

    def _set_limit(self, client: TestClient, value, token: str | None = ADMIN_TOKEN):
        headers = {} if token is None else {"X-Admin-Token": token}
        return client.put(
            "/api/admin/config", json={"maxUploadBytes": value}, headers=headers
        )

    def _upload(self, client: TestClient, content: bytes):
        return client.post("/api/upload", files={"file": ("a.las", content)})

    # TC01
    def test_config_exposes_the_limit_from_the_environment(self) -> None:
        client = self._client()

        self.assertEqual(START_LIMIT, self._limit(client))

    # TC02
    def test_admin_change_is_applied_to_the_next_upload(self) -> None:
        client = self._client()
        self.assertEqual(201, self._upload(client, LAS_BYTES + b"0" * 100).status_code)

        response = self._set_limit(client, len(LAS_BYTES))

        self.assertEqual(200, response.status_code)
        self.assertEqual(len(LAS_BYTES), response.json()["maxUploadBytes"])
        self.assertEqual(len(LAS_BYTES), self._limit(client))
        # Business outcome: the same file that passed before is now rejected.
        rejected = self._upload(client, LAS_BYTES + b"0" * 100)
        self.assertEqual(413, rejected.status_code)
        self.assertEqual("FILE_TOO_LARGE", rejected.json()["error"]["code"])

    # TC03 - boundary of the upload size around the new limit N
    def test_upload_boundary_around_the_new_limit(self) -> None:
        client = self._client()
        limit = len(LAS_BYTES) + 1
        self.assertEqual(200, self._set_limit(client, limit).status_code)

        cases = (
            (limit - 1, 201),  # N-1
            (limit, 201),  # N
            (limit + 1, 413),  # N+1
        )
        for size, expected in cases:
            with self.subTest(size=size):
                content = LAS_BYTES + b"0" * (size - len(LAS_BYTES))
                self.assertEqual(size, len(content))
                self.assertEqual(expected, self._upload(client, content).status_code)

    # TC04 + TC05 - boundary of the accepted config value
    def test_limit_value_boundaries(self) -> None:
        cases = (
            (LIMIT_MIN - 1, 422),  # 0
            (LIMIT_MIN, 200),  # 1
            (LIMIT_MIN + 1, 200),  # 2
            (LIMIT_MAX - 1, 200),
            (LIMIT_MAX, 200),
            (LIMIT_MAX + 1, 422),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                client = self._client()
                response = self._set_limit(client, value)
                self.assertEqual(expected, response.status_code)
                expected_limit = value if expected == 200 else START_LIMIT
                self.assertEqual(expected_limit, self._limit(client))

    # TC06 - negative
    def test_missing_token_is_rejected_and_limit_is_unchanged(self) -> None:
        client = self._client()

        response = self._set_limit(client, LIMIT_MIN, token=None)

        self.assertEqual(401, response.status_code)
        self.assertEqual("UNAUTHORIZED", response.json()["error"]["code"])
        self.assertEqual(START_LIMIT, self._limit(client))
        self.assertEqual(201, self._upload(client, LAS_BYTES).status_code)

    # TC07 - negative
    def test_wrong_token_is_rejected_and_limit_is_unchanged(self) -> None:
        client = self._client()

        response = self._set_limit(client, LIMIT_MIN, token="wrong-token")

        self.assertEqual(403, response.status_code)
        self.assertEqual("FORBIDDEN", response.json()["error"]["code"])
        self.assertEqual(START_LIMIT, self._limit(client))
        self.assertEqual(201, self._upload(client, LAS_BYTES).status_code)

    # TC08 - negative: no admin token configured means the endpoint is closed
    def test_change_is_denied_when_no_admin_token_is_configured(self) -> None:
        client = self._client(admin_token=None)

        for token in ("", "anything"):
            with self.subTest(token=token):
                response = self._set_limit(client, LIMIT_MIN, token=token)
                self.assertIn(response.status_code, (401, 403))
                self.assertEqual(START_LIMIT, self._limit(client))

    # TC09 - failure path: a rejected update must not change upload behaviour
    def test_rejected_update_keeps_the_old_limit_for_uploads(self) -> None:
        client = self._client()

        for invalid in (0, -5, LIMIT_MAX + 1, "big"):
            with self.subTest(value=invalid):
                self.assertEqual(422, self._set_limit(client, invalid).status_code)

        self.assertEqual(START_LIMIT, self._limit(client))
        content = LAS_BYTES + b"0" * (START_LIMIT - len(LAS_BYTES))
        self.assertEqual(201, self._upload(client, content).status_code)
        self.assertEqual(413, self._upload(client, content + b"0").status_code)


class AdminTokenSettingsTest(unittest.TestCase):
    # TC10
    def test_admin_token_is_read_from_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {"APP_ADMIN_TOKEN": "abc"}):
            self.assertEqual("abc", Settings.from_environment().admin_token)
        with mock.patch.dict(os.environ, {"APP_ADMIN_TOKEN": ""}):
            self.assertIsNone(Settings.from_environment().admin_token)


if __name__ == "__main__":
    unittest.main()
