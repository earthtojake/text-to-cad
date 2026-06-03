import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSidebarDirectoryTree,
  cadFileParamForEntry,
  findSidebarDirectoryById,
  findEntryByUrlPath,
  missingFileRefForCatalog,
  selectedEntryKeyFromUrl,
  listSidebarItems,
  filenameLabelForEntry,
  normalizeCadFileQueryParam,
  normalizeCadRefQueryParams,
  readCadDirParam,
  sidebarDirectoryPath,
  sidebarDirectoryIdForEntry,
  sidebarLabelForEntry,
  shouldDeferFileParamSelection,
  writeCadDirParam,
  writeCadParam,
  writeCadRefQueryParams
} from "./sidebar.js";
import {
  buildAvailableThemePresets,
  cadWorkspaceDefaultFileSheetWidthForViewport,
  CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH,
  CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
  CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
  CAD_DIRECTORY_SESSION_STORAGE_KEY,
  createDirectorySessionThemeSlice,
  createTabRecord,
  deleteCustomThemePreset,
  getAvailableThemePresetIdForSettings,
  isDirectorySessionThemeSlice,
  readCadDirectorySessionState,
  readCadWorkspaceGlassTone,
  readCustomThemePresets,
  readThemeSettings,
  readThemeSettingsState,
  readThemeSettingsStateFromAppearanceQuery,
  readDirectoryThemeSettingsState,
  resetThemePresetToDefault,
  restoreDefaultThemePresets,
  saveAndActivateCustomThemePreset,
  saveCustomThemePreset,
  serializeThemeSettingsForStorage,
  THEME_STORAGE_KEY,
  updateThemePresetSettings,
  writeCadDirectorySessionState,
  writeCustomThemePresets,
  writeCustomThemePresetLibrary,
  writeThemeSettings
} from "./persistence.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "cadjs/lib/themeSettings.js";
import {
  readStoredActiveCadDir
} from "./cadViewerDirectorySession.mjs";
import {
  CAD_WORKSPACE_MIN_MODEL_VIEWPORT_WIDTH,
  canFitDesktopPanels,
  maxPanelWidthForViewport,
  preferredPanelWidthAfterViewportSync,
  resolveDesktopPanelWidths
} from "../components/workbench/hooks/useCadWorkspaceLayout.js";
import {
  createSessionBackedTabRecord,
  shouldActivateUrlSelection
} from "../components/workbench/hooks/useCadDirectorySession.js";
import {
  CAD_WORKSPACE_LAYOUT_MODE,
  CAD_WORKSPACE_DESKTOP_BREAKPOINT_PX,
  CAD_WORKSPACE_FILE_VIEWER_DEFAULT_OPEN_BREAKPOINT_PX,
  CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX,
  CAD_WORKSPACE_MOBILE_BREAKPOINT_PX,
  getCadWorkspaceLayoutMode,
  isCadWorkspaceCompactFileSheetViewport,
  isCadWorkspaceDesktopViewport,
  isCadWorkspaceMobileViewport,
  shouldCadWorkspaceDefaultFileViewerOpen,
  shouldCadWorkspaceDefaultFileSettingsOpen
} from "./breakpoints.js";
import {
  entryIconStatus,
  entryIsPythonBackedStep,
  entryStepSourceKind
} from "./entryIconStatus.js";
import {
  ENTRY_ICON_KIND,
  entryIconKind
} from "./entryIconKind.js";
import {
  COLOR_SCHEME_STORAGE_KEY
} from "../ui/colorScheme.js";
import {
  fileSessionIndexStorageKey,
  fileSessionStorageKey
} from "./fileSessionState.js";
import {
  CAD_DIRECTORY_STORAGE_EVENT_ACTION,
  cadDirectoryStorageEventAction
} from "./storageEvents.js";

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

test("entryIconStatus marks buildable STEP artifacts as generating in production-capable viewers", () => {
  const entry = {
    file: "benchmarks/bracket.step",
    kind: "part",
    artifact: {
      ok: false,
      error: "missing_glb"
    }
  };

  assert.deepEqual(
    entryIconStatus(entry, {
      sourceFormat: "step",
      entryKey: "benchmarks/bracket.step",
      hasMesh: false
    }),
    {
      artifactBuildable: true,
      artifactGenerating: false,
      artifactStale: false,
      artifactWarning: false,
      loading: false,
      pending: true,
      sourceFormat: "step",
      statusLabel: "artifact generates on open"
    }
  );

  assert.deepEqual(
    entryIconStatus(entry, {
      sourceFormat: "step",
      entryKey: "benchmarks/bracket.step",
      hasMesh: false,
      activeStepArtifactGenerationFile: "benchmarks/bracket.step"
    }),
    {
      artifactBuildable: true,
      artifactGenerating: true,
      artifactStale: false,
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "generating artifact"
    }
  );

  assert.equal(
    entryIconStatus(entry, {
      sourceFormat: "step",
      entryKey: "benchmarks/bracket.step",
      hasMesh: false,
      activeStepArtifactGenerationFiles: [
        "benchmarks/other.step",
        "benchmarks/bracket.step"
      ]
    }).artifactGenerating,
    true
  );

  assert.deepEqual(
    entryIconStatus(entry, {
      sourceFormat: "step",
      entryKey: "benchmarks/bracket.step",
      hasMesh: false,
      activeGenerationFiles: ["benchmarks/.bracket.step.glb"],
      stepArtifactGenerationAvailable: false
    }),
    {
      artifactBuildable: true,
      artifactGenerating: true,
      artifactStale: false,
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "generating artifact"
    }
  );

  assert.equal(
    entryIconStatus({
      file: "benchmarks/stale.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true
      }
    }, {
      sourceFormat: "step",
      entryKey: "benchmarks/stale.step",
      hasMesh: false
    }).artifactBuildable,
    true
  );

  assert.equal(
    entryIconStatus({
      file: "benchmarks/generated.step",
      kind: "part",
      sourceKind: "python",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true,
        sourceKind: "python"
      }
    }, {
      sourceFormat: "step",
      entryKey: "benchmarks/generated.step",
      hasMesh: false
    }).artifactBuildable,
    true
  );

  assert.deepEqual(
    entryIconStatus(entry, {
      sourceFormat: "step",
      entryKey: "benchmarks/bracket.step",
      hasMesh: false,
      stepArtifactGenerationAvailable: false
    }),
    {
      artifactBuildable: false,
      artifactGenerating: false,
      artifactStale: false,
      artifactWarning: true,
      loading: false,
      pending: true,
      sourceFormat: "step",
      statusLabel: "artifacts missing"
    }
  );

  assert.deepEqual(
    entryIconStatus({ file: "prints/bracket.gcode", kind: "gcode" }, {
      sourceFormat: "gcode",
      hasGcode: false
    }),
    {
      artifactBuildable: false,
      artifactGenerating: false,
      artifactStale: false,
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "gcode",
      statusLabel: "pending"
    }
  );

  assert.deepEqual(
    entryIconStatus({
      file: "benchmarks/missing-source.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_source_path"
      }
    }, {
      sourceFormat: "step",
      entryKey: "benchmarks/missing-source.step",
      hasMesh: true
    }),
    {
      artifactBuildable: true,
      artifactGenerating: false,
      artifactStale: false,
      artifactWarning: false,
      loading: false,
      pending: false,
      sourceFormat: "step",
      statusLabel: "artifact generates on open"
    }
  );

  assert.deepEqual(
    entryIconStatus({
      file: "benchmarks/stale.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true
      }
    }, {
      sourceFormat: "step",
      entryKey: "benchmarks/stale.step",
      hasMesh: false
    }),
    {
      artifactBuildable: true,
      artifactGenerating: false,
      artifactStale: true,
      artifactWarning: false,
      loading: false,
      pending: true,
      sourceFormat: "step",
      statusLabel: "artifact generates on open"
    }
  );

  assert.deepEqual(
    entryIconStatus({
      file: "benchmarks/generated.step",
      kind: "part",
      sourceKind: "python",
      artifact: {
        ok: false,
        error: "missing_glb"
      }
    }, {
      sourceFormat: "step",
      entryKey: "benchmarks/generated.step",
      hasMesh: false
    }),
    {
      artifactBuildable: true,
      artifactGenerating: false,
      artifactStale: false,
      artifactWarning: false,
      loading: false,
      pending: true,
      sourceFormat: "step",
      statusLabel: "artifact generates on open"
    }
  );
});

test("entryStepSourceKind only exposes Python generators for source badges", () => {
  assert.equal(
    entryStepSourceKind({
      kind: "part",
      file: "parts/raw.step",
      sourceKind: "step"
    }),
    ""
  );
  assert.equal(
    entryIsPythonBackedStep({
      kind: "part",
      file: "parts/raw.step",
      sourceKind: "step"
    }),
    false
  );
  assert.equal(
    entryIsPythonBackedStep({
      kind: "assembly",
      file: "parts/generated.step",
      sourceKind: "python"
    }),
    true
  );
  assert.equal(
    entryStepSourceKind({
      kind: "part",
      file: "parts/stale.step",
      artifact: { ok: false, sourceKind: "python" }
    }),
    "python"
  );
  assert.equal(
    entryIsPythonBackedStep({
      kind: "part",
      file: "parts/stale.step",
      artifact: { ok: false, sourceKind: "python" }
    }),
    true
  );
  assert.equal(
    entryStepSourceKind({
      kind: "part",
      file: "parts/legacy.step"
    }),
    ""
  );
  assert.equal(
    entryIsPythonBackedStep({
      kind: "dxf",
      file: "drawings/profile.dxf"
    }),
    false
  );
});

test("entryIconStatus treats active generator runs as loading and suppresses artifact warnings", () => {
  const entry = {
    file: "robots/tom/robot_arm.step",
    kind: "assembly",
    sourceKind: "python",
    artifact: {
      ok: false,
      error: "stale_step_artifact",
      stale: true,
      sourceKind: "python"
    }
  };

  assert.deepEqual(
    entryIconStatus(entry, {
      sourceFormat: "step",
      entryKey: "robots/tom/robot_arm.step",
      hasMesh: false,
      activeGenerationFiles: ["robots/tom/robot_arm.step"]
    }),
    {
      artifactBuildable: true,
      artifactGenerating: false,
      artifactStale: true,
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "generating"
    }
  );

  assert.equal(
    entryIconKind(entry, {
      sourceFormat: "step",
      status: entryIconStatus(entry, {
        sourceFormat: "step",
        entryKey: "robots/tom/robot_arm.step",
        hasMesh: false,
        activeGenerationFiles: ["robots/tom/robot_arm.step"]
      })
    }),
    ENTRY_ICON_KIND.LOADING
  );
});

test("entryIconKind gives STEP, STL, 3MF, and GLB distinct file explorer icons", () => {
  const stepIcon = entryIconKind({
    file: "parts/bracket.step",
    kind: "part",
    source: { format: "step", path: "parts/bracket.step" }
  }, { sourceFormat: "step" });
  const stlIcon = entryIconKind({
    file: "meshes/bracket.stl",
    kind: "stl",
    source: { format: "stl", path: "meshes/bracket.stl" }
  }, { sourceFormat: "stl" });
  const threeMfIcon = entryIconKind({
    file: "prints/bracket.3mf",
    kind: "3mf",
    source: { format: "3mf", path: "prints/bracket.3mf" }
  }, { sourceFormat: "3mf" });
  const glbIcon = entryIconKind({
    file: "exports/bracket.glb",
    kind: "glb",
    source: { format: "glb", path: "exports/bracket.glb" }
  }, { sourceFormat: "glb" });
  const staleStepIcon = entryIconKind({
    file: "parts/stale.step",
    kind: "part",
    artifact: { ok: false, stale: true }
  }, {
    sourceFormat: "step",
    status: { artifactWarning: true, artifactStale: true }
  });

  assert.equal(stepIcon, ENTRY_ICON_KIND.STEP_PART);
  assert.equal(stlIcon, ENTRY_ICON_KIND.STL_MESH);
  assert.equal(threeMfIcon, ENTRY_ICON_KIND.THREE_MF_MESH);
  assert.equal(glbIcon, ENTRY_ICON_KIND.GLB_MESH);
  assert.equal(staleStepIcon, ENTRY_ICON_KIND.STEP_PART);
  assert.equal(new Set([stepIcon, stlIcon, threeMfIcon, glbIcon]).size, 4);
});

test("workspace breakpoints split mobile and desktop layouts", () => {
  assert.equal(CAD_WORKSPACE_DESKTOP_BREAKPOINT_PX, CAD_WORKSPACE_MOBILE_BREAKPOINT_PX);
  assert.equal(CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX, 1024);
  assert.equal(getCadWorkspaceLayoutMode(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1), CAD_WORKSPACE_LAYOUT_MODE.MOBILE);
  assert.equal(isCadWorkspaceMobileViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1), true);
  assert.equal(isCadWorkspaceDesktopViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1), false);
  assert.equal(isCadWorkspaceCompactFileSheetViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1), false);

  assert.equal(getCadWorkspaceLayoutMode(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX), CAD_WORKSPACE_LAYOUT_MODE.DESKTOP);
  assert.equal(isCadWorkspaceMobileViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX), false);
  assert.equal(isCadWorkspaceDesktopViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX), true);
  assert.equal(isCadWorkspaceCompactFileSheetViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX), true);
  assert.equal(isCadWorkspaceCompactFileSheetViewport(CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX - 1), true);
  assert.equal(isCadWorkspaceCompactFileSheetViewport(CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX), false);

  assert.equal(getCadWorkspaceLayoutMode(CAD_WORKSPACE_FILE_VIEWER_DEFAULT_OPEN_BREAKPOINT_PX), CAD_WORKSPACE_LAYOUT_MODE.DESKTOP);
});

test("workspace panel defaults keep file viewer closed and file sheet open only on desktop", () => {
  assert.equal(CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH, 280);
  assert.equal(
    cadWorkspaceDefaultFileSheetWidthForViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1),
    CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
  );
  assert.equal(
    cadWorkspaceDefaultFileSheetWidthForViewport(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX),
    CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
  );
  assert.equal(
    cadWorkspaceDefaultFileSheetWidthForViewport(CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX - 1),
    CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
  );
  assert.equal(
    cadWorkspaceDefaultFileSheetWidthForViewport(CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX),
    CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
  );
  assert.equal(
    shouldCadWorkspaceDefaultFileSettingsOpen(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1),
    false
  );
  assert.equal(
    shouldCadWorkspaceDefaultFileSettingsOpen(CAD_WORKSPACE_MOBILE_BREAKPOINT_PX),
    true
  );
  assert.equal(
    shouldCadWorkspaceDefaultFileViewerOpen(CAD_WORKSPACE_FILE_VIEWER_DEFAULT_OPEN_BREAKPOINT_PX - 1),
    false
  );
  assert.equal(
    shouldCadWorkspaceDefaultFileViewerOpen(CAD_WORKSPACE_FILE_VIEWER_DEFAULT_OPEN_BREAKPOINT_PX),
    false
  );
  assert.equal(
    shouldCadWorkspaceDefaultFileViewerOpen(320, { hasSelectedFile: false }),
    false
  );
  assert.equal(
    shouldCadWorkspaceDefaultFileViewerOpen(1600, { hasSelectedFile: false }),
    false
  );
});

test("filenameLabelForEntry shows canonical step, stl, 3mf, glb, gcode, dxf, urdf, srdf, and sdf suffixes", () => {
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

  assert.equal(
    filenameLabelForEntry({
      file: "toolpaths/bracket.gcode",
      kind: "gcode",
      source: { format: "gcode", path: "toolpaths/bracket.gcode" }
    }),
    "bracket.gcode"
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

test("workspace URL selection overrides restored sidebar selection", () => {
  assert.equal(
    shouldActivateUrlSelection({
      selectedKey: "robots/sample.srdf",
      selectedKeyExists: true,
      urlSelectionRequested: true,
      nextSelectedKey: "robots/sample.urdf"
    }),
    true
  );

  assert.equal(
    shouldActivateUrlSelection({
      selectedKey: "robots/sample.srdf",
      selectedKeyExists: false,
      urlSelectionRequested: true,
      nextSelectedKey: "robots/sample.urdf"
    }),
    true
  );
});

test("directory storage events never sync per-file session state across tabs", () => {
  assert.equal(
    cadDirectoryStorageEventAction(fileSessionStorageKey("models", "parts/bracket.step")),
    CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE
  );
  assert.equal(
    cadDirectoryStorageEventAction(fileSessionIndexStorageKey("models")),
    CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE
  );
  assert.equal(
    cadDirectoryStorageEventAction(CAD_DIRECTORY_SESSION_STORAGE_KEY),
    CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE
  );
  assert.equal(
    cadDirectoryStorageEventAction(COLOR_SCHEME_STORAGE_KEY),
    CAD_DIRECTORY_STORAGE_EVENT_ACTION.COLOR_SCHEME
  );
  assert.equal(
    cadDirectoryStorageEventAction(THEME_STORAGE_KEY),
    CAD_DIRECTORY_STORAGE_EVENT_ACTION.THEME
  );
});

test("workspace initial tab records prefer restored file session tab state", () => {
  const record = createSessionBackedTabRecord({
    key: "parts/sample_plate.step",
    createTabRecord,
    initialSelectedTabSnapshot: {
      selectedPartIds: ["fallback"]
    },
    fileSessionState: {
      slices: {
        tab: {
          selectedPartIds: ["restored"],
          inspectedAssemblyNodeId: "inspected",
          hiddenPartIds: ["hidden"]
        }
      }
    }
  });

  assert.equal(record.key, "parts/sample_plate.step");
  assert.deepEqual(record.selectedPartIds, ["restored"]);
  assert.equal(record.inspectedAssemblyNodeId, "inspected");
  assert.deepEqual(record.hiddenPartIds, ["hidden"]);
});

test("workspace tab records restore old expanded assembly inspection state", () => {
  const record = createTabRecord("assemblies/sample.step", {
    expandedAssemblyPartIds: ["module", "leaf"]
  });

  assert.equal(record.inspectedAssemblyNodeId, "leaf");
  assert.deepEqual(record.expandedAssemblyPartIds, ["module", "leaf"]);
});

test("workspace resize sync preserves wider preferred sidebar widths", () => {
  assert.equal(preferredPanelWidthAfterViewportSync(420, 150), 420);
  assert.equal(preferredPanelWidthAfterViewportSync(120, 150), 150);
});

test("workspace panel default width budgets reserve at least 700px for the model viewport", () => {
  assert.equal(CAD_WORKSPACE_MIN_MODEL_VIEWPORT_WIDTH, 700);
  assert.equal(maxPanelWidthForViewport(1024, 520, { openPanelCount: 2 }), 162);
  assert.equal(maxPanelWidthForViewport(900, 560, { openPanelCount: 2 }), 100);
  assert.equal(maxPanelWidthForViewport(900, 560, { openPanelCount: 1 }), 200);
  assert.equal(canFitDesktopPanels(850, [150]), true);
  assert.equal(canFitDesktopPanels(849, [150]), false);
  assert.equal(canFitDesktopPanels(1090, [150, 240]), true);
  assert.equal(canFitDesktopPanels(1089, [150, 240]), false);
});

test("workspace manual panel widths can open below the model viewport reserve", () => {
  assert.deepEqual(
    resolveDesktopPanelWidths({
      viewportWidth: 900,
      sidebarOpen: true,
      sheetOpen: false,
      sidebarWidth: 260,
      sheetWidth: 0,
      sidebarMinWidth: 150,
      sheetMinWidth: 240,
      sidebarMaxWidth: 520,
      sheetMaxWidth: 560
    }),
    {
      sidebarWidth: 260,
      sheetWidth: 0
    }
  );
  assert.deepEqual(
    resolveDesktopPanelWidths({
      viewportWidth: 900,
      sidebarOpen: true,
      sheetOpen: true,
      sidebarWidth: 260,
      sheetWidth: 260,
      sidebarMinWidth: 150,
      sheetMinWidth: 240,
      sidebarMaxWidth: 520,
      sheetMaxWidth: 560
    }),
    {
      sidebarWidth: 260,
      sheetWidth: 260
    }
  );
});

test("workspace global session state stores global panel open state and only custom widths", () => {
  const storage = createMemoryStorage();
  const customFileViewerWidth = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH + 64;
  const customFileSheetWidth = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH + 72;

  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: false,
    fileViewerExpandedDirectoryIds: null,
    fileViewerWidthPx: null,
    fileSheetOpen: null,
    fileSheetWidthPx: null,
    theme: null
  });

  assert.equal(writeCadDirectorySessionState({
    fileViewerWidthPx: CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
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
    fileViewerOpen: false,
    fileViewerExpandedDirectoryIds: null,
    fileViewerWidthPx: null,
    fileSheetOpen: null,
    fileSheetWidthPx: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
    theme: null
  });

  assert.equal(writeCadDirectorySessionState({
    fileViewerWidthPx: customFileViewerWidth,
    fileSheetWidthPx: customFileSheetWidth
  }, { storage }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileViewerWidthPx: customFileViewerWidth,
      fileSheetWidthPx: customFileSheetWidth
    }
  );
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: false,
    fileViewerExpandedDirectoryIds: null,
    fileViewerWidthPx: customFileViewerWidth,
    fileSheetOpen: null,
    fileSheetWidthPx: customFileSheetWidth,
    theme: null
  });

  assert.equal(writeCadDirectorySessionState({
    fileViewerOpen: true,
    fileViewerWidthPx: customFileViewerWidth,
    fileSheetOpen: false,
    fileSheetWidthPx: customFileSheetWidth
  }, { storage }), true);
  assert.deepEqual(
    JSON.parse(storage.getItem(CAD_DIRECTORY_SESSION_STORAGE_KEY)),
    {
      version: 1,
      fileViewerOpen: true,
      fileViewerWidthPx: customFileViewerWidth,
      fileSheetOpen: false,
      fileSheetWidthPx: customFileSheetWidth
    }
  );
  assert.deepEqual(readCadDirectorySessionState({ storage }), {
    fileViewerOpen: true,
    fileViewerExpandedDirectoryIds: null,
    fileViewerWidthPx: customFileViewerWidth,
    fileSheetOpen: false,
    fileSheetWidthPx: customFileSheetWidth,
    theme: null
  });

  assert.equal(writeCadDirectorySessionState({
    fileViewerOpen: false,
    fileViewerWidthPx: CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
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
    fileViewerWidthPx: null,
    fileSheetOpen: true,
    fileSheetWidthPx: null,
    theme: null
  });

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
    fileViewerOpen: false,
    fileViewerExpandedDirectoryIds: ["assemblies", "parts/servo"],
    fileViewerWidthPx: null,
    fileSheetOpen: null,
    fileSheetWidthPx: null,
    theme: null
  });

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
    fileViewerOpen: false,
    fileViewerExpandedDirectoryIds: [],
    fileViewerWidthPx: null,
    fileSheetOpen: null,
    fileSheetWidthPx: null,
    theme: null
  });
});

test("workspace glass tone defaults to inferred light tone", () => {
  assert.equal(readCadWorkspaceGlassTone(), "light");
});

test("built-in theme selection persists active id without theme snapshots", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    assert.equal(writeThemeSettings(cloneThemePresetSettings("blue"), { presetId: "blue" }), true);
    assert.deepEqual(
      JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY)),
      {
        version: 11,
        activeThemeId: "blue",
        themes: []
      }
    );
    assert.deepEqual(readThemeSettingsState(), {
      presetId: "blue",
      settings: cloneThemePresetSettings("blue")
    });
    assert.deepEqual(readThemeSettings(), cloneThemePresetSettings("blue"));

    assert.equal(writeThemeSettings(cloneThemePresetSettings("workbench"), { presetId: "workbench" }), true);

    assert.deepEqual(
      globalThis.window.localStorage.getItem(THEME_STORAGE_KEY),
      null
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme URL param is ignored in favor of stored theme state", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=gcode%2Fsample.gcode&theme=blue"
    },
    localStorage: createMemoryStorage()
  };

  try {
    assert.equal(writeThemeSettings(cloneThemePresetSettings("workbench")), true);
    assert.deepEqual(readThemeSettingsState(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("appearance URL param overrides stored theme state without mutating persistence", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=parts%2Ffixture.step&appearance=workbench"
    },
    localStorage: createMemoryStorage()
  };

  try {
    assert.equal(writeThemeSettings(cloneThemePresetSettings("blue"), { presetId: "blue" }), true);
    const storedTheme = JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY));
    assert.equal(storedTheme.activeThemeId, "blue");
    assert.deepEqual(readThemeSettingsStateFromAppearanceQuery(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
    assert.deepEqual(readThemeSettingsState(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
    assert.equal(
      JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY)).activeThemeId,
      "blue"
    );
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme persistence ignores stale stored built-in workbench snapshots", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const staleWorkbenchTheme = cloneThemePresetSettings("workbench");
    staleWorkbenchTheme.modeColors.dark.background.solidColor = "#d1d5db";
    staleWorkbenchTheme.modeColors.dark.background.linearEnd = "#9ca3af";
    staleWorkbenchTheme.modeColors.dark.floor.color = "#d1d5db";
    staleWorkbenchTheme.modeColors.dark.floor.gridCellColor = "#9ca3af";
    globalThis.window.localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({
        version: 11,
        activeThemeId: "workbench",
        themes: [{
          id: "workbench",
          label: "Workbench",
          presetId: "workbench",
          theme: staleWorkbenchTheme
        }]
      })
    );

    const state = readThemeSettingsState();
    const availableWorkbenchPresets = readCustomThemePresets().filter((preset) => preset.id === "workbench");
    assert.equal(state.presetId, "workbench");
    assert.deepEqual(state.settings, cloneThemePresetSettings("workbench"));
    assert.equal(availableWorkbenchPresets.length, 1);
    assert.deepEqual(availableWorkbenchPresets[0].settings, cloneThemePresetSettings("workbench"));
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme default stays on workbench under system dark mode", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage(),
    matchMedia: () => ({ matches: true })
  };

  try {
    assert.deepEqual(readThemeSettingsState(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme persistence does not store unsaved built-in theme edits", () => {
  const blueThemeSettings = cloneThemePresetSettings("blue");
  const customThemeSettings = normalizeThemeSettings({
    ...blueThemeSettings,
    materials: {
      ...blueThemeSettings.materials,
      brightness: 1.17
    }
  });

  const serialized = serializeThemeSettingsForStorage(customThemeSettings, { presetId: "blue" });
  assert.deepEqual(serialized, {
    version: 11,
    activeThemeId: "blue",
    themes: []
  });
});

test("directory session theme slices keep dirty settings against the active theme", () => {
  const blueThemeSettings = cloneThemePresetSettings("blue");
  const customThemeSettings = normalizeThemeSettings({
    ...blueThemeSettings,
    materials: {
      ...blueThemeSettings.materials,
      brightness: 1.17
    }
  });

  assert.equal(createDirectorySessionThemeSlice({
    presetId: "blue",
    settings: blueThemeSettings
  }), null);

  const slice = createDirectorySessionThemeSlice({
    presetId: "blue",
    settings: customThemeSettings
  });
  assert.deepEqual(slice, {
    presetId: "blue",
    settings: customThemeSettings
  });
  assert.equal(isDirectorySessionThemeSlice(slice), true);
});

test("directory theme state restores unsaved session settings globally", () => {
  const originalWindow = globalThis.window;
  const blueThemeSettings = cloneThemePresetSettings("blue");
  const customThemeSettings = normalizeThemeSettings({
    ...blueThemeSettings,
    materials: {
      ...blueThemeSettings.materials,
      brightness: 1.17
    }
  });
  globalThis.window = {
    location: { search: "" },
    localStorage: createMemoryStorage(),
    sessionStorage: createMemoryStorage()
  };

  try {
    assert.equal(writeThemeSettings(blueThemeSettings, { presetId: "blue" }), true);
    globalThis.window.sessionStorage.setItem(CAD_DIRECTORY_SESSION_STORAGE_KEY, JSON.stringify({
      version: 1,
      theme: {
        presetId: "blue",
        settings: customThemeSettings
      }
    }));
    assert.deepEqual(readDirectoryThemeSettingsState(), {
      presetId: "blue",
      settings: customThemeSettings
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme persistence ignores legacy stored theme state", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    globalThis.window.localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        themeId: "blue",
        customSettings: {
          materials: {
            brightness: 1.17
          }
        }
      })
    );

    assert.deepEqual(readThemeSettingsState(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme persistence ignores previous theme library versions", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const previousWorkbenchTheme = normalizeThemeSettings({
      ...cloneThemePresetSettings("workbench"),
      edges: {
        ...cloneThemePresetSettings("workbench").edges,
        topologyFilter: "feature"
      }
    });
    globalThis.window.localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({
        version: 8,
        activeThemeId: "workbench",
        themes: [{
          id: "workbench",
          label: "Workbench",
          presetId: "workbench",
          theme: previousWorkbenchTheme
        }]
      })
    );

    const availableWorkbenchPresets = readCustomThemePresets().filter((preset) => preset.id === "workbench");
    assert.equal(availableWorkbenchPresets.length, 1);
    assert.deepEqual(availableWorkbenchPresets[0].settings, cloneThemePresetSettings("workbench"));
    assert.deepEqual(readThemeSettingsState(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme persistence ignores stored themes with removed source presets", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const retiredTheme = normalizeThemeSettings({
      ...cloneThemePresetSettings("workbench"),
      background: {
        ...cloneThemePresetSettings("workbench").background,
        solidColor: "#123456"
      }
    });
    globalThis.window.localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({
        version: 11,
        activeThemeId: "custom:retired-shop",
        themes: [{
          id: "custom:retired-shop",
          label: "Retired shop",
          presetId: "retired-preset",
          theme: retiredTheme
        }]
      })
    );

    assert.equal(readCustomThemePresets().some((preset) => preset.id === "custom:retired-shop"), false);
    assert.deepEqual(readThemeSettingsState(), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("custom themes save to local storage and can be selected by id", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const customThemeSettings = normalizeThemeSettings({
      ...cloneThemePresetSettings("blue"),
      background: {
        ...cloneThemePresetSettings("blue").background,
        solidColor: "#101418"
      }
    });
    const savedPreset = saveCustomThemePreset("Shop dark", customThemeSettings);

    assert.equal(savedPreset.label, "Shop dark");
    assert.equal(savedPreset.id, "custom:shop-dark");
    assert.equal(readCustomThemePresets().some((preset) => preset.id === savedPreset.id), true);
    const availableThemePresets = buildAvailableThemePresets(readCustomThemePresets());
    assert.equal(availableThemePresets.some((preset) => preset.id === savedPreset.id), true);
    assert.equal(availableThemePresets.at(-1)?.id, savedPreset.id);
    assert.deepEqual(
      availableThemePresets.find((preset) => preset.id === "blue").settings,
      cloneThemePresetSettings("blue")
    );
    assert.equal(getAvailableThemePresetIdForSettings(customThemeSettings, readCustomThemePresets()), savedPreset.id);

    assert.equal(writeThemeSettings(savedPreset.settings, {
      presetId: savedPreset.id,
      customPresets: readCustomThemePresets()
    }), true);
    const storedTheme = JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY));
    assert.equal(storedTheme.version, 11);
    assert.equal(storedTheme.activeThemeId, savedPreset.id);
    assert.equal(storedTheme.themes.some((theme) => theme.id === "blue"), false);
    const storedSavedTheme = storedTheme.themes.find((theme) => theme.id === savedPreset.id);
    assert.deepEqual(storedSavedTheme.theme, savedPreset.settings);
    assert.deepEqual(readThemeSettingsState(readCustomThemePresets()), {
      presetId: savedPreset.id,
      settings: savedPreset.settings
    });
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("custom themes can be saved and selected atomically", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    assert.equal(writeThemeSettings(cloneThemePresetSettings("blue"), { presetId: "blue" }), true);
    const customThemeSettings = normalizeThemeSettings({
      ...cloneThemePresetSettings("blue"),
      background: {
        ...cloneThemePresetSettings("blue").background,
        solidColor: "#101418"
      }
    });
    const savedTheme = saveAndActivateCustomThemePreset("Shop dark", customThemeSettings, {
      sourceThemeId: "blue",
      customPresets: readCustomThemePresets()
    });

    assert.equal(savedTheme.preset.id, "custom:shop-dark");
    assert.equal(readCustomThemePresets().some((preset) => preset.id === savedTheme.preset.id), true);
    assert.deepEqual(
      buildAvailableThemePresets(readCustomThemePresets()).find((preset) => preset.id === "blue").settings,
      cloneThemePresetSettings("blue")
    );
    assert.deepEqual(readThemeSettingsState(readCustomThemePresets()), {
      presetId: savedTheme.preset.id,
      settings: savedTheme.preset.settings
    });
    const storedTheme = JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY));
    assert.equal(storedTheme.activeThemeId, savedTheme.preset.id);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("themes can be deleted from local storage while at least one remains", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const shopPreset = saveCustomThemePreset("Shop dark", cloneThemePresetSettings("blue"));
    const warmPreset = saveCustomThemePreset("Warm bench", cloneThemePresetSettings("clay"));
    assert.equal(readCustomThemePresets().some((preset) => preset.id === shopPreset.id), true);
    assert.equal(readCustomThemePresets().some((preset) => preset.id === warmPreset.id), true);
    assert.equal(writeThemeSettings(warmPreset.settings, {
      presetId: warmPreset.id,
      customPresets: readCustomThemePresets()
    }), true);

    assert.equal(deleteCustomThemePreset(warmPreset.id), true);
    const customPresets = readCustomThemePresets();
    assert.equal(customPresets.some((preset) => preset.id === shopPreset.id), true);
    assert.equal(customPresets.some((preset) => preset.id === warmPreset.id), false);
    const storedTheme = JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY));
    assert.equal(storedTheme.activeThemeId, "");
    assert.equal(storedTheme.themes.some((preset) => preset.id === shopPreset.id), true);
    assert.deepEqual(readThemeSettingsState(readCustomThemePresets()), {
      presetId: "workbench",
      settings: cloneThemePresetSettings("workbench")
    });
    assert.equal(deleteCustomThemePreset("workbench"), false);
    assert.equal(readCustomThemePresets().some((preset) => preset.id === "workbench"), true);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("custom themes can be updated, reset to their source preset, and fully restored", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const savedPreset = saveCustomThemePreset("Shop blue", cloneThemePresetSettings("blue"), {
      sourceThemeId: "blue"
    });
    const updatedBlueTheme = normalizeThemeSettings({
      ...cloneThemePresetSettings("blue"),
      materials: {
        ...cloneThemePresetSettings("blue").materials,
        brightness: 1.31
      }
    });

    assert.equal(updateThemePresetSettings("blue", updatedBlueTheme), false);
    assert.equal(updateThemePresetSettings(savedPreset.id, updatedBlueTheme), true);
    assert.deepEqual(
      readCustomThemePresets().find((preset) => preset.id === savedPreset.id).settings,
      updatedBlueTheme
    );

    assert.equal(resetThemePresetToDefault("blue"), false);
    assert.equal(resetThemePresetToDefault(savedPreset.id), true);
    assert.deepEqual(
      readCustomThemePresets().find((preset) => preset.id === savedPreset.id).settings,
      cloneThemePresetSettings("blue")
    );

    assert.equal(deleteCustomThemePreset("blue"), false);
    assert.equal(deleteCustomThemePreset(savedPreset.id), true);
    assert.equal(readCustomThemePresets().some((preset) => preset.id === savedPreset.id), false);

    assert.equal(restoreDefaultThemePresets(), true);
    assert.equal(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY), null);
    assert.equal(readCustomThemePresets().some((preset) => preset.id === "blue"), true);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("custom theme library persistence clears the active global theme id", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    assert.equal(writeThemeSettings(cloneThemePresetSettings("blue")), true);
    assert.equal(writeCustomThemePresetLibrary([]), true);
    assert.equal(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY), null);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("custom theme preset updates preserve the active global theme id", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const savedTheme = saveAndActivateCustomThemePreset("Shop dark", cloneThemePresetSettings("blue"), {
      sourceThemeId: "blue"
    });
    assert.equal(writeCustomThemePresets(readCustomThemePresets()), true);
    const storedTheme = JSON.parse(globalThis.window.localStorage.getItem(THEME_STORAGE_KEY));
    assert.equal(storedTheme.version, 11);
    assert.equal(storedTheme.activeThemeId, savedTheme.preset.id);
    assert.equal(storedTheme.themes.some((theme) => theme.id === savedTheme.preset.id), true);
    assert.equal(storedTheme.themes.some((theme) => theme.id === "blue"), false);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("theme persistence ignores legacy full preset payloads", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    localStorage: createMemoryStorage()
  };

  try {
    const legacyCinematic = cloneThemePresetSettings("light");
    delete legacyCinematic.materials.tintMode;
    delete legacyCinematic.materials.emissiveIntensity;
    legacyCinematic.materials.defaultColor = "#aeb9c3";
    legacyCinematic.materials.tintStrength = 0.28;
    legacyCinematic.materials.saturation = 0.42;
    legacyCinematic.materials.contrast = 1.02;
    legacyCinematic.materials.brightness = 0.94;
    legacyCinematic.materials.roughness = 0.46;
    legacyCinematic.materials.metalness = 0.02;
    legacyCinematic.materials.clearcoat = 0.18;
    legacyCinematic.materials.clearcoatRoughness = 0.34;
    legacyCinematic.materials.envMapIntensity = 0.58;
    legacyCinematic.edges.enabled = false;
    legacyCinematic.edges.color = "#8fa1b5";
    legacyCinematic.edges.opacity = 0.1;
    legacyCinematic.edges.thickness = 1;
    legacyCinematic.background.solidColor = "#050711";
    legacyCinematic.background.linearStart = "#02040b";
    legacyCinematic.background.linearEnd = "#252f47";
    legacyCinematic.background.linearAngle = 90;
    legacyCinematic.background.radialInner = "#171d30";
    legacyCinematic.background.radialOuter = "#02040b";
    legacyCinematic.floor.color = "#141a29";
    legacyCinematic.floor.roughness = 0.62;
    legacyCinematic.floor.reflectivity = 0.22;
    legacyCinematic.floor.shadowOpacity = 0.24;
    legacyCinematic.floor.horizonBlend = 0.28;
    legacyCinematic.environment.enabled = true;
    legacyCinematic.environment.intensity = 0.46;
    legacyCinematic.environment.rotationY = -0.35;
    legacyCinematic.lighting.toneMappingExposure = 1.2;
    legacyCinematic.lighting.directional.color = "#f1f6fb";
    legacyCinematic.lighting.directional.intensity = 2.45;
    legacyCinematic.lighting.directional.position = { x: -190, y: 300, z: 210 };
    legacyCinematic.lighting.spot.color = "#dbeafe";
    legacyCinematic.lighting.spot.intensity = 1.34;
    legacyCinematic.lighting.spot.angle = 0.72;
    legacyCinematic.lighting.spot.position = { x: 160, y: 245, z: 126 };
    legacyCinematic.lighting.point.color = "#8fb6d8";
    legacyCinematic.lighting.point.intensity = 0.34;
    legacyCinematic.lighting.point.position = { x: -260, y: 95, z: -220 };
    legacyCinematic.lighting.ambient.color = "#1e293b";
    legacyCinematic.lighting.ambient.intensity = 0.2;
    legacyCinematic.lighting.hemisphere.skyColor = "#dbe7f3";
    legacyCinematic.lighting.hemisphere.groundColor = "#070a14";
    legacyCinematic.lighting.hemisphere.intensity = 0.68;

    globalThis.window.localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(legacyCinematic));

    assert.deepEqual(readThemeSettings(), cloneThemePresetSettings("workbench"));
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("normalizeCadRefQueryParams accepts relative refs", () => {
  assert.deepEqual(
    normalizeCadRefQueryParams(["parts/sample_plate#f2", "@cad[parts/sample_base#e1]"]),
    ["@cad[parts/sample_plate#f2]", "@cad[parts/sample_base#e1]"]
  );
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

test("selectedEntryKeyFromUrl does not use refs to mask a missing explicit file param", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=parts%2Fmissing.step&refs=parts%2Fsample_plate%23f2"
    }
  };

  try {
    assert.equal(
      selectedEntryKeyFromUrl([
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

test("selectedEntryKeyFromUrl prefers explicit refs over VIEWER_DEFAULT_FILE when no file param exists", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?refs=parts%2Fsample_plate%23f2"
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
      ], { defaultFile: "parts/sample_base.step" }),
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

test("selectedEntryKeyFromUrl restores the selected canonical ref query param", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?refs=parts%2Fsample_plate%23f2"
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

test("writeCadParam skips unchanged URL replacements", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23f2",
      pathname: "/",
      search: "?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23f2",
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
    assert.equal(calls[0][2], "/?file=parts%2Fsample_base.step&refs=parts%2Fsample_plate%23f2");
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

test("writeCadParam stores active dir and omits dir for directory file selections", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?dir=docs%2Fpublic&refs=parts%2Fsample_plate%23f2",
      pathname: "/",
      search: "?dir=docs%2Fpublic&refs=parts%2Fsample_plate%23f2",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(args)
    },
    sessionStorage: createMemoryStorage()
  };

  try {
    writeCadParam("hero/planetary_gear_assembly.step.glb");
    assert.equal(calls.length, 1);
    const nextUrl = new URL(`http://viewer.test${calls[0][2]}`);
    assert.equal(nextUrl.searchParams.has("dir"), false);
    assert.equal(nextUrl.searchParams.get("file"), "hero/planetary_gear_assembly.step.glb");
    assert.equal(nextUrl.searchParams.get("refs"), "parts/sample_plate#f2");
    assert.equal(readStoredActiveCadDir(), "docs/public");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("writeCadParam keeps explicit dir when clearing file selection", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?dir=docs%2Fpublic&file=hero%2Fplanetary_gear_assembly.step.glb",
      pathname: "/",
      search: "?dir=docs%2Fpublic&file=hero%2Fplanetary_gear_assembly.step.glb",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(args)
    },
    sessionStorage: createMemoryStorage()
  };

  try {
    writeCadParam("");
    assert.equal(calls.length, 1);
    const nextUrl = new URL(`http://viewer.test${calls[0][2]}`);
    assert.equal(nextUrl.searchParams.get("dir"), "docs/public");
    assert.equal(nextUrl.searchParams.has("file"), false);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("writeCadParam keeps explicit dir when active dir cannot be stored", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?dir=docs%2Fpublic",
      pathname: "/",
      search: "?dir=docs%2Fpublic",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(args)
    }
  };

  try {
    writeCadParam("hero/planetary_gear_assembly.step.glb");
    assert.equal(calls.length, 1);
    const nextUrl = new URL(`http://viewer.test${calls[0][2]}`);
    assert.equal(nextUrl.searchParams.get("dir"), "docs/public");
    assert.equal(nextUrl.searchParams.get("file"), "hero/planetary_gear_assembly.step.glb");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("writeCadDirParam selects a workspace and clears file selection", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23f2",
      pathname: "/",
      search: "?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23f2",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(["replace", ...args]),
      pushState: (...args) => calls.push(["push", ...args])
    },
    sessionStorage: createMemoryStorage()
  };

  try {
    assert.equal(readCadDirParam(), null);
    writeCadDirParam("/workspace/models", { history: "push" });
    assert.deepEqual(calls.map((call) => call[0]), ["push"]);
    const nextUrl = new URL(`http://viewer.test${calls[0][3]}`);
    assert.equal(nextUrl.searchParams.get("dir"), "/workspace/models");
    assert.equal(nextUrl.searchParams.has("file"), false);
    assert.equal(nextUrl.searchParams.get("refs"), "parts/sample_plate#f2");
    assert.equal(readStoredActiveCadDir(), "/workspace/models");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("writeCadRefQueryParams skips unchanged URL replacements", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23f2",
      pathname: "/",
      search: "?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23f2",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(args)
    }
  };

  try {
    writeCadRefQueryParams(["@cad[parts/sample_plate#f2]"]);
    assert.equal(calls.length, 0);

    writeCadRefQueryParams(["@cad[parts/sample_plate#e1]"]);
    assert.equal(calls.length, 1);
    assert.equal(calls[0][2], "/?file=parts%2Fsample_plate.step&refs=parts%2Fsample_plate%23e1");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
