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
  sidebarDirectoryPath,
  sidebarDirectoryIdForEntry,
  sidebarLabelForEntry,
  shouldDeferFileParamSelection,
  writeCadParam
} from "./sidebar.js";
import {
  cadWorkspaceDefaultFileSheetWidthForViewport,
  CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH,
  CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
  CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
  CAD_DIRECTORY_SESSION_STORAGE_KEY,
  createDirectorySessionThemeSlice,
  createTabRecord,
  isDirectorySessionThemeSlice,
  readCadDirectorySessionState,
  readCadWorkspaceGlassTone,
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
} from "cadjs/lib/themeSettings.js";
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
  entryIconKind,
  isCodeDerivedEntry
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
      hasMesh: false,
      activeStepArtifactGenerationFiles: ["benchmarks/bracket.step"],
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
    file: "robots/tom/tom.step",
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
      hasMesh: false,
      activeStepArtifactGenerationFiles: ["robots/tom/tom.step"]
    }),
    {
      artifactBuildable: true,
      artifactGenerating: true,
      artifactStale: true,
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "generating artifact"
    }
  );

  assert.equal(
    entryIconKind(entry, {
      sourceFormat: "step",
      status: entryIconStatus(entry, {
        sourceFormat: "step",
        hasMesh: false,
        activeStepArtifactGenerationFiles: ["robots/tom/tom.step"]
      })
    }),
    ENTRY_ICON_KIND.LOADING
  );
});

test("a generated model takes the icon of the imported file it stands in for", () => {
  const generatedAssembly = {
    file: "mechanisms/table.step.py",
    kind: "assembly",
    sourceKind: "python",
    source: { sourcePath: "mechanisms/table.step.py" }
  };
  const importedAssembly = { file: "mechanisms/table.step", kind: "assembly" };
  const generatedPart = {
    file: "parts/bracket.step.py",
    kind: "part",
    source: { sourcePath: "parts/bracket.step.py" }
  };
  const importedPart = { file: "parts/bracket.step", kind: "part" };

  // Generated and imported read alike; the code badge carries the difference.
  assert.equal(
    entryIconKind(generatedAssembly, { sourceFormat: "step" }),
    entryIconKind(importedAssembly, { sourceFormat: "step" })
  );
  assert.equal(entryIconKind(generatedAssembly, { sourceFormat: "step" }), ENTRY_ICON_KIND.STEP);
  assert.equal(
    entryIconKind(generatedPart, { sourceFormat: "step" }),
    entryIconKind(importedPart, { sourceFormat: "step" })
  );
  assert.equal(entryIconKind(generatedPart, { sourceFormat: "step" }), ENTRY_ICON_KIND.STEP);
});

test("a STEP part and a STEP assembly share one file icon", () => {
  const part = entryIconKind({ file: "a.step", kind: "part" }, { sourceFormat: "step" });
  const assembly = entryIconKind({ file: "b.step", kind: "assembly" }, { sourceFormat: "step" });
  assert.equal(part, assembly);
  assert.equal(part, ENTRY_ICON_KIND.STEP);
});

test("an implicit model has its own icon rather than a generic code glyph", () => {
  const implicit = entryIconKind({ file: "a.implicit.js", kind: "implicit" }, { sourceFormat: "implicit" });
  assert.equal(implicit, ENTRY_ICON_KIND.IMPLICIT);
  assert.notEqual(implicit, ENTRY_ICON_KIND.STEP);
});

test("isCodeDerivedEntry marks generator-backed files and nothing else", () => {
  assert.equal(isCodeDerivedEntry({ file: "a.step.py", kind: "assembly" }), true);
  assert.equal(isCodeDerivedEntry({ file: "a.dxf.py", kind: "dxf" }), true);
  assert.equal(isCodeDerivedEntry({ kind: "part", sourceKind: "python" }), true);
  assert.equal(isCodeDerivedEntry({ file: "a.step", kind: "assembly" }), false);
  assert.equal(isCodeDerivedEntry({ file: "a.dxf", kind: "dxf" }), false);
  // An .implicit.js IS the code rather than being generated from it, so it
  // keeps its own icon and takes no badge.
  assert.equal(isCodeDerivedEntry({ file: "a.implicit.js", kind: "implicit" }), false);
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

  assert.equal(stepIcon, ENTRY_ICON_KIND.STEP);
  assert.equal(stlIcon, ENTRY_ICON_KIND.STL_MESH);
  assert.equal(threeMfIcon, ENTRY_ICON_KIND.THREE_MF_MESH);
  assert.equal(glbIcon, ENTRY_ICON_KIND.GLB_MESH);
  assert.equal(staleStepIcon, ENTRY_ICON_KIND.STEP);
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

test("filenameLabelForEntry names the source file, not the logical output", () => {
  // A gen_step model can carry its logical STEP in `file` while the file the user edits is
  // the generator recorded in sourcePath. The label follows the source, so a generator never
  // masquerades as a committed STEP.
  assert.equal(
    filenameLabelForEntry({
      file: "simple/spur_gear_blank.step",
      kind: "part",
      sourceKind: "python",
      sourcePath: "simple/spur_gear_blank.step.py"
    }),
    "spur_gear_blank.step.py"
  );
  // A committed STEP (sourceKind step) keeps the plain `.step` label.
  assert.equal(
    filenameLabelForEntry({
      file: "imports/widget.step",
      kind: "part",
      sourceKind: "step"
    }),
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

test("selectedEntryKeyFromUrl ignores retired refs when explicit file param is missing", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?file=parts%2Fmissing.step&refs=%23f2"
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

test("selectedEntryKeyFromUrl ignores retired refs as file identity", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?refs=%23f2"
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
      "parts/sample_base.step"
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

test("selectedEntryKeyFromUrl ignores retired refs without a file context", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      search: "?refs=%23f2"
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

test("writeCadParam drops retired refs query params", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: {
      href: "http://viewer.test/?file=parts%2Fsample_plate.step&refs=f2",
      pathname: "/",
      search: "?file=parts%2Fsample_plate.step&refs=f2",
      hash: ""
    },
    history: {
      replaceState: (...args) => calls.push(args)
    }
  };

  try {
    writeCadParam("parts/sample_plate.step");
    assert.equal(calls.length, 1);
    assert.equal(calls[0][2], "/?file=parts%2Fsample_plate.step");
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
      href: "http://viewer.test/workspace/models?file=parts%2Fold.step&refs=f2",
      pathname: "/workspace/models",
      search: "?file=parts%2Fold.step&refs=f2",
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
    assert.equal(nextUrl.searchParams.has("refs"), false);
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
