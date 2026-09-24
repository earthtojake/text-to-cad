import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default ?? traverseModule;
const WORKSPACE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../StepSurface.jsx"
);

function referencedNames(functionPath) {
  const names = new Set();
  functionPath.traverse({
    ReferencedIdentifier(identifierPath) {
      names.add(identifierPath.node.name);
    }
  });
  return names;
}

function workspaceLoadingEffects() {
  const source = fs.readFileSync(WORKSPACE_PATH, "utf8");
  const ast = parse(source, {
    sourceType: "module",
    plugins: ["jsx", "classProperties", "classPrivateProperties", "topLevelAwait"]
  });
  const effects = [];
  traverse(ast, {
    CallExpression(callPath) {
      if (callPath.node.callee?.type !== "Identifier" || callPath.node.callee.name !== "useEffect") {
        return;
      }
      const callbackPath = callPath.get("arguments.0");
      if (!callbackPath?.isFunction()) {
        return;
      }
      const names = referencedNames(callbackPath);
      for (const loaderName of [
        "loadMeshForEntry",
        "loadReferencesForEntry",
        "loadDisplayEdgesForEntry"
      ]) {
        if (names.has(loaderName)) {
          effects.push({
            loaderName,
            callbackPath,
            names,
            run(scope) {
              const callbackSource = source.slice(callbackPath.node.start, callbackPath.node.end);
              // The callback is repository source located by the parser above. Execute that
              // exact body with a small closure substitute so the regression asserts loader
              // behavior rather than an AST spelling or call count in source text.
              return Function("scope", `with (scope) { return (${callbackSource})(); }`)(scope);
            }
          });
        }
      }
    }
  });
  return effects;
}

test("persisted Render loads model documents and shared interaction assets", () => {
  const effects = workspaceLoadingEffects();
  const byLoader = new Map(effects.map((effect) => [effect.loaderName, effect]));
  assert.equal(effects.length, 3, "expected one effect for each document or inspection loader");

  const selectedEntry = { path: "fixture.step" };
  const meshState = { cached: "mesh" };
  const meshEvents = [];
  byLoader.get("loadMeshForEntry").run({
    renderSession: { enabled: true },
    selectedEntry,
    selectedEntryRenderAssetFormat: "step",
    assetKindForRenderFormat: () => "mesh",
    ASSET_KIND: { MESH: "mesh", DRAWING: "drawing" },
    shouldStartMeshLoad: () => true,
    meshLoadInProgress: false,
    meshLoadTargetFile: "",
    meshLoadTargetHash: "",
    fileKey: (entry) => entry.path,
    selectedMeshHash: "hash",
    selectedMeshMatches: false,
    fatalLoadFailure: null,
    isAssemblyView: false,
    selectedAssemblyInteractionReady: false,
    selectedAssemblyHydrationFailed: false,
    meshState,
    loadMeshForEntry: (entry) => {
      meshEvents.push(["load", entry]);
      return Promise.resolve();
    },
    cancelMeshLoad: () => meshEvents.push(["cancel"]),
    setStatus: () => meshEvents.push(["status"]),
    setError: () => meshEvents.push(["error"])
  });
  assert.deepEqual(meshEvents, [["load", selectedEntry]]);
  assert.deepEqual(meshState, { cached: "mesh" });

  const referenceState = { cached: "topology" };
  const referenceEvents = [];
  byLoader.get("loadReferencesForEntry").run({
    selectedEntry,
    selectedEntryHasReferences: true,
    referenceLoadingEnabled: true,
    selectedReferencesMatch: false,
    requestedStepTreeTopologyNodeIds: ["part-1"],
    referenceState,
    cancelReferenceLoad: () => referenceEvents.push("cancel"),
    loadReferencesForEntry: () => {
      referenceEvents.push("load");
      return Promise.resolve();
    },
    setReferenceState: () => referenceEvents.push("state"),
    setReferenceStatus: () => referenceEvents.push("status"),
    setReferenceError: () => referenceEvents.push("error")
  });
  assert.deepEqual(referenceEvents, ["load"]);
  assert.deepEqual(referenceState, { cached: "topology" });

  const displayEdgeState = { cached: "edges" };
  const displayEdgeEvents = [];
  byLoader.get("loadDisplayEdgesForEntry").run({
    selectedEntry,
    selectedStepDisplayEdgesRequested: true,
    selectedDisplayEdgesMatch: false,
    displayEdgeState,
    cancelDisplayEdgeLoad: () => displayEdgeEvents.push("cancel"),
    loadDisplayEdgesForEntry: () => {
      displayEdgeEvents.push("load");
      return Promise.resolve();
    },
    setDisplayEdgeState: () => displayEdgeEvents.push("state"),
    setDisplayEdgeStatus: () => displayEdgeEvents.push("status"),
    setDisplayEdgeError: () => displayEdgeEvents.push("error")
  });
  assert.deepEqual(displayEdgeEvents, ["load"]);
  assert.deepEqual(displayEdgeState, { cached: "edges" });
});
