"""Durable, single-host viewer drafts with transactional revision checks."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class DraftConflict(ValueError):
    pass


class ViewerDraftStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS viewer_drafts (
                    dataset_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS draft_operations (
                    dataset_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    PRIMARY KEY (dataset_id, operation_id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=1.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _current(connection: sqlite3.Connection, dataset_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT revision, state_json FROM viewer_drafts WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        if row is None:
            return {"revision": 0, "state": {"pointSize": 1.0, "colorMode": "rgb"}}
        return {"revision": row["revision"], "state": json.loads(row["state_json"])}

    def load(self, dataset_id: str) -> dict[str, Any]:
        connection = self._connect()
        try:
            return self._current(connection, dataset_id)
        finally:
            connection.close()

    def save(
        self, dataset_id: str, expected_revision: int, operation_id: str, state: dict[str, Any]
    ) -> dict[str, Any]:
        command = json.dumps(
            {"expectedRevision": expected_revision, "state": state}, sort_keys=True
        )
        connection = self._connect()
        try:
            # Both the replay lookup and revision check share the write transaction.
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT command_json, response_json FROM draft_operations "
                "WHERE dataset_id = ? AND operation_id = ?",
                (dataset_id, operation_id),
            ).fetchone()
            if previous is not None:
                if previous["command_json"] != command:
                    raise DraftConflict("This operation ID was used for another draft command")
                result = json.loads(previous["response_json"])
                connection.commit()
                return result

            current = self._current(connection, dataset_id)
            if current["revision"] != expected_revision:  # VT055_CONCURRENCY_GUARD
                raise DraftConflict("A newer draft exists; load it before saving again")

            result = {"revision": current["revision"] + 1, "state": state}
            connection.execute(
                "INSERT INTO viewer_drafts(dataset_id, revision, state_json) VALUES (?, ?, ?) "
                "ON CONFLICT(dataset_id) DO UPDATE SET "
                "revision = excluded.revision, state_json = excluded.state_json",
                (dataset_id, result["revision"], json.dumps(state, sort_keys=True)),
            )
            connection.execute(
                "INSERT INTO draft_operations VALUES (?, ?, ?, ?)",
                (dataset_id, operation_id, command, json.dumps(result, sort_keys=True)),
            )
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
