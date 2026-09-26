import assert from "node:assert/strict";
import test from "node:test";

import {
  cadFileParamForEntry,
  findEntryByUrlPath,
  normalizeCadFileQueryParam,
  writeCadParam
} from "./sidebar.js";

test("findEntryByUrlPath matches catalog-root file params exactly", () => {
  const entry = {
    file: "examples/sample_assembly.step",
    kind: "assembly"
  };

  assert.equal(
    findEntryByUrlPath([entry], "examples/sample_assembly.step"),
    entry
  );
  assert.equal(
    findEntryByUrlPath([entry], "examples/sample_assembly"),
    null
  );
});

test("findEntryByUrlPath matches local backend root-relative file params", () => {
  const entry = {
    file: "/tmp/workspace/models/examples/sample_assembly.step",
    rootRelativeFile: "examples/sample_assembly.step",
    kind: "assembly"
  };

  assert.equal(
    findEntryByUrlPath([entry], "examples/sample_assembly.step"),
    entry
  );
  assert.equal(
    findEntryByUrlPath([entry], "/tmp/workspace/models/examples/sample_assembly.step"),
    null
  );
  assert.equal(
    findEntryByUrlPath([entry], "models/examples/sample_assembly.step"),
    null
  );
});

test("cadFileParamForEntry keeps directory navigation root-relative", () => {
  const entry = {
    file: "/tmp/workspace/models/examples/sample_assembly.step",
    rootRelativeFile: "examples/sample_assembly.step",
    kind: "assembly"
  };

  assert.equal(
    cadFileParamForEntry(entry),
    "examples/sample_assembly.step"
  );
});

test("normalizeCadFileQueryParam normalizes file params as relative paths", () => {
  assert.equal(normalizeCadFileQueryParam("parts/sample_plate.step"), "parts/sample_plate.step");
  assert.equal(normalizeCadFileQueryParam("workspace/parts/sample_plate.step"), "workspace/parts/sample_plate.step");
  assert.equal(normalizeCadFileQueryParam("/workspace/imports/widget.step/"), "workspace/imports/widget.step");
});
test("writeCadParam skips unchanged URL replacements", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?file=parts%2Fsample_plate.step",
      pathname: "/",
      search: "?file=parts%2Fsample_plate.step",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(args)
    }
  };

  try {
    writeCadParam("parts/sample_plate.step");
    assert.equal(calls.length, 0);

    writeCadParam("parts/sample_base.step");
    assert.equal(calls.length, 1);
    assert.equal(calls[0][2], "/?file=parts%2Fsample_base.step");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
test("writeCadParam can push user navigation history", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/",
      pathname: "/",
      search: "",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(["replace", ...args]),
      pushState: (...args) => calls.push(["push", ...args])
    }
  };

  try {
    writeCadParam("parts/sample_plate.step", { history: "push" });
    assert.deepEqual(calls.map((call) => call[0]), ["push"]);
    assert.equal(calls[0][3], "/?file=parts%2Fsample_plate.step");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("writeCadParam leaves the directory path untouched", () => {
  // The directory lives in the URL's path; selecting a file must only touch the query.
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/workspace/models?file=parts%2Fold.step",
      pathname: "/workspace/models",
      search: "?file=parts%2Fold.step",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(["replace", ...args]),
      pushState: (...args) => calls.push(["push", ...args])
    }
  };

  try {
    writeCadParam("parts/sample_plate.step", { history: "push" });
    assert.deepEqual(calls.map((call) => call[0]), ["push"]);
    const nextUrl = new URL(`http://viewer.test${calls[0][3]}`);
    assert.equal(nextUrl.pathname, "/workspace/models");
    assert.equal(nextUrl.searchParams.get("file"), "parts/sample_plate.step");
    assert.equal(nextUrl.searchParams.has("dir"), false);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
