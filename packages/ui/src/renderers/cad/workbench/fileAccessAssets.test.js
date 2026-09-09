import assert from "node:assert/strict";
import test from "node:test";

import {
  copyTargetsForFileAccessAsset,
  fileAccessAssetHasDeepLink,
  fileAccessAssetsForEntry,
  viewerDeepLinkForFileAccessAsset
} from "./fileAccessAssets.js";

const viewerServerInfo = {
  rootPath: "/project/text-to-cad/models",
};

test("file access assets always include output filename", () => {
  const assets = fileAccessAssetsForEntry({
    file: "assemblies/robot-arm/robot-arm.step",
  });

  assert.deepEqual(assets.output, {
    asset: "output",
    fileRef: "assemblies/robot-arm/robot-arm.step",
    filename: "robot-arm.step",
    label: "robot-arm.step",
    rootRelativePath: "assemblies/robot-arm/robot-arm.step",
  });
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

test("file access assets are ARTIFACTS ONLY -- there is never a third source asset", () => {
  // A model script is not a file the viewer offers: scripts live in `src/`, not
  // beside their output, and the viewer never presents an artifact under a
  // generator's name. The asset set is the same two entries for every file.
  const step = fileAccessAssetsForEntry({ file: "generated/robot.step" });
  assert.equal(step.source, undefined);
  assert.deepEqual(Object.keys(step).sort(), ["artifact", "output"]);
  assert.equal(step.output.filename, "robot.step");

  const urdf = fileAccessAssetsForEntry({ file: "robots/tom/tom.urdf", kind: "urdf" });
  assert.equal(urdf.source, undefined);
  assert.equal(urdf.output.filename, "tom.urdf");
  assert.equal(urdf.output.rootRelativePath, "robots/tom/tom.urdf");
});

test("file access copy targets include absolute and root-relative local paths", () => {
  const targets = copyTargetsForFileAccessAsset({
    rootRelativePath: "assemblies/robot-arm/robot-arm.step",
  }, {
    rootPath: "/project/text-to-cad/models",
  });

  assert.deepEqual(targets, {
    path: "/project/text-to-cad/models/assemblies/robot-arm/robot-arm.step",
    filename: "robot-arm.step",
    relativePath: "assemblies/robot-arm/robot-arm.step",
  });
});

test("copy targets resolve the asset's root-relative path against the served root", () => {
  // This used to resolve against a SECOND root (the repo root, one level above the
  // served directory), which is how a path outside the served root still got an
  // absolute form. There is one root now, so a relative path is relative to it.
  const targets = copyTargetsForFileAccessAsset({
    rootRelativePath: "cad/drawings/gasket_plate.dxf",
  }, viewerServerInfo);

  assert.deepEqual(targets, {
    path: "/project/text-to-cad/models/cad/drawings/gasket_plate.dxf",
    filename: "gasket_plate.dxf",
    relativePath: "cad/drawings/gasket_plate.dxf",
  });
});

test("copy targets take the filename the asset already carries", () => {
  // An artifact asset's display filename can differ from the basename of the path it
  // resolves to (a package artifact resolves to its own file), so the asset wins.
  const targets = copyTargetsForFileAccessAsset({
    filename: ".robot-arm.step.glb",
    rootRelativePath: "assemblies/robot-arm/.robot-arm.step.glb",
  }, viewerServerInfo);

  assert.equal(targets.filename, ".robot-arm.step.glb");
});

test("copy targets fall back to the path basename when the asset has no filename", () => {
  const targets = copyTargetsForFileAccessAsset({
    rootRelativePath: "cad/assemblies/robot-arm.step",
  }, viewerServerInfo);

  assert.equal(targets.filename, "robot-arm.step");
});

test("viewer deep link is the app-navigated URL for the entry", () => {
  // writeCadParam serializes `?file=` through URLSearchParams, which encodes the
  // path separators, so the copied link must carry the same `%2F` form — a copied
  // link and an app-navigated link are byte-identical for the same entry.
  const assets = fileAccessAssetsForEntry({
    file: "examples/STEP/planetary_gear_assembly.step",
  }, { viewerServerInfo });

  const link = viewerDeepLinkForFileAccessAsset(assets.output, viewerServerInfo, {
    origin: "http://127.0.0.1:3434",
  });

  assert.equal(link, "http://127.0.0.1:3434/?file=examples%2FSTEP%2Fplanetary_gear_assembly.step");
});

test("viewer deep link re-bases an absolute catalog path against the served root", () => {
  const assets = fileAccessAssetsForEntry({
    file: "/project/text-to-cad/models/cad/drawings/gasket_plate.dxf",
  }, { viewerServerInfo });

  const link = viewerDeepLinkForFileAccessAsset(assets.output, viewerServerInfo, {
    origin: "http://127.0.0.1:3434",
  });

  assert.equal(link, "http://127.0.0.1:3434/?file=cad%2Fdrawings%2Fgasket_plate.dxf");
});

test("viewer deep link encodes the file param exactly as URLSearchParams does", () => {
  // A space becomes `+` under URLSearchParams' form encoding — the same bytes the
  // address bar shows after the app itself selects the entry.
  const link = viewerDeepLinkForFileAccessAsset({
    rootRelativePath: "parts/bracket rev2.step",
  }, viewerServerInfo, { origin: "http://127.0.0.1:3434" });

  assert.equal(link, "http://127.0.0.1:3434/?file=parts%2Fbracket+rev2.step");
});

test("viewer deep link requires a root-relative ref and an origin", () => {
  assert.equal(fileAccessAssetHasDeepLink({ rootRelativePath: "cad/robot-arm.step" }), true);
  // No derivable ref: the menu hides Copy Link, and the builder returns nothing.
  assert.equal(fileAccessAssetHasDeepLink({ rootRelativePath: "" }), false);
  assert.equal(fileAccessAssetHasDeepLink(null), false);
  assert.equal(
    viewerDeepLinkForFileAccessAsset({ rootRelativePath: "" }, viewerServerInfo, {
      origin: "http://127.0.0.1:3434",
    }),
    ""
  );
  assert.equal(
    viewerDeepLinkForFileAccessAsset({ rootRelativePath: "cad/robot-arm.step" }, viewerServerInfo, {
      origin: "",
    }),
    ""
  );
});
