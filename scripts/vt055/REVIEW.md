# AI-assisted patch review after test execution

Review context: the implementation diff, green backend (101 tests, 2 skipped),
green frontend (91 tests), PLAN.md/AC1-AC5, and the recorded red API evidence.
This is a coding-agent self-review, not approval by another team member.

Prompt/context: review the autosave patch against VT-055, especially newer-data
protection, idempotency, weak AI-generated tests, and confidence beyond test pass.

## Supported observation: accepted and reproduced

The client validated the acknowledgement's schema but set `saved` without checking
that its revision/state matched the pending command. A schema-valid response for
another edit could falsely acknowledge the local edit. Evidence: the original
useViewerDraft save() diff; new T23 in useViewerDraft.spec.ts initially failed with
`Expected: error / Received: saved` (evidence/review-reproduction.txt).

Action: compare revision to expectedRevision+1 and both submitted settings before
clearing the pending operation. Keep the local edit and retry operation on failure.
T23 now guards the public saved/error outcome, not helper calls or private storage.

## Insufficiently evidenced observation: not accepted as a conclusion

"SQLite's single-writer model means this patch cannot meet p95 <= 2 seconds at
60 concurrent tasks." The diff alone supplies no latency measurement. Treat it as
a hypothesis for the real loopback HTTP experiment, not grounds to change DB or
claim failure. The workload, p95 and limits are recorded in evidence/load.json.
Observed result: 180 successful independent saves at concurrency 60 had p95
192.402 ms; the two contention/retry workloads also stayed below 2000 ms. This
rejects the categorical claim for this run, not every possible workload or host.

## Existing test design corrected during verification

router.spec.ts assumed the metadata request was the first fetch and cast its input
to Request. Adding draft restore made that assumption fail without violating the
metadata requirement. The revised test checks that the required metadata/draft
paths are present, independent of fetch order or Request/string transport form.
See evidence/initial-ui-regression.txt. This is a test-quality correction, not an
application change to satisfy an irrelevant call-order expectation.

Residual risks: single-host SQLite, no authentication inherited from the MVP,
unsent edits on page close, indefinite operation-ledger growth, schema migration,
and network/filesystem behavior outside the measured local environment. These
are not declared solved by the patch or by its tests.
