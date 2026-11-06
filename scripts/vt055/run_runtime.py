"""Start an isolated local app, execute browser/load tests, and stop it."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "scripts/vt055/evidence"


def main():
    EVIDENCE.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vt055-runtime-") as temporary:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "VT055_DATA_ROOT": temporary}
        with (EVIDENCE / "runtime-server.txt").open("w") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "scripts.vt055.runtime_app:app",
                                       "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Server stopped; inspect runtime-server.txt")
                    try:
                        if httpx.get(base + "/health", timeout=0.5).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                else:
                    raise RuntimeError("Server failed to become ready")
                for script, output in [("e2e_autosave.py", "e2e.json"), ("load_autosave.py", "load.json")]:
                    subprocess.run([sys.executable, str(ROOT / "scripts/vt055" / script), "--base-url", base,
                                    "--output", str(EVIDENCE / output)], cwd=ROOT, check=True)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
