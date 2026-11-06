# AI usage: actual context, output and verification

Tool: OpenAI Codex coding agent. Date: 2026-11-06. The agent read the repository,
provided VT-055 assignment and lectures 06/07, wrote the plan/test/patch, ran tools,
reviewed its diff and assembled evidence. This is disclosed agent self-review;
there is no claim that another student reviewed or approved the branch.

Actual user request: "đây là bài tiếp theo mình cần thực hiện", with the VT-055
assignment. The user supplied Lecture 06/07 after being asked. The task context
explicitly requires Spec -> Test -> AI-assisted Change -> Verify -> Review,
decision table, removing the concurrency/idempotency guard, 60 tasks and p95 2 s.

## Actual agent plan output (excerpt from this task)

"Kế hoạch ban đầu có hai phương án cần loại: dùng JobStore để giữ nháp sẽ mất
dữ liệu khi restart; dùng thời gian do client gửi để chọn bản mới nhất sẽ phụ
thuộc đồng hồ máy người dùng."

Both were rejected before code. JobStore is in-memory and ViewerPage has only
component refs at baseline. They were replaced by SQLite persistence, server
revisions and a real transaction guard. PLAN.md was committed before red tests.

## Actual review output after test execution (excerpt)

"Review sau lượt test đã phát hiện một thiếu sót thật: frontend có thể báo
'saved' khi nhận payload đúng schema nhưng không khớp với lệnh vừa gửi."

T23 reproduced this with expected error / received saved, then the patch added
an acknowledgement matching guard. The separate claim that single-writer SQLite
cannot meet p95 2 s at 60 tasks was not accepted without measurement. The local
benchmark later recorded p95 192.402 ms for 180 successful saves.

## Plausible AI code/tests that were not trusted immediately

1. Validating response shape was insufficient to acknowledge the actual edit.
   The test asserts the visible saved/error outcome against the command oracle.
2. A test that expects metadata to be the first fetch is coupled to orchestration
   order. Adding draft restore exposed it; it was changed to check required paths.
   A negative 404 test alone also passed even before this feature existed.

Passing tests were challenged with the required temporary guard mutation, which
T03/T11/T13 detect. Coverage, load and browser results retain their explicit scope.
