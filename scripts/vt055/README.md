# VT-055: versioned viewer-draft autosave

Phạm Đức Duy / 23001855 / SE2026-T14 / 3D-WEB-04.

Branch: [feat/vt055-viewer-draft-autosave](https://github.com/padoruqm/SE2026-T14/tree/feat/vt055-viewer-draft-autosave).
Baseline: `aab6bd79e59ee4d4065ea3c32dc422c69c8b88af`, the local `dev` snapshot.
This branch is for individual assignment review. It has not been merged or
approved by another team member. The original checkout is untouched.

## Scope and contract

The viewer automatically saves `pointSize` and `colorMode` after 300 ms of idle
editing and restores them per dataset. `GET /api/pointcloud/{dataset_id}/draft`
returns `{revision, state}`. `PUT` accepts `{expectedRevision, operationId, state}`.
Only the current revision may be advanced. Stale writes get 409 without mutation;
exact retry commands return their original acknowledgement without another write.
SQLite transactions enforce this across independent connections, not just UI state.
"Newer" means server-committed revision; no client timestamps are trusted.

Storage/network errors retain local edits and the pending operation for retry.
Conflicts stop automatic saves; **Load latest saved draft** explicitly discards
the local unsaved settings and reloads the current server state. The UI does not
claim saved while a newer local edit is pending or when the acknowledgement differs.

This is a single-host, trusted-local MVP slice. It does not add authentication,
full project history, unsent page-close recovery, arbitrary point-cloud processing,
retention/compaction for the operation ledger, or a production deployment guarantee.

## Install and run (from repository root)

Python >=3.11; Node matching frontend/package.json. Test versions used are pinned
in this directory; frontend dependencies use the repository's package-lock.json.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[dev]' -r scripts/vt055/requirements.txt
cd frontend
npm ci
npm run api:generate
npm run lint
npm run typecheck
npm test
VITE_API_BASE_URL='' npm run build
cd ..
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
```

Focused API and frontend contracts:

```bash
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p test_viewer_drafts.py -v
cd frontend
npm test -- src/features/viewer/__tests__/useViewerDraft.spec.ts src/features/viewer/__tests__/viewerDraftApi.spec.ts
cd ..
```

The implementation uses stdlib sqlite3; no production package was added. Draft
database/WAL files live under APP_STORAGE_ROOT and are excluded from Git.

## Reproduce mutation, coverage, browser and load evidence

Run after committing the implementation (the mutation tool checks out HEAD):

```bash
.venv/bin/python scripts/vt055/run_quality.py
.venv/bin/python scripts/vt055/mutate_guard.py
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/vt055/run_runtime.py
```

`run_runtime.py` builds no assets by itself: run the production frontend build
above first. It creates a fresh temporary data directory, generates tiny LAS
fixtures with the existing sample generator, starts the real app on a loopback
port, runs browser/API/SQLite and 60-task TCP tests, and stops the server.
Use `VT055_CHROMIUM_EXECUTABLE=/path/to/chrome` only to select an installed browser;
the observed browser version is recorded in evidence/e2e.json.

`mutate_guard.py` creates a temporary Git branch/worktree and deliberate-bug
commit, removes the revision guard and requires T03/T11 to fail. It removes the
worktree and leaves the delivery branch/source untouched. It does not push or
merge the mutation branch. Exit 0 means the mutation was detected as intended.

## Evidence and confidence limits

- PLAN.md was committed before tests/code; red-api.txt preserves the missing
  endpoint failures, not an invented red result.
- REVIEW.md records the post-test AI review, a reproduced valid observation and
  an insufficiently evidenced performance claim.
- evidence/ contains baseline/green logs, review reproduction, coverage, mutation,
  concurrency repeats, actual browser E2E and actual loopback HTTP latency.
- Backend coverage is scoped to the two new draft modules; 100% there is not
  whole-system/risk coverage. Converter integration skips are explicitly retained.
- E2E verifies built Vue -> real HTTP -> SQLite; Potree rendering is outside this
  slice. The local performance result concerns small JSON, not WAN/large LAS jobs.
- A remote check found newer dev commits `78c264b` in jobs/processing/tests;
  these do not touch autosave files. This assignment retains its stated baseline
  instead of mixing unrelated team changes into the evidence.

The decision table and acceptance criteria in PLAN.md are the oracle. Assertions
check persisted state/revision, conflict/error outcomes and visible UI behavior.
Generated clients are regenerated from OpenAPI, never edited by hand.
