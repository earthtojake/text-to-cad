import assert from "node:assert/strict";
import test from "node:test";

import {
  cadFileParamForEntry,
  findEntryByUrlPath,
  normalizeCadFileQueryParam,
  writeCadParam
} from "./sidebar.js";
import {
  CAD_DIRECTORY_SESSION_STORAGE_KEY,
  readCadDirectorySessionState,
  writeCadDirectorySessionState,
} from "./persistence.js";
import { CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH, CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH } from "@hardcore/ui/renderers/cad/state";

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, String(value));
    },
    removeItem: (key) => {
      values.delete(key);
    }
  };
}

test("workspace global session state stores the panel choice, the tree's folders and only custom widths", () => {
  const storage = createMemoryStorage();
  const customFileSheetWidth = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH + 72;

  // Nothing stored is nobody having said, for BOTH panel flags. The file
  // tree's default is the shared panel list's (`@hardcore/ui/navigation`'s
  // `panels.js`) and not a `false` written down here; there is no file-viewer
  // WIDTH at all any more, because there is one panel column and
  // `fileSheetWidthPx` is its width.
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: null,
    fileViewerExpandedDirectoryIds: null,
    fileSheetOpen: null,
    fileSheetWidthPx: null
  });

  assert.equal(writeCadDirectorySessionState({
    fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
  }, { storage }), true);
  assert.equal(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY), null);

  assert.equal(writeCadDirectorySessionState({
    fileSheetWidthPx: CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
  }, {
    storage,
    defaultFileSheetWidthPx: CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
  }), true);
  assert.equal(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY), null);

  assert.equal(writeCadDirectorySessionState({
    fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
  }, {
    storage,
    defaultFileSheetWidthPx: CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
  }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
    }
  );
  assert.deepEqual(readCadDirectorySessionState({
    storage,
    defaultFileSheetWidthPx: CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
  }), {
    fileViewerOpen: null,
    fileViewerExpandedDirectoryIds: null,
    fileSheetOpen: null,
    fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
  });

  assert.equal(writeCadDirectorySessionState({
    fileViewerOpen: true,
    fileSheetOpen: false,
    fileSheetWidthPx: customFileSheetWidth
  }, { storage }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileViewerOpen: true,
      fileSheetOpen: false,
      fileSheetWidthPx: customFileSheetWidth
    }
  );
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: true,
    fileViewerExpandedDirectoryIds: null,
    fileSheetOpen: false,
    fileSheetWidthPx: customFileSheetWidth
  });

  // `false` round-trips as `false`: a person who CLOSED the file tree comes
  // back to it closed, which is the whole reason this field is nullable
  // rather than a plain boolean.
  assert.equal(writeCadDirectorySessionState({
    fileViewerOpen: false,
    fileSheetOpen: true,
    fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
  }, { storage }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileViewerOpen: false,
      fileSheetOpen: true
    }
  );
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: false,
    fileViewerExpandedDirectoryIds: null,
    fileSheetOpen: true,
    fileSheetWidthPx: null
  });

  // The file tree's open folders, deduplicated and kept in order.
  assert.equal(writeCadDirectorySessionState({
    fileViewerExpandedDirectoryIds: ["assemblies", "parts/servo", "assemblies"]
  }, { storage }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileViewerExpandedDirectoryIds: ["assemblies", "parts/servo"]
    }
  );
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: null,
    fileViewerExpandedDirectoryIds: ["assemblies", "parts/servo"],
    fileSheetOpen: null,
    fileSheetWidthPx: null
  });

  // An empty list is a tree with everything shut, and is not the same as
  // never having stored one.
  assert.equal(writeCadDirectorySessionState({
    fileViewerExpandedDirectoryIds: []
  }, { storage }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileViewerExpandedDirectoryIds: []
    }
  );
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: null,
    fileViewerExpandedDirectoryIds: [],
    fileSheetOpen: null,
    fileSheetWidthPx: null
  });
});

test("legacy directory theme overrides are ignored without affecting panel state", () => {
  const storage = createMemoryStorage();
  const legacy = JSON.stringify({ version: 1, fileSheetOpen: true, theme: { themeId: "custom", custom: { projection: "perspective" } } });
  storage.setItem(CAD_DIRECTORY_SESSION_STORAGE_KEY, legacy);
  const state = readCadDirectorySessionState({ storage });
  assert.equal(state.fileSheetOpen, true);
  assert.equal("theme" in state, false);
  assert.equal(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY), legacy);
  writeCadDirectorySessionState(state, { storage });
  assert.deepEqual(JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)), { version: 1, fileSheetOpen: true });
});

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
