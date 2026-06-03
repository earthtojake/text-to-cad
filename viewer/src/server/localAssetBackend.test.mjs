import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { createLocalAssetBackend } from "./localAssetBackend.mjs";

async function withTempDirectoryRoot(callback) {
  const directoryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-backend-"));
  try {
    return await callback(directoryRoot);
  } finally {
    fs.rmSync(directoryRoot, { recursive: true, force: true });
  }
}

function writeStepWithSourceMetadata(filePath, sourcePath) {
  fs.writeFileSync(filePath, [
    "ISO-10303-21;",
    "DATA;",
    `#1=DESCRIPTIVE_REPRESENTATION_ITEM('cadpy:sourcePath','${sourcePath}');`,
    "#2=REPRESENTATION('cadpy:sourcePath',(#1),#9);",
    "#3=PROPERTY_DEFINITION('cadpy metadata','cadpy:sourcePath',#10);",
    "#4=PROPERTY_DEFINITION_REPRESENTATION(#3,#2);",
    "ENDSEC;",
    "END-ISO-10303-21;",
    "",
  ].join("\n"));
}

test("local backend serves catalog from an in-memory scan without writing catalog files", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    const hiddenCatalogPath = path.join(directoryRoot, ".catalog.json");
    const visibleCatalogPath = path.join(directoryRoot, "catalog.json");
    const modelCatalogPath = path.join(modelRoot, "catalog.json");
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "sample.stl"), "solid sample\nendsolid sample\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    const refreshed = backend.refreshCatalog();
    const catalog = backend.readCatalog();

    assert.deepEqual(catalog, refreshed);
    assert.equal(catalog.schemaVersion, 4);
    assert.equal(fs.existsSync(hiddenCatalogPath), false);
    assert.equal(fs.existsSync(visibleCatalogPath), false);
    assert.equal(fs.existsSync(modelCatalogPath), false);
    assert.deepEqual(catalog.entries.map((entry) => ({
      file: entry.file,
      rootRelativeFile: entry.rootRelativeFile,
      kind: entry.kind,
      hasUrl: Boolean(entry.url),
      hasHash: Boolean(entry.hash),
      bytes: entry.bytes,
    })), [{
      file: path.join(modelRoot, "sample.stl"),
      rootRelativeFile: "sample.stl",
      kind: "stl",
      hasUrl: true,
      hasHash: true,
      bytes: "solid sample\nendsolid sample\n".length,
    }]);
    fs.writeFileSync(path.join(modelRoot, "late.stl"), "solid late\nendsolid late\n");
    assert.equal(backend.readCatalog().entries.some((entry) => entry.rootRelativeFile === "late.stl"), false);
    assert.equal(backend.refreshCatalog().entries.some((entry) => entry.rootRelativeFile === "late.stl"), true);
    assert.equal(fs.existsSync(hiddenCatalogPath), false);
    assert.equal(fs.existsSync(visibleCatalogPath), false);
    assert.equal(fs.existsSync(modelCatalogPath), false);
    assert.equal("writeCatalog" in backend, false);
  });
});

test("local backend defaults directory mode to the directory root", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    fs.writeFileSync(path.join(directoryRoot, "sample.stl"), "solid sample\nendsolid sample\n");
    const backend = createLocalAssetBackend({ directoryRoot });

    assert.deepEqual(backend.readCatalog().entries.map((entry) => entry.rootRelativeFile), ["sample.stl"]);
  });
});

test("local backend accepts relative request directories from the directory root", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    fs.mkdirSync(path.join(directoryRoot, "models"), { recursive: true });
    fs.writeFileSync(path.join(directoryRoot, "models", "sample.stl"), "solid sample\nendsolid sample\n");
    const backend = createLocalAssetBackend({ directoryRoot });

    assert.deepEqual(backend.readCatalog({ rootDir: "models" }).entries.map((entry) => entry.rootRelativeFile), ["sample.stl"]);
  });
});

test("local backend keeps directory mode for file params that look absolute", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    fs.mkdirSync(path.join(directoryRoot, "models"), { recursive: true });
    fs.mkdirSync(path.join(directoryRoot, "other"), { recursive: true });
    fs.writeFileSync(path.join(directoryRoot, "models", "inside.stl"), "solid inside\nendsolid inside\n");
    const outsidePath = path.join(directoryRoot, "other", "solo.stl");
    fs.writeFileSync(outsidePath, "solid solo\nendsolid solo\n");
    const backend = createLocalAssetBackend({ directoryRoot });

    const catalog = backend.readCatalog({ rootDir: "models", fileRef: outsidePath });

    assert.deepEqual(catalog.entries.map((entry) => entry.rootRelativeFile), ["inside.stl"]);
    assert.deepEqual(catalog.entries.map((entry) => entry.file), [path.join(directoryRoot, "models", "inside.stl")]);
  });
});

test("local backend keeps directory mode for missing relative file params", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    fs.mkdirSync(path.join(directoryRoot, "models"), { recursive: true });
    fs.writeFileSync(path.join(directoryRoot, "models", "sample.stl"), "solid sample\nendsolid sample\n");
    const backend = createLocalAssetBackend({ directoryRoot });

    assert.deepEqual(
      backend.readCatalog({ rootDir: "models", fileRef: "missing.stl" }).entries.map((entry) => entry.rootRelativeFile),
      ["sample.stl"]
    );
  });
});

test("local backend reports missing request directories", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const backend = createLocalAssetBackend({ directoryRoot });

    assert.throws(
      () => backend.readCatalog({ rootDir: "missing-models" }),
      /CAD Viewer directory not found/
    );
  });
});

test("local backend incrementally refreshes changed CAD catalog entries", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    const firstPath = path.join(modelRoot, "first.stl");
    const secondPath = path.join(modelRoot, "second.stl");
    fs.writeFileSync(firstPath, "solid first\nendsolid first\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    assert.deepEqual(backend.readCatalog().entries.map((entry) => entry.rootRelativeFile), ["first.stl"]);

    fs.writeFileSync(secondPath, "solid second\nendsolid second\n");
    assert.deepEqual(backend.readCatalog().entries.map((entry) => entry.rootRelativeFile), ["first.stl"]);
    assert.deepEqual(
      backend.refreshCatalogForPath({ filePath: secondPath }).entries.map((entry) => entry.rootRelativeFile),
      ["first.stl", "second.stl"]
    );

    fs.unlinkSync(firstPath);
    assert.deepEqual(
      backend.refreshCatalogForPath({ filePath: firstPath }).entries.map((entry) => entry.rootRelativeFile),
      ["second.stl"]
    );
  });
});

test("local backend refreshes requested files against a cached dynamic root catalog", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    const firstPath = path.join(modelRoot, "first.stl");
    const secondPath = path.join(modelRoot, "second.stl");
    fs.writeFileSync(firstPath, "solid first\nendsolid first\n");
    const backend = createLocalAssetBackend({ directoryRoot });

    assert.deepEqual(
      backend.readCatalog({ rootDir: modelRoot, fileRef: "first.stl" }).entries.map((entry) => entry.rootRelativeFile),
      ["first.stl"]
    );

    fs.writeFileSync(secondPath, "solid second\nendsolid second\n");
    assert.deepEqual(
      backend.readCatalog({ rootDir: modelRoot, fileRef: "second.stl" }).entries.map((entry) => entry.rootRelativeFile),
      ["first.stl", "second.stl"]
    );

    fs.unlinkSync(firstPath);
    assert.deepEqual(
      backend.readCatalog({ rootDir: modelRoot, fileRef: "first.stl" }).entries.map((entry) => entry.rootRelativeFile),
      ["second.stl"]
    );
  });
});

test("local backend incrementally refreshes STEP entries when sidecars change", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    const stepPath = path.join(modelRoot, "part.step");
    const modulePath = path.join(modelRoot, ".part.step.js");
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    assert.equal(backend.readCatalog().entries[0].moduleUrl, undefined);

    fs.writeFileSync(modulePath, "export default { manifest: { schemaVersion: 1 } };\n");
    const withModule = backend.refreshCatalogForPath({ filePath: modulePath });
    assert.ok(withModule.entries[0].moduleUrl.startsWith("/__cad/asset?file="));
    assert.equal(withModule.entries[0].moduleFile, modulePath);

    fs.unlinkSync(modulePath);
    const withoutModule = backend.refreshCatalogForPath({ filePath: modulePath });
    assert.equal(withoutModule.entries[0].moduleUrl, undefined);
  });
});

test("local backend reports active generator status for the active root", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    const statusPath = path.join(modelRoot, ".part.step.run-1.generation.lock.json");
    const updatedAt = new Date().toISOString();
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(statusPath, JSON.stringify({
      status: "running",
      id: "run-1",
      pid: process.pid,
      startedAt: updatedAt,
      updatedAt,
      sourcePath: "models/part.py",
      generator: "gen_step",
      outputs: [{ path: "models/part.step", kind: "step" }],
    }));
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    const status = backend.readGenerationStatus();

    assert.equal(status.files[path.join(modelRoot, "part.step")].running, true);
    assert.equal(status.files[path.join(modelRoot, "part.step")].generator, "gen_step");
    assert.equal(backend.generationStatusDir(), modelRoot);
    assert.equal(backend.isGenerationStatusPath(statusPath), true);
  });
});

test("local backend resolves same-stem Python generators without requiring a STEP file", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "box.py"), "def gen_step():\n    return None\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    const resolved = backend.resolveStepSource("box.py");

    assert.equal(resolved.stepPath, path.join(modelRoot, "box.step"));
    assert.equal(resolved.skipStepWrite, true);
  });
});

test("local backend rejects Viewer artifact regeneration when same-stem Python has no STEP file", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    const generatorPath = path.join(modelRoot, "robot", "robot.py");
    fs.mkdirSync(path.dirname(generatorPath), { recursive: true });
    fs.writeFileSync(generatorPath, "def gen_step():\n    return None\n");
    const stepPath = path.join(modelRoot, "robot", "robot.step");
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      stepArtifactGenerator: async () => {
        throw new Error("Python generators should not be invoked by Viewer regeneration.");
      },
    });
    const resolved = backend.resolveStepSource("robot/robot.step");

    assert.equal(resolved.stepPath, stepPath);
    assert.equal(resolved.sourcePath, generatorPath);
    assert.equal(resolved.skipStepWrite, true);
    await assert.rejects(
      () => backend.generateStepArtifact({
        fileRef: "robot/robot.step",
        force: true,
      }),
      /only regenerates GLB artifacts for existing STEP\/STP files/
    );
  });
});

test("local backend regenerates same-stem Python STEP artifacts from the STEP file", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    const generatorPath = path.join(modelRoot, "robot", "robot.py");
    fs.mkdirSync(path.dirname(generatorPath), { recursive: true });
    fs.writeFileSync(generatorPath, "def gen_step():\n    return None\n");
    const stepPath = path.join(modelRoot, "robot", "robot.step");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      stepArtifactGenerator: async (request) => {
        assert.equal(request.stepPath, stepPath);
        assert.equal(request.sourcePath, "");
        assert.equal(request.skipStepWrite, false);
        assert.equal(request.writeStepAfterArtifact, false);
        assert.equal(request.force, true);
        return { ok: true, validation: { ok: true } };
      },
    });
    const resolved = backend.resolveStepSource("robot/robot.step");

    assert.equal(resolved.stepPath, stepPath);
    assert.equal(resolved.sourcePath, generatorPath);
    assert.equal(resolved.skipStepWrite, true);
    const result = await backend.generateStepArtifact({
      fileRef: "robot/robot.step",
      force: true,
    });

    assert.equal(result.ok, true);
    assert.equal(result.stepPath, stepPath);
  });
});

test("local backend regenerates GLB artifacts for imported STEP files", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(path.join(modelRoot, "robot"), { recursive: true });
    const stepPath = path.join(modelRoot, "robot", "robot.step");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      stepArtifactGenerator: async (request) => {
        assert.equal(request.stepPath, stepPath);
        assert.equal(request.sourcePath, "");
        assert.equal(request.skipStepWrite, false);
        assert.equal(request.writeStepAfterArtifact, false);
        assert.equal(request.force, true);
        return { ok: true, validation: { ok: true } };
      },
    });

    const result = await backend.generateStepArtifact({
      fileRef: "robot/robot.step",
      force: true,
    });

    assert.equal(result.ok, true);
    assert.equal(result.stepPath, stepPath);
  });
});

test("local backend regenerates Python metadata STEP artifacts from the STEP file", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(path.join(modelRoot, "generated"), { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "generated", "source.py"), "def gen_step():\n    return None\n");
    const stepPath = path.join(modelRoot, "generated", "part.step");
    writeStepWithSourceMetadata(stepPath, "models/generated/source.py");
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      stepArtifactGenerator: async (request) => {
        assert.equal(request.stepPath, stepPath);
        assert.equal(request.sourcePath, "");
        assert.equal(request.skipStepWrite, false);
        assert.equal(request.writeStepAfterArtifact, false);
        return { ok: true, validation: { ok: true } };
      },
    });
    const catalog = backend.refreshCatalog();

    const result = await backend.generateStepArtifact({
      fileRef: "generated/part.step",
      catalog,
    });

    assert.equal(result.ok, true);
    assert.equal(result.stepPath, stepPath);
  });
});

test("local backend rejects artifact regeneration for non-STEP files", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "robot.urdf"), "<robot name=\"r\" />\n");
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      stepArtifactGenerator: async () => {
        throw new Error("Non-STEP files should not invoke STEP artifact generation.");
      },
    });

    await assert.rejects(
      () => backend.generateStepArtifact({
        fileRef: "robot.urdf",
        force: true,
      }),
      /Only STEP\/STP sources or same-stem Python generators can generate STEP topology artifacts/
    );
  });
});

test("local backend reports missing Python-backed STEP files dynamically", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "box.py"), "def gen_step():\n    return None\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    const status = backend.readStepSourceStatus({ fileRef: "box.step" });

    assert.equal(status.ok, false);
    assert.equal(status.sourceKind, "python");
    assert.equal(status.step.status, "missing");
    assert.equal(status.step.missing, true);
  });
});

test("local backend defers STEP artifact status to current-file status reads", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    const catalogEntry = backend.readCatalog().entries[0];
    const status = backend.readStepSourceStatus({ fileRef: "part.step" });

    assert.equal(catalogEntry.file, path.join(modelRoot, "part.step"));
    assert.equal(catalogEntry.rootRelativeFile, "part.step");
    assert.equal(catalogEntry.artifact, undefined);
    assert.equal(status.artifact.error, "missing_glb");
    assert.equal(status.artifact.glbPath, path.join(modelRoot, ".part.step.glb"));
  });
});

test("local backend resolves selected output files instead of generated GLB artifacts", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    const stepPath = path.join(modelRoot, "part.step");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    fs.writeFileSync(path.join(modelRoot, ".part.step.glb"), "glb");
    const openedPaths = [];
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      sourceFileOpener: async (filePath) => {
        openedPaths.push(filePath);
      },
    });
    const catalog = backend.refreshCatalog();

    const access = backend.resolveFileAssetAccess({
      fileRef: "part.step",
      asset: "output",
      catalog,
    });
    const opened = await backend.openFileAsset({
      fileRef: "part.step",
      asset: "output",
      catalog,
    });

    assert.equal(access.asset, "output");
    assert.equal(access.path, stepPath);
    assert.equal(access.filename, "part.step");
    assert.equal(access.contentType, "application/step");
    assert.deepEqual(openedPaths, [stepPath]);
    assert.deepEqual(opened, {
      asset: "output",
      file: stepPath,
      filename: "part.step",
      opened: true,
    });
  });
});

test("local backend resolves generated GLB artifact assets from catalog URLs", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    const stepPath = path.join(modelRoot, "part.step");
    const artifactPath = path.join(modelRoot, ".part.step.glb");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    fs.writeFileSync(artifactPath, "glb");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });
    const catalog = backend.refreshCatalog();

    const access = backend.resolveFileAssetAccess({
      fileRef: "part.step",
      asset: "artifact",
      catalog,
    });

    assert.equal(access.asset, "artifact");
    assert.equal(access.file, artifactPath);
    assert.equal(access.rootRelativeFile, ".part.step.glb");
    assert.equal(access.path, artifactPath);
    assert.equal(access.filename, ".part.step.glb");
    assert.equal(access.contentType, "model/gltf-binary");
  });
});

test("local backend resolves catalog output files whose names begin with two dots", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    const stepPath = path.join(modelRoot, "..part.step");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });
    const catalog = backend.refreshCatalog();

    const access = backend.resolveFileAssetAccess({
      fileRef: "..part.step",
      asset: "output",
      catalog,
    });

    assert.equal(access.path, stepPath);
    assert.equal(access.file, stepPath);
    assert.equal(access.rootRelativeFile, "..part.step");
    assert.equal(access.filename, "..part.step");
  });
});

test("local backend resolves Python source code separately from output files", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(modelRoot, { recursive: true });
    const stepPath = path.join(modelRoot, "part.step");
    const sourcePath = path.join(modelRoot, "part.py");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    fs.writeFileSync(sourcePath, "def gen_step():\n    return None\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });
    const catalog = backend.refreshCatalog();

    const output = backend.resolveFileAssetAccess({ fileRef: "part.step", asset: "output", catalog });
    const source = backend.resolveFileAssetAccess({ fileRef: "part.step", asset: "source", catalog });

    assert.equal(output.path, stepPath);
    assert.equal(source.asset, "source");
    assert.equal(source.path, sourcePath);
    assert.equal(source.filename, "part.py");
    assert.equal(source.contentType, "text/plain; charset=utf-8");
  });
});

test("local backend resolves directory-root-relative catalog source files", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    const robotDir = path.join(modelRoot, "robots");
    fs.mkdirSync(robotDir, { recursive: true });
    const urdfPath = path.join(robotDir, "robot.urdf");
    const sourcePath = path.join(robotDir, "robot_urdf.py");
    fs.writeFileSync(urdfPath, "<robot name=\"sample\" />\n");
    fs.writeFileSync(sourcePath, "def gen_urdf():\n    return {'xml': '<robot name=\"sample\" />'}\n");
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });
    const catalog = {
      schemaVersion: 4,
      entries: [{
        file: "robots/robot.urdf",
        kind: "urdf",
        sourceKind: "python",
        source: { file: "models/robots/robot_urdf.py" },
      }],
    };

    const source = backend.resolveFileAssetAccess({ fileRef: "robots/robot.urdf", asset: "source", catalog });

    assert.equal(source.asset, "source");
    assert.equal(source.path, sourcePath);
    assert.equal(source.filename, "robot_urdf.py");
  });
});

test("local backend file asset access requires a catalog entry inside the active root", async () => {
  await withTempDirectoryRoot((directoryRoot) => {
    fs.writeFileSync(path.join(directoryRoot, "secret.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
    fs.mkdirSync(path.join(directoryRoot, "models"), { recursive: true });
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    assert.throws(
      () => backend.resolveFileAssetAccess({
        fileRef: "../secret.step",
        asset: "output",
        catalog: { schemaVersion: 4, entries: [{ file: "../secret.step" }] },
      }),
      /outside the active CAD Viewer root|Output file not found/
    );
    assert.throws(
      () => backend.resolveFileAssetAccess({
        fileRef: "part.step",
        asset: "output",
        catalog: { schemaVersion: 4, entries: [] },
      }),
      /CAD catalog entry not found/
    );
  });
});

test("local backend ignores same-stem Python metadata when regenerating existing STEP artifacts", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    const modelRoot = path.join(directoryRoot, "models");
    fs.mkdirSync(path.join(modelRoot, "robot"), { recursive: true });
    fs.writeFileSync(path.join(modelRoot, "robot", "__init__.py"), "\n");
    const generatorPath = path.join(modelRoot, "robot", "robot.py");
    fs.writeFileSync(generatorPath, "def gen_step():\n    return None\n");
    const stepPath = path.join(modelRoot, "robot", "robot.step");
    fs.writeFileSync(stepPath, "ISO-10303-21;\nEND-ISO-10303-21;\n");
    const backend = createLocalAssetBackend({
      directoryRoot,
      rootDir: "models",
      stepArtifactGenerator: async (request) => {
        assert.equal(request.stepPath, stepPath);
        assert.equal(request.sourcePath, "");
        assert.equal(request.skipStepWrite, false);
        assert.equal(request.writeStepAfterArtifact, false);
        return { ok: true, validation: { ok: true } };
      },
    });

    const result = await backend.generateStepArtifact({
      fileRef: "robot/robot.step",
    });

    assert.equal(result.ok, true);
    assert.equal(result.stepPath, stepPath);
  });
});

test("local backend writes only served CAD assets inside the active root", async () => {
  await withTempDirectoryRoot(async (directoryRoot) => {
    fs.mkdirSync(path.join(directoryRoot, "models"), { recursive: true });
    const backend = createLocalAssetBackend({ directoryRoot, rootDir: "models" });

    const written = await backend.writeAsset({ fileRef: ".box.step.glb", body: Buffer.from("glb") });
    const writtenDotDotPrefix = await backend.writeAsset({ fileRef: "..box.step.glb", body: Buffer.from("glb") });

    assert.equal(written.bytes, 3);
    assert.equal(writtenDotDotPrefix.bytes, 3);
    assert.equal(fs.readFileSync(path.join(directoryRoot, "models", ".box.step.glb"), "utf8"), "glb");
    assert.equal(fs.readFileSync(path.join(directoryRoot, "models", "..box.step.glb"), "utf8"), "glb");
    await assert.rejects(
      () => backend.writeAsset({ fileRef: "../escape.glb", body: Buffer.from("bad") }),
      /inside the active CAD Viewer root/
    );
  });
});
