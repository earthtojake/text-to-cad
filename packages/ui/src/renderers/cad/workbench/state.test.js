import assert from 'node:assert/strict';
import test from 'node:test';
import { createTabRecord, cadWorkspaceDefaultFileSheetWidthForViewport, CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH, CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH } from './state.js';
import { resolveDesktopPanelWidth } from '../file-view/fileViewState.js';
import { entryIconStatus } from './entryIconStatus.js';
import { ENTRY_ICON_KIND, entryIconKind } from '../../../file-viewer/navigation/entryIconKind.js';
import { CAD_WORKSPACE_LAYOUT_MODE, CAD_WORKSPACE_DESKTOP_BREAKPOINT_PX, CAD_WORKSPACE_FILE_VIEWER_DEFAULT_OPEN_BREAKPOINT_PX, CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX, CAD_WORKSPACE_MOBILE_BREAKPOINT_PX, getCadWorkspaceLayoutMode, isCadWorkspaceCompactFileSheetViewport, isCadWorkspaceDesktopViewport, isCadWorkspaceMobileViewport, shouldCadWorkspaceDefaultFileViewerOpen, shouldCadWorkspaceDefaultFileSettingsOpen } from './breakpoints.js';

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
      artifactWarning: false,
      loading: false,
      pending: true,
      sourceFormat: "step",
      statusLabel: "compiles on open"
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
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "compiling"
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
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "compiling"
    }
  );

  assert.equal(
    entryIconStatus({
      file: "benchmarks/unbuilt.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_glb"
      }
    }, {
      sourceFormat: "step",
      entryKey: "benchmarks/unbuilt.step",
      hasMesh: false
    }).artifactBuildable,
    true
  );

  assert.equal(
    entryIconStatus({
      file: "benchmarks/generated.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_glb"
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
      artifactWarning: false,
      loading: false,
      pending: false,
      sourceFormat: "step",
      statusLabel: "compiles on open"
    }
  );

  assert.deepEqual(
    entryIconStatus({
      file: "benchmarks/generated.step",
      kind: "part",
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
      artifactWarning: false,
      loading: false,
      pending: true,
      sourceFormat: "step",
      statusLabel: "compiles on open"
    }
  );
});

test("entryIconStatus treats active generator runs as loading and suppresses artifact warnings", () => {
  const entry = {
    file: "robots/tom/tom.step",
    kind: "assembly",
    artifact: {
      ok: false,
      error: "missing_glb"
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
      artifactWarning: false,
      loading: true,
      pending: true,
      sourceFormat: "step",
      statusLabel: "compiling"
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

test("how a model was produced changes nothing about its icon", () => {
  const generatedAssembly = {
    file: "mechanisms/table.step",
    kind: "assembly",
    sourceUrl: "/mechanisms/table.step.json"
  };
  const importedAssembly = { file: "mechanisms/table.step", kind: "assembly" };
  const generatedPart = {
    file: "parts/bracket.step",
    kind: "part",
    sourceUrl: "/parts/bracket.step.json"
  };
  const importedPart = { file: "parts/bracket.step", kind: "part" };

  // Generated and imported read exactly alike: nothing distinguishes them.
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

test("workspace tab records restore old expanded assembly inspection state", () => {
  const record = createTabRecord("assemblies/sample.step", {
    expandedAssemblyPartIds: ["module", "leaf"]
  });

  assert.equal(record.inspectedAssemblyNodeId, "leaf");
  assert.deepEqual(record.expandedAssemblyPartIds, ["module", "leaf"]);
});

test("workspace manual panel widths can open below the model viewport reserve", () => {
  // ONE panel column now, so one number rather than a pair. A width a person
  // dragged past the model viewport's reserve is still their width; only the
  // panel's own range clamps it.
  assert.equal(
    resolveDesktopPanelWidth({ open: true, width: 260, minWidth: 150, maxWidth: 520 }),
    260
  );
  assert.equal(
    resolveDesktopPanelWidth({ open: true, width: 90, minWidth: 150, maxWidth: 520 }),
    150
  );
  assert.equal(
    resolveDesktopPanelWidth({ open: true, width: 900, minWidth: 150, maxWidth: 520 }),
    520
  );
  // A closed panel takes no room at all.
  assert.equal(
    resolveDesktopPanelWidth({ open: false, width: 260, minWidth: 150, maxWidth: 520 }),
    0
  );
});
