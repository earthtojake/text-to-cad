import assert from "node:assert/strict";
import test from "node:test";

import {
  applyServerArgsToEnv,
  parseServerArgs,
} from "./serverArgs.mjs";

test("parseServerArgs accepts direct backend port and host flags", () => {
  assert.deepEqual(
    parseServerArgs(["--port=4190", "--host", "0.0.0.0"]),
    {
      port: 4190,
      host: "0.0.0.0",
      rootDir: "",
      shutdownAfterMs: null,
      help: false,
    }
  );
});

test("parseServerArgs accepts a default directory", () => {
  assert.deepEqual(
    parseServerArgs(["--dir=/tmp/models", "--port", "4190"]),
    {
      port: 4190,
      host: "",
      rootDir: "/tmp/models",
      shutdownAfterMs: null,
      help: false,
    }
  );
  assert.deepEqual(
    parseServerArgs(["--dir", "models"]),
    {
      port: null,
      host: "",
      rootDir: "models",
      shutdownAfterMs: null,
      help: false,
    }
  );
});

test("parseServerArgs accepts an explicit shutdown duration", () => {
  assert.deepEqual(
    parseServerArgs(["--shutdown-after", "12h"]),
    {
      port: null,
      host: "",
      rootDir: "",
      shutdownAfterMs: 12 * 60 * 60 * 1000,
      help: false,
    }
  );
  assert.throws(() => parseServerArgs(["--shutdown-after", "forever"]), /positive duration/);
});

test("parseServerArgs rejects removed root-dir flags", () => {
  assert.throws(
    () => parseServerArgs(["--root-dir", "/tmp/models"]),
    /--root-dir has been removed/
  );
});

test("applyServerArgsToEnv preserves env while keeping CLI port in parsed args", () => {
  const result = applyServerArgsToEnv({
    argv: ["--port", "4190", "--dir", "/tmp/models"],
    cwd: "/tmp/project",
    env: {
      VIEWER_ASSET_BACKEND: "local-fs",
    },
  });

  assert.equal(result.args.port, 4190);
  assert.equal(result.args.rootDir, "/tmp/models");
  assert.equal(result.env.VIEWER_ASSET_BACKEND, "local-fs");
});

test("parseServerArgs rejects invalid ports", () => {
  assert.throws(() => parseServerArgs(["--port", "99999"]), /TCP port/);
});
