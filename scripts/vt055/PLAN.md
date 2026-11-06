# VT-055: spec and AI-assisted plan, before implementation

Author: Phạm Đức Duy, 23001855. Date: 2026-11-06.
Baseline: aab6bd79e59ee4d4065ea3c32dc422c69c8b88af (local dev snapshot).
Branch: feat/vt055-viewer-draft-autosave. No merge authorization.

## Problem and scope

The existing viewer keeps pointSize and colorMode in component memory. A reload
loses them. Autosave should preserve these two settings per existing dataset,
while a delayed or retried save must not replace an already accepted newer draft.
This is a small working viewer-settings slice, not full project/mesh/history save.

## Acceptance criteria (the test oracle, not inferred from implementation)

- AC1: after the initial load, a valid settings edit is automatically saved after
  300 ms of inactivity and restored on reload, including a new application instance.
- AC2: a save may advance revision r to r+1 only if expectedRevision equals r.
  A stale command receives 409 and must not change the persisted state/revision.
  "Newer" means a server-committed revision, not a client timestamp.
- AC3: retrying the same operationId with exactly the same normalized command
  returns its original acknowledgement without a second write/revision increment;
  reusing that ID with a different command receives 409. Later saved state is not
  rolled back by replaying an older acknowledgement.
- AC4: invalid input and unknown datasets are rejected; a storage failure must not
  acknowledge success or leave a partial committed update. The UI retains local
  edits, shows an error/conflict and offers explicit retry or load-latest.
- AC5: overlapping edits save only the newest queued settings after the current
  request completes. Stale load/save responses from a previous dataset cannot
  alter the active dataset. Conflict does not trigger blind automatic overwrite.

Constraints: preserve existing upload/view/convert behavior; no new production
dependency if stdlib suffices; use real storage transactions for the concurrency
contract; measure 60 concurrent API saves against p95 <= 2.0 s. The prototype is
single-host local MVP, inheriting its lack of authentication. No browser-close
delivery, cross-machine DB, full 3D-render E2E or production-scale claim is made.

Invariant: each accepted save advances the server revision exactly once, and a
request based on an older revision never changes the current persisted draft.

## Actual AI plan candidates and repository review

The coding agent considered (1) reusing JobStore for drafts and (2) ordering by
client-provided timestamps. Both candidates were rejected before code:

1. backend/app/jobs/store.py keeps jobs in memory; restart loses that state.
   Draft persistence must therefore use its own durable adapter, not JobStore.
2. ViewerPage.vue currently has only two refs and there is no revision contract.
   Timestamps do not make read/check/write atomic or compare clocks reliably.
   Use a server revision and transactionally enforced compare-and-swap instead.

## Implementation sequence and expected files

1. Commit this plan. Run existing backend/frontend baseline suites.
2. Write public API tests from AC1-AC5 and the decision table before implementing
   the endpoint. Record their 404 failures and commit the red tests.
3. Add backend/app/storage/viewer_drafts.py using sqlite3 transactions, operation
   replay and compare-and-swap; backend/app/api/viewer_drafts.py for GET/PUT;
   wire the router/store in backend/app/main.py. Update openapi/openapi.yaml.
4. Add viewerDraftApi.ts and useViewerDraft.ts plus focused frontend tests;
   integrate them into ViewerPage.vue. Do not change Potree/measurement internals.
5. Run baseline + new suites, typecheck/lint/build and real local HTTP/browser
   checks. Review diff after tests. Capture one supported and one insufficiently
   supported AI review observation and the resulting decision.
6. Remove only the revision guard on a temporary mutation branch/commit; require
   a public outcome test to detect it. Keep the mutation out of the delivery branch.
7. Run line/branch coverage, deterministic time/order checks, and 60-task load
   experiments. Publish only the feature branch, with scripts/vt055/README.md,
   executable tests and evidence. Produce the Vietnamese assignment PDF.

Expected extra files: backend/tests/test_viewer_drafts.py; frontend viewer tests;
scripts/vt055/{README.md,e2e_autosave.py,load_autosave.py,mutate_guard.py}; evidence
text/JSON. SQLite is standard library; coverage and browser automation are test-only.

## Test design decision table

Rules are ordered; '-' means not applicable after the earlier condition.

| Rule | Valid payload | Existing dataset | Known op | Same command | Base == current | Storage works | Expected |
|---|---|---|---|---|---|---|---|
| R1 | no | - | - | - | - | - | 422; no write |
| R2 | yes | no | - | - | - | - | 404; no write |
| R3 | yes | yes | yes | yes | - | yes | 200 original ack; current unchanged |
| R4 | yes | yes | yes | no | - | yes | 409; no write |
| R5 | yes | yes | no | - | no | yes | 409; no write |
| R6 | yes | yes | no | - | yes | yes | 200; revision +1; exact settings |
| R7 | yes | yes | no | - | yes | no | 503; rollback; no saved status |

Data: point sizes 1 and 5, valid 2.5, invalid 0.5/5.5/1.25/non-finite;
rgb/elevation/intensity vs unknown; revision 0/1/2 and stale/future bases;
fixed operation IDs; independent temporary directories/databases. Concurrency uses
barriers rather than sleeps; UI debounce/order uses fake timers/deferred promises.
