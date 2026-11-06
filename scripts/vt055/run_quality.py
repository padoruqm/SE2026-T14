"""Coverage and bounded flakiness experiments for the autosave boundary."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "scripts/vt055/evidence"


def main():
    with tempfile.TemporaryDirectory(prefix="vt055-coverage-") as temporary:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "COVERAGE_FILE": str(Path(temporary) / "data")}
        result = subprocess.run([sys.executable, "-m", "coverage", "run", "--branch", "--source=backend/app",
                                 "-m", "unittest", "discover", "-s", "backend/tests", "-v"],
                                cwd=ROOT, env=env, capture_output=True, text=True)
        (EVIDENCE / "green-backend.txt").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, "Backend regression suite failed"
        subprocess.run([sys.executable, "-m", "coverage", "json", "--include=*/viewer_drafts.py",
                        "-o", str(EVIDENCE / "coverage.json")], cwd=ROOT, env=env, check=True)
        report = subprocess.check_output([sys.executable, "-m", "coverage", "report", "-m", "--include=*/viewer_drafts.py"],
                                         cwd=ROOT, env=env, text=True)
        (EVIDENCE / "coverage.txt").write_text(report)
        print(report)
        # Repeat the actual contention contract, not a sleep-based simulation.
        repeats = []
        for index in range(10):
            run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "backend/tests",
                                  "-p", "test_viewer_drafts.py", "-k", "T11"],
                                 cwd=ROOT, env=env, capture_output=True, text=True)
            repeats.append({"round": index + 1, "exit": run.returncode})
            assert run.returncode == 0, run.stderr
        (EVIDENCE / "flaky-concurrency.json").write_text(json.dumps({
            "repeats": repeats, "isolation": "new TemporaryDirectory/SQLite database per test",
            "coordination": "threading.Barrier; no scheduling sleep or assumed winner",
            "conclusion": "10 observed passes reduce, but do not eliminate, concurrency flakiness risk",
        }, indent=2) + "\n")
        print("Contention test: 10/10 repeats passed")


if __name__ == "__main__":
    main()
