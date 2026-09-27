import assert from 'node:assert/strict';
import test from 'node:test';
import { ENTRY_ICON_KIND, entryIconKind } from './entryIconKind.js';

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
