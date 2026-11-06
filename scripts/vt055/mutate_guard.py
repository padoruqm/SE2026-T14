"""Remove the concurrency guard only in a temporary worktree/commit; require kill."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "scripts/vt055/evidence"
RELATIVE = "backend/app/storage/viewer_drafts.py"
GUARD = '''            if current["revision"] != expected_revision:  # VT055_CONCURRENCY_GUARD
                raise DraftConflict("A newer draft exists; load it before saving again")
'''


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def main():
    original_hash = hashlib.sha256((ROOT / RELATIVE).read_bytes()).hexdigest()
    baseline = git("rev-parse", "HEAD")
    branch = f"test/vt055-remove-guard-{baseline[:7]}-{uuid4().hex[:6]}"
    with tempfile.TemporaryDirectory(prefix="vt055-mutation-") as directory:
        worktree = Path(directory) / "repo"
        git("worktree", "add", "--detach", str(worktree), baseline)
        try:
            git("switch", "-c", branch, cwd=worktree)
            file = worktree / RELATIVE
            source = file.read_text()
            assert source.count(GUARD) == 1, "Mutation target changed; review this script"
            file.write_text(source.replace(GUARD, "            # VT055 deliberate bug: guard removed\n"))
            git("add", RELATIVE, cwd=worktree)
            git("commit", "-m", "test(storage): deliberately remove revision guard for mutation", cwd=worktree)
            mutation = git("rev-parse", "HEAD", cwd=worktree)
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "backend/tests", "-p", "test_viewer_drafts.py", "-v"],
                cwd=worktree, env={**os.environ, "PYTHONPATH": str(worktree / "backend")},
                capture_output=True, text=True,
            )
            output = result.stdout + result.stderr
            (EVIDENCE / "mutation.txt").write_text(output)
            killed = result.returncode != 0 and "FAIL: test_T03" in output and "FAIL: test_T11" in output
            record = {"baseline": baseline, "temporary_branch": branch, "mutation_commit": mutation,
                      "mutation": "removed revision compare-and-swap guard; kept replay lookup",
                      "test_exit": result.returncode, "killed_by_T03_and_T11": killed,
                      "submission_source_unchanged": hashlib.sha256((ROOT / RELATIVE).read_bytes()).hexdigest() == original_hash}
            (EVIDENCE / "mutation.json").write_text(json.dumps(record, indent=2) + "\n")
            print(json.dumps(record, indent=2))
            assert killed and record["submission_source_unchanged"], "Mutation did not produce the expected invariant failures"
        finally:
            git("worktree", "remove", "--force", str(worktree))


if __name__ == "__main__":
    main()
