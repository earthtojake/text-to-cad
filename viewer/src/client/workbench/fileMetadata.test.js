import assert from "node:assert/strict";
import test from "node:test";

import {
  fileMetadataGroupsForEntry,
  formatFileMetadataBytes
} from "./fileMetadata.js";

function rowByLabel(groups, label) {
  for (const group of groups) {
    const row = group.rows.find((candidate) => candidate.label === label);
    if (row) {
      return row;
    }
  }
  return null;
}

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

test("file metadata groups summarize catalog entry fields", () => {
  const hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
  const groups = fileMetadataGroupsForEntry({
    file: "parts/example.step",
    kind: "part",
    url: "/models/parts/.example.step.glb?v=123",
    hash,
    bytes: 1536,
    headers: {
      "content-type": "model/step",
      etag: "\"012345\""
    },
    sourceKind: "step",
  }, {
    viewerServerInfo,
  });

  assert.deepEqual(groups.map((group) => group.title), ["File", "Headers", "Source"]);
  assert.equal(rowByLabel(groups, "Path").value, "parts/example.step");
  assert.equal(rowByLabel(groups, "Kind").value, "Part / STEP");
  assert.equal(rowByLabel(groups, "Size").value, "1.5 KB (1,536 B)");
  assert.equal(rowByLabel(groups, "Hash").displayValue, "0123456789ab...89abcdef");
  assert.equal(rowByLabel(groups, "Hash").copyValue, hash);
  assert.equal(rowByLabel(groups, "Asset").value, "parts/.example.step.glb");
  assert.equal(rowByLabel(groups, "Asset").title, "parts/.example.step.glb");
  assert.equal(rowByLabel(groups, "content-type").value, "model/step");
  assert.equal(rowByLabel(groups, "etag").value, "\"012345\"");
  assert.equal(rowByLabel(groups, "Kind").value, "Part / STEP");
});

test("file metadata hides Python source fields unless local opening is available", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "robots/tom/base_clamp.dxf",
    kind: "dxf",
    sourceKind: "python",
    source: {
      file: "models/robots/tom/base_clamp.py",
      sourcePath: "models/robots/tom/base_clamp.py",
      sourceHash: "7fe65652f2cea885534dc08b69b8ca69bc6d5677f007778e0fdd088428b3bd3e"
    }
  });

  assert.equal(rowByLabel(groups, "Python source"), null);
  assert.equal(rowByLabel(groups, "Source hash"), null);
});

test("file metadata downloads path and artifact rows when hosted file downloads are available", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "parts/example.step",
    kind: "part",
    url: "/models/parts/.example.step.glb?v=123",
    sourceKind: "python",
    source: {
      file: "parts/example.py",
      sourceHash: "7fe65652f2cea885534dc08b69b8ca69bc6d5677f007778e0fdd088428b3bd3e"
    }
  }, {
    includeFileDownloadActions: true,
    viewerServerInfo
  });

  const pathRow = rowByLabel(groups, "Path");
  const assetRow = rowByLabel(groups, "Asset");
  assert.equal(pathRow.action, "download");
  assert.equal(pathRow.href, "/__cad/download?file=parts%2Fexample.step&asset=output");
  assert.equal(pathRow.openUrl, "");
  assert.equal(pathRow.asset?.asset, "output");
  assert.equal(assetRow.action, "download");
  assert.equal(assetRow.value, "parts/.example.step.glb");
  assert.equal(assetRow.href, "/__cad/download?file=parts%2Fexample.step&asset=artifact");
  assert.equal(assetRow.openUrl, "");
  assert.equal(assetRow.asset?.asset, "artifact");
  assert.equal(rowByLabel(groups, "Python source"), null);
  assert.equal(rowByLabel(groups, "Source hash"), null);
});

test("file metadata uses direct Blob download URLs for hosted catalogs", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "parts/example.step",
    kind: "part",
    url: "https://blob.example.test/models2/parts/.example.step.glb",
    sourceKind: "step",
    step: {
      url: "https://blob.example.test/models2/parts/example.step",
    },
  }, {
    includeFileDownloadActions: true,
    viewerServerInfo: hostedViewerServerInfo
  });

  const pathRow = rowByLabel(groups, "Path");
  const assetRow = rowByLabel(groups, "Asset");
  assert.equal(pathRow.href, "https://blob.example.test/models2/parts/example.step");
  assert.equal(assetRow.href, "https://blob.example.test/models2/parts/.example.step.glb");
});

test("file metadata opens path and artifact rows when local opening is available", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "parts/example.step",
    kind: "part",
    url: "/models/parts/.example.step.glb?v=123",
  }, {
    includeFileOpenActions: true,
    viewerServerInfo
  });

  const pathRow = rowByLabel(groups, "Path");
  const assetRow = rowByLabel(groups, "Asset");
  assert.equal(pathRow.action, "open");
  assert.equal(pathRow.openUrl, "/__cad/reveal?file=parts%2Fexample.step&asset=output");
  assert.equal(pathRow.asset?.asset, "output");
  assert.equal(assetRow.action, "open");
  assert.equal(assetRow.value, "parts/.example.step.glb");
  assert.equal(assetRow.openUrl, "/__cad/reveal?file=parts%2Fexample.step&asset=artifact");
  assert.equal(assetRow.asset?.asset, "artifact");
});

test("file metadata includes a local open action for Python-generated files", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "robots/tom/base_clamp.dxf",
    kind: "dxf",
    url: "/models/robots/tom/base_clamp.dxf?v=abc",
    hash: "dxfhash",
    bytes: 39076,
    sourceKind: "python",
    source: {
      file: "models/robots/tom/base_clamp.py",
      sourcePath: "models/robots/tom/base_clamp.py",
      sourceHash: "7fe65652f2cea885534dc08b69b8ca69bc6d5677f007778e0fdd088428b3bd3e"
    }
  }, {
    includeFileOpenActions: true,
    includePythonSource: true,
    viewerServerInfo
  });

  const sourceRow = rowByLabel(groups, "Python source");
  assert.equal(sourceRow.value, "robots/tom/base_clamp.py");
  assert.equal(sourceRow.href, "");
  assert.equal(sourceRow.action, "open");
  assert.equal(sourceRow.openUrl, "/__cad/reveal?file=robots%2Ftom%2Fbase_clamp.dxf&asset=source");
  assert.equal(sourceRow.asset?.asset, "source");
  assert.equal(rowByLabel(groups, "Source hash").displayValue, "7fe65652f2ce...28b3bd3e");
  assert.equal(rowByLabel(groups, "Source hash").copyValue, "7fe65652f2cea885534dc08b69b8ca69bc6d5677f007778e0fdd088428b3bd3e");
});

test("file metadata lists module and relation catalog data", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "robots/example.srdf",
    kind: "srdf",
    url: "/models/robots/example.srdf?v=1",
    hash: "srdfhash",
    bytes: 1933,
    moduleUrl: "/models/robots/.example.step.js?v=1",
    relations: {
      urdf: {
        file: "robots/example.urdf",
        hash: "89d28a294dc54630a7933b612ada74e40df564bb059a9bb7cf2b6d41ae8c14a3",
        bytes: 9414
      }
    }
  }, {
    viewerServerInfo,
  });

  assert.equal(rowByLabel(groups, "Module").value, "robots/.example.step.js");
  assert.equal(rowByLabel(groups, "Module").href, "/models/robots/.example.step.js?v=1");
  assert.equal(rowByLabel(groups, "URDF file").value, "robots/example.urdf");
  assert.equal(rowByLabel(groups, "URDF size").value, "9.19 KB (9,414 B)");
  assert.equal(rowByLabel(groups, "URDF hash").displayValue, "89d28a294dc5...ae8c14a3");
  assert.equal(rowByLabel(groups, "URDF hash").copyValue, "89d28a294dc54630a7933b612ada74e40df564bb059a9bb7cf2b6d41ae8c14a3");
});

test("file metadata can suppress dynamic source and artifact status while generating", () => {
  const groups = fileMetadataGroupsForEntry({
    file: "parts/example.step",
    kind: "part",
    url: "/models/parts/.example.step.glb?v=123",
    sourceKind: "python",
    sourceStatus: {
      status: "stale",
      currentHash: "new-hash"
    },
    artifact: {
      error: "stale_step_artifact",
      artifactHash: "old-hash",
      currentHash: "new-hash",
      message: "Generated GLB doesn't match the hash of the STEP file."
    }
  }, {
    includePythonSource: true,
    suppressDynamicStatus: true
  });

  assert.equal(rowByLabel(groups, "Status"), null);
  assert.equal(rowByLabel(groups, "Current"), null);
  assert.equal(rowByLabel(groups, "Artifact"), null);
  assert.equal(rowByLabel(groups, "Artifact hash"), null);
  assert.equal(rowByLabel(groups, "Message"), null);
});

test("file metadata byte formatting handles empty and raw byte values", () => {
  assert.equal(formatFileMetadataBytes(-1), "");
  assert.equal(formatFileMetadataBytes(""), "0 B");
  assert.equal(formatFileMetadataBytes(42), "42 B");
  assert.equal(formatFileMetadataBytes(1048576), "1 MB (1,048,576 B)");
});
