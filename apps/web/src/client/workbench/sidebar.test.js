import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSidebarDirectoryTree,
  cadFileParamForEntry,
  findSidebarDirectoryById,
  findEntryByUrlPath,
  missingFileRefForCatalog,
  selectedEntryKeyForFile,
  selectedEntryKeyFromUrl,
  listSidebarItems,
  filenameLabelForEntry,
  normalizeCadFileQueryParam,
  sidebarDirectoryPath,
  sidebarDirectoryIdForEntry,
  sidebarLabelForEntry,
  shouldDeferFileParamSelection,
  writeCadParam
} from "./sidebar.js";
import {
  cadWorkspaceDefaultFileSheetWidthForViewport,
  CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH,
  CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
  CAD_DIRECTORY_SESSION_STORAGE_KEY,
  createDirectorySessionThemeSlice,
  isDirectorySessionThemeSlice,
  readCadDirectorySessionState,
  readThemeSettings,
  readThemeSettingsState,
  readDirectoryThemeSettingsState,
  THEME_STORAGE_KEY,
  THEME_STORAGE_VERSION,
  writeCadDirectorySessionState,
  writeThemeSettings,
  writeThemeState
} from "./persistence.js";
import {
  cloneThemePresetSettings,
  CUSTOM_THEME_ID,
  normalizeThemeSettings,
  SYSTEM_THEME_ID
} from "@hardcore/core/lib/themeSettings.js";
import {
  COLOR_SCHEME_STORAGE_KEY
} from "../ui/colorScheme.js";

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

test("filenameLabelForEntry shows canonical step, stl, 3mf, glb, dxf, urdf, srdf, and sdf suffixes", () => {
  assert.equal(
    filenameLabelForEntry({
      file: "sample_mount.step",
      kind: "part",
      source: { format: "step", path: "parts/sample_mount.step" }
    }),
    "sample_mount.step"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "sample_assembly.step",
      kind: "assembly",
      source: { format: "step", path: "assemblies/sample_assembly.step" }
    }),
    "sample_assembly.step"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "imports/vendor/widget.stp",
      kind: "part",
      source: { format: "stp", path: "imports/vendor/widget.stp" },
      step: { path: "imports/vendor/widget.stp" }
    }),
    "widget.stp"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "sample_robot.urdf",
      kind: "urdf",
      source: { format: "urdf", path: "sample_robot.urdf" },
      name: "sample_robot (URDF)"
    }),
    "sample_robot.urdf"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "sample_robot.srdf",
      kind: "srdf",
      source: { format: "srdf", path: "sample_robot.srdf" },
      name: "sample_robot (SRDF)"
    }),
    "sample_robot.srdf"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "sample_robot.sdf",
      kind: "sdf",
      source: { format: "sdf", path: "sample_robot.sdf" },
      name: "sample_robot (SDF)"
    }),
    "sample_robot.sdf"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "sample_plate.dxf",
      kind: "dxf",
      source: { format: "dxf", path: "drawings/sample_plate.dxf" }
    }),
    "sample_plate.dxf"
  );

  // A `<name>.dxf.py` drawing generator keeps its REAL name. Collapsing it to
  // `gasket_plate.dxf` made it indistinguishable from an imported drawing of the same stem
  // sitting beside it — two entries, one label.
  assert.equal(
    filenameLabelForEntry({
      file: "drawings/gasket_plate.dxf.py",
      kind: "dxf",
      source: { format: "python", path: "drawings/gasket_plate.dxf.py" }
    }),
    "gasket_plate.dxf.py"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "fixtures/bracket.stl",
      kind: "stl",
      source: { format: "stl", path: "fixtures/bracket.stl" }
    }),
    "bracket.stl"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "fixtures/bracket.3mf",
      kind: "3mf",
      source: { format: "3mf", path: "fixtures/bracket.3mf" }
    }),
    "bracket.3mf"
  );

  assert.equal(
    filenameLabelForEntry({
      file: "fixtures/bracket.glb",
      kind: "glb",
      source: { format: "glb", path: "fixtures/bracket.glb" }
    }),
    "bracket.glb"
  );

});

test("filenameLabelForEntry names the file on disk, whatever else an entry carries", () => {
  // A model is an artifact and is presented as one: the label is the basename of the
  // entry's own path, and no other field on the entry can rename it. `moonwatch.step`
  // reads as `moonwatch.step`, whether a script wrote it or someone dropped it there.
  assert.equal(
    filenameLabelForEntry({ file: "simple/spur_gear_blank.step", kind: "part" }),
    "spur_gear_blank.step"
  );
  assert.equal(
    filenameLabelForEntry({
      file: "watches/moonwatch.step",
      kind: "assembly",
      sourceUrl: "/watches/moonwatch.step.json"
    }),
    "moonwatch.step"
  );
  assert.equal(
    filenameLabelForEntry({ file: "drawings/mars_rover_concept.dxf", kind: "dxf" }),
    "mars_rover_concept.dxf"
  );
  assert.equal(
    filenameLabelForEntry({ file: "imports/widget.step", kind: "part" }),
    "widget.step"
  );
});

test("sidebarLabelForEntry uses the same suffix-aware filename labels", () => {
  const entry = {
    file: "sample_assembly.step",
    kind: "assembly",
    source: { format: "step", path: "assemblies/sample_assembly.step" }
  };

  assert.equal(sidebarLabelForEntry(entry), "sample_assembly.step");
});

test("sidebarDirectoryIdForEntry keeps exact CAD file folders", () => {
  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "parts/sample_plate.step",
      kind: "part",
      source: { format: "step", path: "parts/sample_plate.step" }
    }),
    "parts"
  );

  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "drawings/sample_plate.dxf",
      kind: "dxf",
      source: { format: "dxf", path: "drawings/sample_plate.dxf" }
    }),
    "drawings"
  );

  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "sample_robot.urdf",
      kind: "urdf",
      source: { format: "urdf", path: "sample_robot.urdf" }
    }),
    ""
  );

  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "sample_robot.sdf",
      kind: "sdf",
      source: { format: "sdf", path: "sample_robot.sdf" }
    }),
    ""
  );

  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "meshes/fixture.stl",
      kind: "stl",
      source: { format: "stl", path: "meshes/fixture.stl" }
    }),
    "meshes"
  );

  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "meshes/fixture.3mf",
      kind: "3mf",
      source: { format: "3mf", path: "meshes/fixture.3mf" }
    }),
    "meshes"
  );

  assert.equal(
    sidebarDirectoryIdForEntry({
      file: "parts/mount.step",
      kind: "part",
      source: { format: "step", path: "parts/mount.step" }
    }),
    "parts"
  );
});

test("buildSidebarDirectoryTree lists CAD files in their exact source directory", () => {
  const tree = buildSidebarDirectoryTree([
    {
      file: "parts/sample_plate.step",
      kind: "part",
      source: { format: "step", path: "parts/sample_plate.step" }
    },
    {
      file: "drawings/sample_plate.dxf",
      kind: "dxf",
      source: { format: "dxf", path: "drawings/sample_plate.dxf" }
    }
  ]);

  const partsDirectory = tree.directories.find((directory) => directory.id === "parts");
  assert.ok(partsDirectory);
  const drawingsDirectory = tree.directories.find((directory) => directory.id === "drawings");
  assert.ok(drawingsDirectory);
  assert.deepEqual(
    [
      ...listSidebarItems(drawingsDirectory).map((item) => `${item.type}:${item.label}`),
      ...listSidebarItems(partsDirectory).map((item) => `${item.type}:${item.label}`),
    ],
    ["entry:sample_plate.dxf", "entry:sample_plate.step"]
  );
});

test("catalog rows for generated models read as their artifacts, in the artifact's folder", () => {
  // Post-migration the script lives in `models/watches/src/`; the artifact lives in
  // `models/watches/`. The catalog rows ARE the artifacts and are placed by their own
  // paths, so a script elsewhere in the tree cannot pull a row into the wrong folder.
  const tree = buildSidebarDirectoryTree([
    {
      file: "watches/moonwatch.step",
      kind: "assembly",
      sourceUrl: "/watches/moonwatch.step.json"
    },
    {
      file: "watches/mars_rover_concept.step",
      kind: "assembly"
    }
  ]);

  const watchesDirectory = tree.directories.find((directory) => directory.id === "watches");
  assert.ok(watchesDirectory);
  assert.deepEqual(
    listSidebarItems(watchesDirectory).map((item) => `${item.type}:${item.label}`),
    ["entry:mars_rover_concept.step", "entry:moonwatch.step"]
  );
});

test("sidebar directory helpers find nested folders and ancestor paths", () => {
  const tree = buildSidebarDirectoryTree([
    {
      file: "assemblies/robot/arm/base.step",
      kind: "part",
      source: { format: "step", path: "assemblies/robot/arm/base.step" }
    },
    {
      file: "assemblies/robot/wrist.step",
      kind: "part",
      source: { format: "step", path: "assemblies/robot/wrist.step" }
    }
  ], { rootName: "models" });

  const armDirectory = findSidebarDirectoryById(tree, "assemblies/robot/arm");
  assert.equal(armDirectory?.name, "arm");
  assert.equal(findSidebarDirectoryById(tree, "missing"), null);
  assert.deepEqual(
    sidebarDirectoryPath(tree, "assemblies/robot/arm").map((directory) => directory.id),
    ["", "assemblies", "assemblies/robot", "assemblies/robot/arm"]
  );
  assert.deepEqual(sidebarDirectoryPath(tree, "missing"), []);
});

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
    fileSheetWidthPx: null,
    theme: null
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
    fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
    theme: null
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
    fileSheetWidthPx: customFileSheetWidth,
    theme: null
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
    fileSheetWidthPx: null,
    theme: null
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
    fileSheetWidthPx: null,
    theme: null
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
    fileSheetWidthPx: null,
    theme: null
  });
});

// Theme state is one active id plus at most one custom settings blob. Presets
// are read-only, there is no saved-theme library, and selecting a preset is the
// only reset.
function withThemeStorage(run) {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };
  try {
    return run(globalThis.window.localStorage);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
}

function storedTheme(storage) {
  const raw = storage.getItem(THEME_STORAGE_KEY);
  return raw ? JSON.parse(raw) : null;
}

test("selecting a preset stores just the id, with no settings snapshot", () => {
  withThemeStorage((storage) => {
    assert.equal(writeThemeState("blue"), true);
    assert.deepEqual(storedTheme(storage), {
      version: THEME_STORAGE_VERSION,
      themeId: "blue",
      custom: null
    });
    assert.deepEqual(readThemeSettings(), cloneThemePresetSettings("blue"));
    assert.equal(readThemeSettingsState().themeId, "blue");
  });
});

test("the default theme is system, and storing it clears the key", () => {
  withThemeStorage((storage) => {
    assert.equal(readThemeSettingsState().themeId, SYSTEM_THEME_ID);
    assert.equal(writeThemeState("blue"), true);
    assert.notEqual(storage.getItem(THEME_STORAGE_KEY), null);
    assert.equal(writeThemeState(SYSTEM_THEME_ID), true);
    assert.equal(storage.getItem(THEME_STORAGE_KEY), null);
  });
});

test("system resolves to the light or dark preset from the OS preference", () => {
  withThemeStorage(() => {
    assert.deepEqual(
      readThemeSettingsState({ prefersDark: false }).settings,
      cloneThemePresetSettings("workbench-light")
    );
    assert.deepEqual(
      readThemeSettingsState({ prefersDark: true }).settings,
      cloneThemePresetSettings("workbench-dark")
    );
  });
});

test("editing settings moves the active theme into the single custom slot", () => {
  withThemeStorage((storage) => {
    writeThemeState("blue");
    const edited = cloneThemePresetSettings("blue");
    edited.materials.roughness = 0.9123;

    assert.equal(writeThemeSettings(edited), true);
    const payload = storedTheme(storage);
    assert.equal(payload.themeId, CUSTOM_THEME_ID);
    assert.equal(payload.custom.materials.roughness, 0.9123);

    const state = readThemeSettingsState();
    assert.equal(state.themeId, CUSTOM_THEME_ID);
    assert.equal(state.settings.materials.roughness, 0.9123);
  });
});

test("there is only one custom theme: a second edit overwrites the first", () => {
  withThemeStorage((storage) => {
    const first = cloneThemePresetSettings("blue");
    first.materials.roughness = 0.11;
    writeThemeSettings(first);

    const second = cloneThemePresetSettings("clay-sunrise");
    second.materials.roughness = 0.88;
    writeThemeSettings(second);

    const payload = storedTheme(storage);
    assert.equal(payload.themeId, CUSTOM_THEME_ID);
    assert.equal(payload.custom.materials.roughness, 0.88);
  });
});

test("selecting a preset resets the active theme but keeps the custom slot", () => {
  withThemeStorage((storage) => {
    const edited = cloneThemePresetSettings("blue");
    edited.materials.roughness = 0.42;
    writeThemeSettings(edited);

    // Picking a preset is the reset: settings become the preset's again...
    assert.equal(writeThemeState("clay-sunrise"), true);
    assert.deepEqual(readThemeSettings(), cloneThemePresetSettings("clay-sunrise"));

    // ...but the one custom theme survives so it stays selectable.
    assert.equal(storedTheme(storage).custom.materials.roughness, 0.42);
    writeThemeState(CUSTOM_THEME_ID);
    assert.equal(readThemeSettings().materials.roughness, 0.42);
  });
});

test("editing back to an exact preset records the preset, not a custom copy", () => {
  withThemeStorage((storage) => {
    writeThemeSettings(cloneThemePresetSettings("blue"));
    assert.equal(storedTheme(storage).themeId, "blue");
    assert.equal(readThemeSettingsState().themeId, "blue");
  });
});

test("custom cannot be active without a custom slot to point at", () => {
  withThemeStorage((storage) => {
    assert.equal(writeThemeState(CUSTOM_THEME_ID), true);
    assert.equal(storage.getItem(THEME_STORAGE_KEY), null);
    assert.equal(readThemeSettingsState().themeId, SYSTEM_THEME_ID);
  });
});

test("theme persistence ignores payloads from older storage versions", () => {
  withThemeStorage((storage) => {
    storage.setItem(THEME_STORAGE_KEY, JSON.stringify({
      version: THEME_STORAGE_VERSION - 1,
      activeThemeId: "custom:shop-dark",
      themes: [{ id: "custom:shop-dark", label: "Shop dark", theme: cloneThemePresetSettings("blue") }]
    }));
    const state = readThemeSettingsState();
    assert.equal(state.themeId, SYSTEM_THEME_ID);
    assert.deepEqual(state.settings, cloneThemePresetSettings("workbench-light"));
  });
});

test("a directory session may pin its own theme over the global one", () => {
  withThemeStorage(() => {
    globalThis.window.sessionStorage = createMemoryStorage();
    writeThemeState("blue");
    assert.equal(readThemeSettingsState().themeId, "blue");

    const slice = createDirectorySessionThemeSlice({ themeId: "terminal", custom: null });
    assert.deepEqual(slice, { themeId: "terminal", custom: null });
    assert.equal(isDirectorySessionThemeSlice(slice), true);

    writeCadDirectorySessionState({ theme: slice });
    assert.equal(readDirectoryThemeSettingsState().themeId, "terminal");
  });
});

test("a directory slice that only restates the global theme is not stored", () => {
  withThemeStorage(() => {
    writeThemeState("blue");
    // Same as global: nothing to override.
    assert.equal(createDirectorySessionThemeSlice({ themeId: "blue", custom: null }), null);
    // Different from global: a real override.
    assert.deepEqual(
      createDirectorySessionThemeSlice({ themeId: "terminal", custom: null }),
      { themeId: "terminal", custom: null }
    );
  });
});

test("a directory theme slice needs a real id, and custom needs its settings", () => {
  assert.equal(createDirectorySessionThemeSlice({ themeId: "nope" }), null);
  assert.equal(createDirectorySessionThemeSlice({ themeId: CUSTOM_THEME_ID, custom: null }), null);
  assert.equal(isDirectorySessionThemeSlice(null), false);
});

test("selectedEntryKeyFromUrl restores the selected file query param", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=parts%2Fsample_plate.step"
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
        {
          file: "parts/sample_base.step",
          cadPath: "parts/sample_base",
          kind: "part"
        },
        {
          file: "parts/sample_plate.step",
          cadPath: "parts/sample_plate",
          kind: "part"
        }
      ]),
      "parts/sample_plate.step"
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("selectedEntryKeyFromUrl uses VIEWER_DEFAULT_FILE when no file query param exists", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: ""
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
        {
          file: "parts/sample_base.step",
          cadPath: "parts/sample_base",
          kind: "part"
        },
        {
          file: "parts/sample_plate.step",
          cadPath: "parts/sample_plate",
          kind: "part"
        }
      ], { defaultFile: "parts/sample_plate.step" }),
      "parts/sample_plate.step"
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("selectedEntryKeyFromUrl does not fall back to VIEWER_DEFAULT_FILE for missing explicit file params", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=parts%2Fmissing.step"
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
        {
          file: "parts/sample_base.step",
          cadPath: "parts/sample_base",
          kind: "part"
        },
        {
          file: "parts/sample_plate.step",
          cadPath: "parts/sample_plate",
          kind: "part"
        }
      ], { defaultFile: "parts/sample_plate.step" }),
      ""
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
test("selectedEntryKeyFromUrl restores workspace-relative file params", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=workspace%2Fparts%2Fsample_plate.step"
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
        {
          file: "workspace/parts/sample_base.step",
          cadPath: "workspace/parts/sample_base",
          kind: "part"
        },
        {
          file: "workspace/parts/sample_plate.step",
          cadPath: "workspace/parts/sample_plate",
          kind: "part"
        }
      ]),
      "workspace/parts/sample_plate.step"
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("selectedEntryKeyFromUrl requires catalog-root-relative file params", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=models%2Fexamples%2Fsample_assembly.step"
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
        {
          file: "examples/sample_assembly.step",
          kind: "assembly"
        }
      ]),
      ""
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
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

test("selectedEntryKeyFromUrl restores root-relative local backend file params", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=examples%2Fsample_assembly.step"
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
        {
          file: "/tmp/workspace/models/examples/sample_assembly.step",
          rootRelativeFile: "examples/sample_assembly.step",
          kind: "assembly"
        }
      ]),
      "/tmp/workspace/models/examples/sample_assembly.step"
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("file query waits for live catalog hydration before surfacing missing file errors", () => {
  assert.equal(
    shouldDeferFileParamSelection({
      explicitFileParam: "examples/pending.step",
      catalogHydrated: false,
      catalogRefreshing: true
    }),
    true
  );
  assert.equal(
    missingFileRefForCatalog({
      explicitFileParam: "examples/pending.step",
      catalogHydrated: false,
      catalogRefreshing: true
    }),
    ""
  );
  assert.equal(
    missingFileRefForCatalog({
      explicitFileParam: "examples/missing.step",
      catalogHydrated: true,
      catalogRefreshing: false
    }),
    "examples/missing.step"
  );
});

test("file query stays pending while a matched catalog entry is being activated", () => {
  const entry = {
    file: "examples/complex_assembly.step",
    cadPath: "models/examples/complex_assembly",
    kind: "assembly",
    source: { path: "examples/complex_assembly.step" },
    step: { path: "examples/complex_assembly.step" }
  };

  assert.equal(
    shouldDeferFileParamSelection({
      explicitFileParam: "models/examples/complex_assembly.step",
      matchingEntry: entry,
      catalogHydrated: true,
      catalogRefreshing: false
    }),
    true
  );
  assert.equal(
    missingFileRefForCatalog({
      explicitFileParam: "models/examples/complex_assembly.step",
      matchingEntry: entry,
      catalogHydrated: true,
      catalogRefreshing: false
    }),
    ""
  );
  assert.equal(
    shouldDeferFileParamSelection({
      explicitFileParam: "models/examples/complex_assembly.step",
      matchingEntry: entry,
      selectedEntry: entry,
      catalogHydrated: true,
      catalogRefreshing: false
    }),
    false
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

// The file surface is TOLD which file to show, so the selection rule has to work
// off a plain path with no window in sight — that is the whole difference
// between an embedded surface and the standalone app, whose `?file=` reaches the
// same function through selectedEntryKeyFromUrl.
test("selectedEntryKeyForFile selects from a path, with no window", () => {
  const originalWindow = globalThis.window;
  delete globalThis.window;
  const entries = [
    { file: "parts/sample_base.step", cadPath: "parts/sample_base", kind: "part" },
    { file: "parts/sample_plate.step", cadPath: "parts/sample_plate", kind: "part" }
  ];

  try {
    assert.equal(
      selectedEntryKeyForFile(entries, "parts/sample_plate.step"),
      "parts/sample_plate.step"
    );
    // Leading and trailing slashes are normalized away, exactly as a query
    // param's are.
    assert.equal(
      selectedEntryKeyForFile(entries, "/parts/sample_plate.step"),
      "parts/sample_plate.step"
    );
    assert.equal(selectedEntryKeyForFile(entries, "parts/missing.step"), "");
    // No path and no configured default selects nothing rather than guessing.
    assert.equal(selectedEntryKeyForFile(entries, "", { defaultFile: null }), "");
    assert.equal(selectedEntryKeyForFile(entries, null, { defaultFile: null }), "");
    // An empty path is what falls back to the build's default file.
    assert.equal(
      selectedEntryKeyForFile(entries, "", { defaultFile: "parts/sample_base.step" }),
      "parts/sample_base.step"
    );
    // An explicit path that matches nothing does NOT fall back.
    assert.equal(
      selectedEntryKeyForFile(entries, "parts/missing.step", { defaultFile: "parts/sample_base.step" }),
      ""
    );
  } finally {
    if (originalWindow !== undefined) {
      globalThis.window = originalWindow;
    }
  }
});
