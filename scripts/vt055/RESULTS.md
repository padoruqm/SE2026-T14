# VT-055 observed results (2026-11-06)

## Provenance

- Repository baseline: aab6bd79e59ee4d4065ea3c32dc422c69c8b88af.
- Spec/plan before implementation: 82f543a.
- Requirement tests and genuine red evidence: b875fe8.
- Implementation and regression tests: 98af6b6ec4c73440b55be82f9971614f049bfca3.
- Temporary mutation commit: b70247d2b8538341ccf071c105b3d1351fce41e9.
  It is not an ancestor of the delivery branch and was not pushed.

## Actual results

| Experiment | Observation | Evidence |
|---|---|---|
| Existing backend baseline | 87 collected; 85 pass, 2 converter-binary tests skipped | baseline-backend.txt |
| Existing frontend baseline | 77 pass / 11 files | baseline-frontend.txt |
| Test first | 14 draft API tests; 25 failing assertions/subtests because the endpoint was absent; missing-dataset case already passed | red-api.txt |
| Final backend regression | 102 collected; 100 pass, same 2 skips | green-backend.txt |
| Final frontend regression | 93 pass / 13 files | green-frontend.txt |
| Post-test review reproduction | Mismatched ack was incorrectly reported saved; T23 initially failed, then passed after the matching guard | review-reproduction.txt and T23 |
| Required mutation | Removing only revision guard makes T03/T11/T13 fail; 15 tests, 3 failures; delivery source unchanged | mutation.json / mutation.txt |
| Coverage (only two new backend modules) | 97/97 statements, 10/10 branches covered | coverage.json / coverage.txt |
| Contention flakiness | T11 passes 10/10 repeated runs with fresh databases and a barrier | flaky-concurrency.json |
| Real Chromium E2E | reload, lost acknowledgement/exact retry, two tabs, local conflict state, explicit load-latest pass | e2e.json |
| 60 independent concurrent saves, 3 rounds | 180/180 expected successes; p95 192.402 ms | load.json |
| 60 concurrent different operations on same base | 1 saved, 59 expected conflicts; p95 191.547 ms | load.json |
| 60 concurrent exact retries | 60 acknowledgements, one revision advance; p95 183.374 ms | load.json |

The p95 target (2000 ms) was met for these observed local JSON workloads, not
proven for WAN, other disks/hosts or large point-cloud tasks. Percentile uses
nearest rank ceil(.95*N); preceding GET revision reads warm the connections.
The performance run took place on the development machine with no isolated
hardware guarantee. E2E excludes Potree binaries/rendering, not the draft API.

Static/build gates passed: ESLint, Oxlint, Redocly OpenAPI lint, vue-tsc --build,
Vite production build, Python compileall, repository-layout validation and
git diff --check. The sandbox initially could not write a symlinked TypeScript
cache; it was replaced with a local cache directory before the successful check.

## Risk traceability

| Requirement/risk | Cases | Executable file | Implementation commit | Outcome |
|---|---|---|---|---|
| AC1 autosave/restore | T01,T02,T15,T18; browser | backend/tests/test_viewer_drafts.py; frontend/src/features/viewer/__tests__/useViewerDraft.spec.ts; scripts/vt055/e2e_autosave.py | 98af6b6 | pass |
| AC2 newer draft wins | T03,T11,T13,T20; contention load | same API/UI tests; scripts/vt055/load_autosave.py | 98af6b6 | pass; required mutation killed |
| AC3 exact retry | T04,T05,T12,T17; lost-ack browser; retry load | same tests and runtime scripts | 98af6b6 | pass, including replay after restart |
| AC4 failure/no false ack | T06-T10,T22,T23,T25 | same API/UI tests | 98af6b6 | pass; T23 reproduced review defect before fix |
| AC5 overlapping edit/route | T16,T19-T21,T24 | frontend/src/features/viewer/__tests__/useViewerDraft.spec.ts | 98af6b6 | pass |

No CI success, team approval or merge is claimed. Review of the individual
branch and broader validation remain separate from these observed local results.
