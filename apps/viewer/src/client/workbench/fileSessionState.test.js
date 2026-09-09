import assert from "node:assert/strict";
import test from "node:test";

import { restoreAnimationState } from "cadgen-js/common/animationClock.js";

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

function urdfEntry(file = "robots/arm.urdf", hash = "urdf-a") {
  return {
    file,
    kind: "urdf",
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
        fileSheetOpenSectionIds: ["tree", "display", "theme"]
      }
    }
  }), { storage });

  const restoredTab = readFileSessionState("models", entry.file, entry, { storage }).slices.tab;
  assert.equal(restoredTab.inspectedAssemblyNodeId, "module-a");
  assert.deepEqual(restoredTab.fileSheetOpenSectionIds, [
    "tree",
    "display",
    "theme"
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
    offset: 0.4,
    offsets: {
      x: 0,
      y: 0,
      z: 0.4
    },
    invert: false
  });
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

test("file session state restores urdf slices only when robot assets match", () => {
  const storage = createMemoryStorage();
  const oldEntry = urdfEntry("robots/arm.urdf", "old-urdf");
  const matchingEntry = urdfEntry("robots/arm.urdf", "old-urdf");
  const staleEntry = urdfEntry("robots/arm.urdf", "new-urdf");

  writeFileSessionState("models", oldEntry.file, createFileSessionSnapshot({
    entry: oldEntry,
    slices: {
      urdf: {
        jointValues: { shoulder: 12.5 }
      }
    }
  }), { storage });

  assert.deepEqual(readFileSessionState("models", oldEntry.file, matchingEntry, { storage }).slices.urdf, {
    jointValues: { shoulder: 12.5 }
  });
  assert.equal(readFileSessionState("models", oldEntry.file, staleEntry, { storage }).slices.urdf, undefined);
});
