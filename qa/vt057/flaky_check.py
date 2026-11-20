"""VT-057 flaky-test check: order/shared state and environment leaks.

Runs the VT-057 tests many times in a shuffled order and checks that
no APP_* variable leaks into os.environ after the run.

Usage (from the repository root):
    PYTHONPATH=backend:backend/tests python3 qa/vt057/flaky_check.py
"""
from __future__ import annotations

import os
import random
import unittest

ROUNDS = 30
MODULES = ("test_runtime_config_api", "test_local_storage")


def _flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(_flatten(item))
        else:
            tests.append(item)
    return tests


def main() -> int:
    environment_before = {k: v for k, v in os.environ.items() if k.startswith("APP_")}
    failures = 0
    total = 0
    for seed in range(ROUNDS):
        tests = _flatten(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
        random.Random(seed).shuffle(tests)
        result = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(
            unittest.TestSuite(tests)
        )
        total += result.testsRun
        bad = len(result.failures) + len(result.errors)
        failures += bad
        if bad:
            print(f"seed={seed}: {bad} failing test(s)")
    environment_after = {k: v for k, v in os.environ.items() if k.startswith("APP_")}
    leaked = environment_after != environment_before
    print(f"rounds={ROUNDS} tests_run={total} failures={failures} env_leak={leaked}")
    return 1 if failures or leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
