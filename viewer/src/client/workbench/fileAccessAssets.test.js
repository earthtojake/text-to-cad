import assert from "node:assert/strict";
import test from "node:test";

import {
  copyTargetsForFileAccessAsset,
  downloadUrlForFileAsset,
  fileAccessAssetsForEntry,
  openUrlForFileAsset
} from "./fileAccessAssets.js";

const viewerServerInfo = {
  directoryRoot: "/project/text-to-cad",
  rootDir: "models",
  rootPath: "/project/text-to-cad/models",
};

const hostedViewerServerInfo = {
  backend: "vercel-blob",
  rootDir: "",
  url: "https://demo.example.test",
};

test("file access assets always include output filename", () => {
  const assets = fileAccessAssetsForEntry({
    file: "assemblies/robot-arm/robot-arm.step",
    sourceKind: "step",
  });

  assert.deepEqual(assets.output, {
    asset: "output",
    fileRef: "assemblies/robot-arm/robot-arm.step",
    filename: "robot-arm.step",
    label: "robot-arm.step",
    rootRelativePath: "assemblies/robot-arm/robot-arm.step",
  });
  assert.equal(assets.source, null);
});

test("file access assets include generated artifact URLs when present", () => {
  const assets = fileAccessAssetsForEntry({
    file: "assemblies/robot-arm/robot-arm.step",
    url: "/models/assemblies/robot-arm/.robot-arm.step.glb?v=123",
  }, {
    viewerServerInfo,
  });

  assert.deepEqual(assets.artifact, {
    asset: "artifact",
    fileRef: "assemblies/robot-arm/robot-arm.step",
    filename: ".robot-arm.step.glb",
    label: ".robot-arm.step.glb",
    rootRelativePath: "assemblies/robot-arm/.robot-arm.step.glb",
  });
});

test("file access assets expose direct Blob download URLs for hosted catalogs", () => {
  const assets = fileAccessAssetsForEntry({
    file: "assemblies/robot-arm/robot-arm.step",
    kind: "assembly",
    url: "https://blob.example.test/models2/assemblies/robot-arm/.robot-arm.step.glb",
    sourceKind: "step",
    step: {
      url: "https://blob.example.test/models2/assemblies/robot-arm/robot-arm.step",
    },
  }, {
    viewerServerInfo: hostedViewerServerInfo,
  });

  assert.equal(
    assets.output.downloadUrl,
    "https://blob.example.test/models2/assemblies/robot-arm/robot-arm.step"
  );
  assert.equal(
    assets.artifact.downloadUrl,
    "https://blob.example.test/models2/assemblies/robot-arm/.robot-arm.step.glb"
  );
});

test("file access assets infer same-stem Python source filenames for Python-backed STEP entries", () => {
  const assets = fileAccessAssetsForEntry({
    file: "assemblies/robot-arm/robot-arm.step",
    sourceKind: "python",
  });

  assert.equal(assets.source?.asset, "source");
  assert.equal(assets.source?.fileRef, "assemblies/robot-arm/robot-arm.step");
  assert.equal(assets.source?.filename, "robot-arm.py");
  assert.equal(assets.source?.label, "robot-arm.py");
  assert.equal(assets.source?.rootRelativePath, "assemblies/robot-arm/robot-arm.py");
});

test("file access assets prefer loaded STEP source status filenames", () => {
  const assets = fileAccessAssetsForEntry({
    file: "generated/robot.step",
    sourceKind: "python",
  }, {
    stepSourceStatus: {
      sourceKind: "python",
      sourcePath: "models/generated/source/robot_module.py",
    },
  });

  assert.equal(assets.source?.filename, "robot_module.py");
  assert.equal(assets.source?.label, "robot_module.py");
  assert.equal(assets.source?.directoryRelativePath, "models/generated/source/robot_module.py");
});

test("file access assets expose explicit catalog source files without changing catalog schema", () => {
  const assets = fileAccessAssetsForEntry({
    file: "generated/robot.step",
    source: {
      file: "generated/robot_source.py",
    },
  });

  assert.equal(assets.source?.filename, "robot_source.py");
  assert.equal(assets.source?.rootRelativePath, "generated/robot_source.py");
});

test("file access assets preserve directory-relative generator source paths", () => {
  const assets = fileAccessAssetsForEntry({
    file: "robots/tom/robot_arm.urdf",
    kind: "urdf",
    sourceKind: "python",
    source: {
      file: "models/robots/tom/robot_arm_urdf.py",
      sourcePath: "models/robots/tom/robot_arm_urdf.py",
    },
  });

  assert.equal(assets.source?.filename, "robot_arm_urdf.py");
  assert.equal(assets.source?.rootRelativePath, "");
  assert.equal(assets.source?.directoryRelativePath, "models/robots/tom/robot_arm_urdf.py");
});

test("file access download URLs target exact output or source assets", () => {
  assert.equal(
    downloadUrlForFileAsset("assemblies/robot arm.step", "source"),
    "/__cad/download?file=assemblies%2Frobot%20arm.step&asset=source"
  );
  assert.equal(
    downloadUrlForFileAsset("assemblies/robot arm.step", "output", "https://cad.example.test/viewer"),
    "https://cad.example.test/__cad/download?file=assemblies%2Frobot%20arm.step&asset=output"
  );
});

test("file access open URLs target the local reveal endpoint", () => {
  assert.equal(
    openUrlForFileAsset("assemblies/robot arm.step", "source"),
    "/__cad/reveal?file=assemblies%2Frobot%20arm.step&asset=source"
  );
  assert.equal(
    openUrlForFileAsset("assemblies/robot arm.step", "output", "http://127.0.0.1:4179/viewer"),
    "http://127.0.0.1:4179/__cad/reveal?file=assemblies%2Frobot%20arm.step&asset=output"
  );
});

test("file access copy targets include absolute and directory-relative local paths", () => {
  const targets = copyTargetsForFileAccessAsset({
    rootRelativePath: "assemblies/robot-arm/robot-arm.step",
  }, {
    directoryRoot: "/project/text-to-cad",
    rootDir: "models",
    rootPath: "/project/text-to-cad/models",
  });

  assert.deepEqual(targets, {
    path: "/project/text-to-cad/models/assemblies/robot-arm/robot-arm.step",
    relativePath: "assemblies/robot-arm/robot-arm.step",
  });
});

test("file access copy targets prefer loaded source directory-relative paths", () => {
  const targets = copyTargetsForFileAccessAsset({
    rootRelativePath: "generated/robot.py",
    directoryRelativePath: "models/generated/source/robot_module.py",
  }, {
    directoryRoot: "/project/text-to-cad",
    rootDir: "models",
    rootPath: "/project/text-to-cad/models",
  });

  assert.deepEqual(targets, {
    path: "/project/text-to-cad/models/generated/source/robot_module.py",
    relativePath: "generated/source/robot_module.py",
  });
});

test("file access copy targets preserve directory-relative paths outside the viewer root", () => {
  const targets = copyTargetsForFileAccessAsset({
    directoryRelativePath: "cad/source/robot_module.py",
  }, viewerServerInfo);

  assert.deepEqual(targets, {
    path: "/project/text-to-cad/cad/source/robot_module.py",
    relativePath: "cad/source/robot_module.py",
  });
});
