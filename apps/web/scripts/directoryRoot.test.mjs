import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { resolveDirectoryRoot } from "./directoryRoot.mjs";

const appRoot = path.resolve("/checkout/apps/web");
const defaultDirectoryRoot = path.resolve("/checkout/apps");
const resolve = (env, cwd) => resolveDirectoryRoot({ env, cwd, appRoot, defaultDirectoryRoot });

test("the backend starts where npm was invoked, else in the working directory", () => {
  assert.equal(resolve({ INIT_CWD: "/models" }, "/elsewhere"), path.resolve("/models"));
  assert.equal(resolve({}, "/models"), path.resolve("/models"));
  assert.equal(resolveDirectoryRoot({ env: {}, cwd: "/tmp" }), path.resolve("/tmp"), "with no app to stay out of");
});

test("the backend never starts inside the app: the next candidate, else the default", () => {
  assert.equal(resolve({ INIT_CWD: appRoot }, "/models"), path.resolve("/models"));
  assert.equal(resolve({ INIT_CWD: path.join(appRoot, "src") }, appRoot), defaultDirectoryRoot);
});
