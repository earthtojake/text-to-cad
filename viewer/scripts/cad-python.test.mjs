import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { cadPythonExecutable } from "./cad-python.mjs";

test("launch-root Windows virtualenv wins over the packaged fallback", (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-python-"));
  const python = path.join(root, ".venv", "Scripts", "python.exe");
  fs.mkdirSync(path.dirname(python), { recursive: true });
  fs.writeFileSync(python, "");

  const previousInitCwd = process.env.INIT_CWD;
  const previousViewerPython = process.env.VIEWER_CAD_PYTHON;
  const previousCadPython = process.env.CAD_PYTHON;
  context.after(() => {
    if (previousInitCwd === undefined) delete process.env.INIT_CWD;
    else process.env.INIT_CWD = previousInitCwd;
    if (previousViewerPython === undefined) delete process.env.VIEWER_CAD_PYTHON;
    else process.env.VIEWER_CAD_PYTHON = previousViewerPython;
    if (previousCadPython === undefined) delete process.env.CAD_PYTHON;
    else process.env.CAD_PYTHON = previousCadPython;
    fs.rmSync(root, { recursive: true, force: true });
  });

  process.env.INIT_CWD = root;
  delete process.env.VIEWER_CAD_PYTHON;
  delete process.env.CAD_PYTHON;
  assert.equal(cadPythonExecutable(path.join(root, "packaged-runtime")), python);
});
