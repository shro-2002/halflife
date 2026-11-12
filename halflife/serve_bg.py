"""Start the Half-Life API in the background (for `make demo`) and wait until it answers.

    uv run python -m halflife.serve_bg [--port 8091]
"""

import argparse
import subprocess
import sys
import time

import httpx

from halflife.config import ROOT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8091)
    port = ap.parse_args().port
    url = f"http://localhost:{port}/health"
    try:
        httpx.get(url, timeout=2).raise_for_status()
        print(f"Half-Life already running: http://localhost:{port}")
        return 0
    except httpx.HTTPError:
        pass
    log = (ROOT / ".cache" / "api.log").open("a")
    subprocess.Popen([sys.executable, "-m", "uvicorn", "halflife.api:app", "--port", str(port)],
                     cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
    for _ in range(30):
        try:
            httpx.get(url, timeout=2).raise_for_status()
            print(f"Half-Life UI: http://localhost:{port}")
            return 0
        except httpx.HTTPError:
            time.sleep(1)
    print("API did not start; see .cache/api.log", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
