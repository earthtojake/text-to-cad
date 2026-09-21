import assert from "node:assert/strict";
import test from "node:test";

import { restoreAnimationState } from "@hardcore/core/common/animationClock.js";

import {
  createFileSessionSnapshot,
  FILE_SESSION_STORAGE_VERSION,
  fileSessionIndexStorageKey,
  fileSessionStorageKey,
  normalizeFileSessionState,
  pruneFileSessionState,
  readFileSessionState,
  writeFileSessionState
} from "./fileSessionState.js";

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

function createThrowingStorage() {
  return {
    getItem: () => null,
    setItem: () => {
      throw new Error("quota exceeded");
    },
    removeItem: () => {
      throw new Error("quota exceeded");
    }
  };
}

function stepEntry(file = "parts/bracket.step", hash = "mesh-a", moduleHash = "module-a") {
  return {
    file,
    kind: "part",
    url: `/assets/${file.split("/").pop()}.glb`,
    hash: moduleHash ? `${hash}:${moduleHash}` : hash,
    bytes: 42
  };
}

function dxfEntry(file = "drawings/bracket.dxf", hash = "dxf-a") {
  return {
    file,
    kind: "dxf",
    url: `/assets/${file.split("/").pop()}`,
    hash
  };
}

test("file session state stores per-file records in isolated namespaces", () => {
  const storage = createMemoryStorage();
  const entry = dxfEntry();

  assert.equal(writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      tab: { referenceQuery: "models-query" }
    }
  }), { storage }), true);
  assert.equal(writeFileSessionState("fixtures", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      tab: { referenceQuery: "fixtures-query" }
    }
  }), { storage }), true);

  assert.equal(readFileSessionState("models", entry.file, entry, { storage }).slices.tab.referenceQuery, "models-query");
  assert.equal(readFileSessionState("fixtures", entry.file, entry, { storage }).slices.tab.referenceQuery, "fixtures-query");
});

test("a stored dxf slice is dropped outright, not migrated", () => {
  // The DXF thickness/bend controls drove a client-side mesh build that no longer exists:
  // the preview is baked by the producer now. A record written before that has no meaning
  // and gets no migration path (design §0.2, §7.4.3).
  const storage = createMemoryStorage();
  const entry = dxfEntry();
  storage.setItem(fileSessionStorageKey("models", entry.file), JSON.stringify({
    version: FILE_SESSION_STORAGE_VERSION,
    fileKey: entry.file,
    signatures: { tab: "whatever" },
    slices: {
      dxf: { thicknessMm: 2.4, bendSettings: [{ id: "bend-1", direction: "down", angleDeg: 91 }] }
    }
  }));
  const restored = readFileSessionState("models", entry.file, entry, { storage });
  assert.deepEqual(restored?.slices ?? {}, {});
});

test("file session state ignores invalid json and version mismatches", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry();
  storage.setItem(fileSessionStorageKey("models", entry.file), "{not json");
  assert.equal(readFileSessionState("models", entry.file, entry, { storage }), null);

  storage.setItem(fileSessionStorageKey("models", entry.file), JSON.stringify({
    version: FILE_SESSION_STORAGE_VERSION + 1,
    fileKey: entry.file,
    slices: {
      tab: { selectedPartIds: ["solid-1"] }
    }
  }));
  assert.equal(readFileSessionState("models", entry.file, entry, { storage }), null);
});

test("retired edge and grid controls cannot be restored from an older session", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry();
  const currentKey = fileSessionStorageKey("models", entry.file);
  const retired = JSON.stringify({
    version: 3,
    fileKey: entry.file,
    slices: {
      display: {
        edges: { thickness: 4, color: "#ff0000" },
        guides: { grid: { enabled: true, density: 3, opacity: 1 } }
      }
    }
  });
  storage.setItem(currentKey.replace(":v4:", ":v3:"), retired);
  assert.equal(readFileSessionState("models", entry.file, entry, { storage }), null);
  storage.setItem(currentKey, retired);
  assert.equal(readFileSessionState("models", entry.file, entry, { storage }), null);
});

test("file session state reports browser storage write failures", () => {
  const errors = [];
  const entry = stepEntry();
  const snapshot = createFileSessionSnapshot({
    entry,
    slices: {
      tab: { selectedPartIds: ["solid-1"] }
    }
  });

  assert.equal(writeFileSessionState("models", entry.file, snapshot, {
    storage: createThrowingStorage(),
    onWriteError: (error) => errors.push(error)
  }), false);
  assert.ok(errors.some((error) => error.key === fileSessionStorageKey("models", entry.file)));
});

test("file session state writes, reads, indexes, and prunes file records", () => {
  const storage = createMemoryStorage();
  const keptEntry = dxfEntry("drawings/kept.dxf", "dxf-kept");
  const staleEntry = dxfEntry("drawings/stale.dxf", "dxf-stale");

  writeFileSessionState("models", keptEntry.file, createFileSessionSnapshot({
    entry: keptEntry,
    slices: {
      tab: { referenceQuery: "kept" }
    }
  }), { storage });
  writeFileSessionState("models", staleEntry.file, createFileSessionSnapshot({
    entry: staleEntry,
    slices: {
      tab: { referenceQuery: "stale" }
    }
  }), { storage });

  assert.deepEqual(JSON.parse(storage.getItem(fileSessionIndexStorageKey("models"))).files, [
    keptEntry.file,
    staleEntry.file
  ]);

  assert.equal(pruneFileSessionState("models", [keptEntry.file], { storage }), true);
  assert.equal(storage.getItem(fileSessionStorageKey("models", staleEntry.file)), null);
  assert.deepEqual(JSON.parse(storage.getItem(fileSessionIndexStorageKey("models"))).files, [keptEntry.file]);
  assert.equal(readFileSessionState("models", keptEntry.file, keptEntry, { storage }).slices.tab.referenceQuery, "kept");
});

test("file session tab state stores file sheet open section ids", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry();

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      tab: {
        inspectedAssemblyNodeId: "module-a",
        fileSheetOpenSectionIds: ["tree", "display", "render"]
      }
    }
  }), { storage });

  const restoredTab = readFileSessionState("models", entry.file, entry, { storage }).slices.tab;
  assert.equal(restoredTab.inspectedAssemblyNodeId, "module-a");
  assert.deepEqual(restoredTab.fileSheetOpenSectionIds, [
    "tree",
    "display",
    "render"
  ]);
});

test("file session tab state ignores global file sheet open state", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry("parts/open.step");

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      tab: {
        fileSheetOpen: true
      }
    }
  }), { storage });

  const restoredTab = readFileSessionState("models", entry.file, entry, { storage }).slices.tab;
  assert.equal(Object.prototype.hasOwnProperty.call(restoredTab, "fileSheetOpen"), false);
});

test("file session tab state stores camera and zoom per file", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry("parts/camera.step");
  const camera = {
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4
  };

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      tab: {
        camera: {
          ...camera,
          modelKey: entry.file,
          sceneScaleMode: "cad",
          coordinateSystem: "cad-z-up-v1"
        }
      }
    }
  }), { storage });

  const rawSession = JSON.parse(storage.getItem(fileSessionStorageKey("models", entry.file)));
  assert.deepEqual(rawSession.slices.tab.camera, camera);
  assert.equal(Object.prototype.hasOwnProperty.call(rawSession.slices.tab, "perspective"), false);
  assert.deepEqual(
    readFileSessionState("models", entry.file, entry, { storage }).slices.tab.camera,
    camera
  );
});

test("file session tab state does not migrate legacy perspective keys", () => {
  const entry = stepEntry("parts/legacy-camera.step");
  const camera = {
    position: [30, 20, 10],
    target: [3, 2, 1],
    up: [0, 0, 1],
    zoom: 1.2
  };

  const session = createFileSessionSnapshot({
    entry,
    slices: {
      tab: {
        perspective: camera
      }
    }
  });

  assert.equal(session.slices.tab.camera, null);
  assert.equal(Object.prototype.hasOwnProperty.call(session.slices.tab, "perspective"), false);
});

test("file session state stores display settings", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry();

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      display: {
        mode: "wireframe",
        clip: {
          enabled: true,
          axis: "z",
          offsets: { z: 0.4 }
        }
      }
    }
  }), { storage });

  const restored = readFileSessionState("models", entry.file, entry, { storage });
  assert.equal(restored.slices.display.mode, "wireframe");
  assert.deepEqual(restored.slices.display.clip, {
    enabled: true,
    axis: "z",
    offsets: { z: 0.4 }
  });
});

test("file session state migrates retired viewer modes and preserves sibling display settings", () => {
  const entry = stepEntry("parts/legacy-display.step");
  const expectedModes = new Map([
    ["shaded", "solid"],
    ["unshaded", "solid"],
    ["hidden_edges", "xray"]
  ]);

  for (const [storedMode, expectedMode] of expectedModes) {
    const restored = normalizeFileSessionState({
      version: FILE_SESSION_STORAGE_VERSION,
      fileKey: entry.file,
      signatures: {},
      slices: {
        display: {
          mode: storedMode,
          clip: { enabled: true, axis: "y", offsets: { y: 0.35 } },
          exploded: { enabled: true, amount: 0.4 },
          guides: { grid: { enabled: false } },
          partColor: { mode: "single", color: "#123456" }
        }
      }
    }, { fileKey: entry.file, skipSignatureCheck: true });

    assert.equal(restored.slices.display.mode, expectedMode, storedMode);
    assert.equal(restored.slices.display.clip.offsets.y, 0.35, storedMode);
    assert.equal(restored.slices.display.exploded.amount, 0.4, storedMode);
    assert.equal(restored.slices.display.grid.enabled, false, storedMode);
    assert.equal(restored.slices.display.surfaces.color, "#123456", storedMode);
  }
});

test("file session state falls back a corrupt viewer mode without discarding valid display settings", () => {
  const entry = stepEntry("parts/corrupt-display.step");
  const restored = normalizeFileSessionState({
    version: FILE_SESSION_STORAGE_VERSION,
    fileKey: entry.file,
    signatures: {},
    slices: {
      display: {
        mode: "definitely_not_a_mode",
        clip: { enabled: true, axis: "x", offsets: { x: 0.6 } },
        guides: { axis: { enabled: false } },
        partColor: { mode: "by_part", colors: ["#abcdef", "#fedcba"] }
      }
    }
  }, { fileKey: entry.file, skipSignatureCheck: true });

  assert.equal(restored.slices.display.mode, "solid");
  assert.equal(restored.slices.display.clip.offsets.x, 0.6);
  assert.equal(restored.slices.display.axes.enabled, false);
  assert.deepEqual(restored.slices.display.surfaces.colors, ["#abcdef", "#fedcba"]);
});

test("file session tab state ignores global file sheet width", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry("parts/custom-width.step");

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      tab: {
        fileSheetWidthPx: 445
      }
    }
  }), { storage });

  const restoredTab = readFileSessionState("models", entry.file, entry, { storage }).slices.tab;
  assert.equal(Object.prototype.hasOwnProperty.call(restoredTab, "fileSheetWidthPx"), false);
});

test("file session state skips stale content-sensitive slices", () => {
  const storage = createMemoryStorage();
  const oldEntry = stepEntry("parts/bracket.step", "old-mesh", "old-module");
  const nextEntry = stepEntry("parts/bracket.step", "new-mesh", "new-module");

  writeFileSessionState("models", oldEntry.file, createFileSessionSnapshot({
    entry: oldEntry,
    slices: {
      tab: {
        selectedPartIds: ["solid-1"],
        hiddenPartIds: ["solid-2"]
      },
      stepModule: {
        enabled: false,
        parameterValues: { elbow: 42 }
      },
      animation: { activeClipId: "meshCycle", elapsedSec: 1.5, speed: 1.2 }
    }
  }), { storage });

  const restored = readFileSessionState("models", nextEntry.file, nextEntry, { storage });
  assert.equal(restored.slices.tab, undefined);
  assert.equal(restored.slices.stepModule, undefined);
  // Both halves of the sidecar ride the same signature: a rebuilt sidecar
  // invalidates the stored pose AND the stored playback position.
  assert.equal(restored.slices.animation, undefined);
});

test("display and Render setup survive ordinary geometry revisions", () => {
  const storage = createMemoryStorage();
  const oldEntry = stepEntry("parts/revised.step", "old-mesh", "old-module");
  const nextEntry = stepEntry("parts/revised.step", "new-mesh", "new-module");

  writeFileSessionState("models", oldEntry.file, createFileSessionSnapshot({
    entry: oldEntry,
    slices: {
      tab: { selectedPartIds: ["old-solid"] },
      display: { mode: "wireframe" },
      render: {
        enabled: true,
        cadProjection: "orthographic",
        payload: {
          quality: "preview",
          exposure: 0.75,
          lighting: { size: 1.4 }
        }
      }
    }
  }), { storage });

  const restored = readFileSessionState("models", nextEntry.file, nextEntry, { storage });
  assert.equal(restored.slices.tab, undefined);
  assert.equal(restored.slices.display.mode, "render");
  assert.deepEqual(restored.slices.render, { cadCamera: null });
  assert.equal(restored.slices.display.lighting.quality, "preview");
  assert.equal(restored.slices.display.lighting.exposure, 0.75);
  assert.equal(restored.slices.display.lighting.size, 1.4);
});

test("A to B to A restores per-file common cameras and migrates a legacy Render camera", () => {
  const storage = createMemoryStorage();
  const entryA = stepEntry("parts/camera-a.step", "mesh-a", "module-a");
  const entryB = stepEntry("parts/camera-b.step", "mesh-b", "module-b");
  const cadA = { position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], projection: "orthographic", orthographicHalfHeight: 18 };
  const renderA = { position: [40, 50, 60], target: [4, 5, 6], up: [0, 0, 1], projection: "perspective", orthographicHalfHeight: 21 };
  const cadB = { position: [-10, -20, 15], target: [-1, -2, 0], up: [0, 0, 1], projection: "orthographic", orthographicHalfHeight: 35 };
  // A exercises migration from the retired mode-specific camera. The live
  // Render camera wins and is persisted as the file's one common camera.
  writeFileSessionState("models", entryA.file, createFileSessionSnapshot({
    entry: entryA,
    slices: { render: {
      enabled: true,
      cadCamera: cadA,
      cadProjection: cadA.projection,
      payload: { quality: "final", camera: renderA }
    } }
  }), { storage });
  // B is already in the canonical shape.
  writeFileSessionState("models", entryB.file, createFileSessionSnapshot({
    entry: entryB,
    slices: { render: {
      enabled: true,
      cadCamera: cadB,
      cadProjection: cadB.projection,
      payload: { quality: "final" }
    } }
  }), { storage });

  const restoredA = readFileSessionState("models", entryA.file, entryA, { storage }).slices.render;
  const restoredB = readFileSessionState("models", entryB.file, entryB, { storage }).slices.render;
  const restoredAAgain = readFileSessionState("models", entryA.file, entryA, { storage }).slices.render;

  assert.deepEqual(restoredA.cadCamera, renderA);
  assert.equal(Object.hasOwn(restoredA, "payload"), false);
  assert.deepEqual(restoredB.cadCamera, cadB);
  assert.equal(Object.hasOwn(restoredB, "payload"), false);
  assert.deepEqual(restoredAAgain, restoredA);
});

test("pose and animation are stored as independent slices", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry("parts/bracket.step", "mesh", "module");

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: {
      stepModule: { enabled: true, parameterValues: { drive: 315 } },
      animation: {
        activeClipId: "meshCycle",
        enabled: false,
        elapsedSec: 2.25,
        speed: 1.5,
        loopEnabled: false
      }
    }
  }), { storage });

  const restored = readFileSessionState("models", entry.file, entry, { storage });
  assert.deepEqual(restored.slices.stepModule, {
    enabled: true,
    parameterValues: { drive: 315 }
  });
  // Each slice carries its OWN gate: the pose gate above says whether the mate
  // graph drives, this one says whether the clip does, and neither restores the
  // other's. A file switched to rest must reopen at rest.
  assert.deepEqual(restored.slices.animation, {
    activeClipId: "meshCycle",
    enabled: false,
    elapsedSec: 2.25,
    speed: 1.5,
    loopEnabled: false
  });
});

test("retired material overrides are ignored without discarding other file state", () => {
  const storage = createMemoryStorage();
  const entry = stepEntry();
  const saved = createFileSessionSnapshot({ entry, slices: { animation: { speed: 1.5 } } });
  // Simulate bytes written before materials became source-owned and read-only.
  saved.slices.materials = { materials: { steel: { roughness: 0.1 } }, assignments: { body: "steel" } };
  saved.signatures.materials = "appearance-a";
  storage.setItem(fileSessionStorageKey("models", entry.file), JSON.stringify(saved));
  const restored = readFileSessionState("models", entry.file, entry, { storage });
  assert.equal(restored.slices.materials, undefined);
  assert.equal(restored.slices.animation.speed, 1.5);
  const snapshot = createFileSessionSnapshot({ entry, slices: saved.slices });
  assert.equal(snapshot.slices.materials, undefined);
});

test("an animation slice stored before the gate existed reopens gated on", () => {
  // End to end, because neither half proves it alone: the stored bytes have no
  // `enabled` field, and the transport the tab actually opens with is whatever
  // restoreAnimationState makes of them against the model's real clips. A slice
  // written before the gate existed is not a slice that asked for animation
  // off. Its idle state was an EMPTY clip id, which is also what the app itself
  // persists while a model's clips are still compiling, so reading either as
  // "the user chose rest" opens a freshly-opened model switched off.
  const storage = createMemoryStorage();
  const entry = stepEntry("parts/bracket.step", "mesh", "module");
  const clips = {
    meshCycle: { id: "meshCycle", label: "Mesh cycle", duration: 6, loop: true, update() {} }
  };

  writeFileSessionState("models", entry.file, createFileSessionSnapshot({
    entry,
    slices: { animation: { activeClipId: "", elapsedSec: 1, speed: 2, loopEnabled: false } }
  }), { storage });

  const slice = readFileSessionState("models", entry.file, entry, { storage }).slices.animation;
  assert.equal(slice.enabled, true);
  assert.deepEqual(restoreAnimationState(slice, clips), {
    activeClipId: "meshCycle",
    enabled: true,
    playing: false,
    elapsedSec: 0,
    // The slice's own transport preferences come back with it.
    speed: 2,
    loopEnabled: false
  });
});

test("file session state stores large-file settings with topology signatures", () => {
  const storage = createMemoryStorage();
  const oldEntry = stepEntry("parts/bracket.step", "old-mesh", "old-module");
  const matchingEntry = stepEntry("parts/bracket.step", "old-mesh", "old-module");
  const staleEntry = stepEntry("parts/bracket.step", "new-mesh", "old-module");

  writeFileSessionState("models", oldEntry.file, createFileSessionSnapshot({
    entry: oldEntry,
    slices: {
      largeFile: {
        selectableTopologyEnabled: true
      }
    }
  }), { storage });

  assert.deepEqual(readFileSessionState("models", oldEntry.file, matchingEntry, { storage }).slices.largeFile, {
    selectableTopologyEnabled: true
  });
  assert.equal(readFileSessionState("models", oldEntry.file, staleEntry, { storage }).slices.largeFile, undefined);
});
