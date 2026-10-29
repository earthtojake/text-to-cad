#!/usr/bin/env bash
# Exercise the shipped launch command, its authenticated page at /<id> and the bundled STEP renderer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

HOST="127.0.0.1"
# VIEWER_RUNTIME_DIR points the smoke test at a client bundled somewhere else
# (CADGEN_RUNTIME_CHECK_DIR-style scratch builds). CI uses the default.
RUNTIME="${VIEWER_RUNTIME_DIR:-$REPO_ROOT/packages/cadgen/src/cadgen/_runtime/viewer}"

echo "==> CAD Viewer launch smoke test (\$PYTHON -m cadgen.viewer)"

# The built client has to be IN the wheel's runtime: its absence is the exact regression
# this guards, and it surfaces as a served page that is 404 rather than as a bad server.
if [ ! -f "$RUNTIME/index.html" ]; then
  echo "FAIL: no bundled CAD Viewer client at $RUNTIME (index.html missing)" >&2
  echo "      Run scripts/bundle/bundle.sh first (test.yml bundles before this step)." >&2
  exit 1
fi
export CADGEN_VIEWER_DIST="$RUNTIME"

pick_interpreter() {
  local candidates=()
  if [ -n "${VIEWER_PYTHON:-}" ]; then
    candidates=("$VIEWER_PYTHON")
  else
    candidates=(
      "$REPO_ROOT/.venv/bin/python"
      "$REPO_ROOT/.venv/Scripts/python.exe"
      python3
      python
    )
  fi

  local candidate resolved
  FOUND_INTERPRETER=""
  for candidate in "${candidates[@]}"; do
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [ -n "$resolved" ] && [ -x "$resolved" ] || continue
    [ -n "$FOUND_INTERPRETER" ] || FOUND_INTERPRETER="$resolved"
    if "$resolved" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec("cadgen") else 1)' \
        >/dev/null 2>&1; then
      PYTHON="$resolved"
      return 0
    fi
  done
  return 1
}

if ! pick_interpreter; then
  if [ -n "${VIEWER_PYTHON:-}" ]; then
    echo "FAIL: VIEWER_PYTHON=$VIEWER_PYTHON cannot run, or cannot import cadgen." >&2
  elif [ -z "$FOUND_INTERPRETER" ]; then
    echo "FAIL: no Python interpreter found (tried the repo venv, python3, and python)." >&2
    echo "      Set VIEWER_PYTHON to the one that installed requirements-dev.txt." >&2
    exit 1
  else
    echo "FAIL: cadgen is not importable from $FOUND_INTERPRETER." >&2
  fi
  echo "      This test imports a real STEP end to end, so the launching interpreter" >&2
  echo "      needs cadgen: pip install -r requirements-dev.txt, or set VIEWER_PYTHON." >&2
  exit 1
fi
export VIEWER_RUNTIME_DIR="$RUNTIME"
"$PYTHON" - <<'PYTHON'
import json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory(prefix="cv-") as temporary:
    root = Path(temporary)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "CADGEN_ENGINE_DIR": str(root / "engine"),
           "CADGEN_STATE_DIR": str(root / "state"), "CADGEN_ENGINE_MESH": "inline",
           "CADGEN_CACHE_DIR": str(root / "no-0.7-store"), "CADGEN_PORT": str(port),
           "CADGEN_ENGINE_STANDBY": "0"}
    def launch(*options):
        result = subprocess.run([sys.executable, "-m", "cadgen.viewer", "--json", *options],
                                cwd=root, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    server = subprocess.Popen([sys.executable, "-m", "cadgen.engine", "server"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 60
        while True:
            if server.poll() is not None:
                raise AssertionError(server.stderr.read())
            state = subprocess.run([sys.executable, "-m", "cadgen.engine", "status", "--json"],
                                   env=env, capture_output=True, text=True, timeout=10)
            if state.returncode == 0 and (json.loads(state.stdout) or {}).get("pid") == server.pid:
                break
            if time.monotonic() >= deadline:
                raise AssertionError("explicit engine server did not become ready")
            time.sleep(0.02)
        first = launch()
        again = launch()
        assert first["pid"] == again["pid"] and first["port"] == again["port"]
        with urlopen(Request(first["apiUrl"]+"/__cad/server", headers={"Authorization": "Bearer "+first["token"]})) as response:
            assert json.load(response)["pid"] == first["pid"]
        # The STEP the page imports: one cylinder, written by build123d's own STEP export, so that no
        # CAD file is committed.
        import build123d as bd
        part = bd.Pos(42, 0, 2) * bd.Cylinder(3, 14)
        part.label = "smoke"
        fixture = root / "smoke.step"
        bd.export_step(part, str(fixture))
        # A launch given a file registers it and lands on its page, /<id>.
        opened = launch(str(fixture))
        assert opened["pid"] == first["pid"]
        page_path = urlsplit(opened["url"]).path
        assert page_path == "/" + opened["documents"][0]["id"], opened
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1000, "height": 720})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                with page.expect_response(lambda response: "/__cad/api/doc/" in response.url and "/part/" in response.url and response.ok, timeout=120000):
                    page.goto(opened["url"])
                page.locator(".cad-loading-overlay").wait_for(state="hidden", timeout=120000)
                assert page.locator("canvas").first.is_visible()
                assert not errors, errors
                assert "token=" not in page.url
                assert urlsplit(page.url).path == page_path, page.url
                print("Bundled viewer rendered a STEP on the engine at /<id>; launch reuse and authentication passed.")
            finally:
                browser.close()
    finally:
        subprocess.run([sys.executable, "-m", "cadgen.engine", "stop"], env=env, capture_output=True, timeout=120)
        if server.poll() is None:
            server.terminate()
        server.communicate(timeout=30)
PYTHON
