#!/usr/bin/env node
import path from "node:path";
import process from "node:process";
import fs from "node:fs/promises";
import {
  buildCadProjectPackage,
  buildCadProjectPackageSummary,
  buildOttoAuthTaskPayload,
  normalizeOttoAuthBaseUrl,
} from "../lib/ottoAuth.js";
import {
  DEFAULT_EXPLORER_ROOT_DIR,
  scanCadDirectory,
} from "../lib/cadDirectoryScanner.mjs";
import {
  readOttoAuthLocalAgentCredential,
} from "../lib/ottoAuthLocalCredentials.mjs";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      continue;
    }
    const [rawKey, inlineValue] = token.slice(2).split("=", 2);
    const key = rawKey.replace(/-([a-z])/g, (_, char) => char.toUpperCase());
    if (inlineValue != null) {
      args[key] = inlineValue;
      continue;
    }
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
      continue;
    }
    args[key] = next;
    index += 1;
  }
  return args;
}

function usage() {
  return `Usage:
  npm --prefix .agents/skills/cad/explorer run ottoauth:buy-parts -- [options]

Options:
  --file <path>              Scan-root-relative CAD file to package.
  --root-dir <path>          CAD scan root, defaults to the current workspace.
  --asset-base-url <url>     Explorer URL that can serve CAD files, e.g. http://127.0.0.1:4178.
  --supplier <name>          Preferred supplier name.
  --supplier-url <url>       Preferred supplier URL.
  --material <text>          Material, process, or finish preference.
  --quantity <n>             Quantity, defaults to 1.
  --max-spend <usd>          Optional USD spend cap.
  --notes <text>             Extra instructions.
  --submit                   Submit to OttoAuth with a linked local agent credential.
  --base-url <url>           OttoAuth base URL, defaults to OTTOAUTH_BASE_URL or http://localhost:3000.
                             Credentials come from env or .agents/ottoauth.local.json.
`;
}

function findEntry(entries, file) {
  const normalized = String(file || "").replace(/\\/g, "/").replace(/^\/+/, "");
  if (!normalized) {
    return entries[0] || null;
  }
  return entries.find((entry) => (
    entry.file === normalized ||
    entry.source?.path === normalized ||
    entry.step?.path === normalized ||
    entry.name === normalized
  )) || null;
}

function contentTypeForCadFile(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".step" || extension === ".stp") return "model/step";
  if (extension === ".stl") return "model/stl";
  if (extension === ".3mf") return "model/3mf";
  if (extension === ".dxf") return "application/dxf";
  if (extension === ".urdf") return "application/xml";
  return "application/octet-stream";
}

function resolveCadFilePath(repoRoot, catalogRootDir, file) {
  const key = String(file?.key || "").replace(/\\/g, "/").replace(/^\/+/, "");
  if (!key) return "";
  return path.resolve(repoRoot, catalogRootDir || "", key);
}

async function uploadCadFilesToOttoAuth(baseUrl, cadPackage, workspaceRoot, credential, catalogRootDir) {
  const cadFiles = Array.isArray(cadPackage?.cadFiles) ? cadPackage.cadFiles : [];
  const uploadable = cadFiles
    .map((file) => ({
      file,
      filePath: resolveCadFilePath(workspaceRoot, catalogRootDir, file),
    }))
    .filter((item) => item.filePath);
  if (!uploadable.length) {
    return cadPackage;
  }

  const files = [];
  for (const item of uploadable) {
    const bytes = await fs.readFile(item.filePath);
    files.push({
      name: path.basename(item.filePath),
      content_type: contentTypeForCadFile(item.filePath),
      content_base64: bytes.toString("base64"),
      metadata: {
        source: "cad-explorer-cli",
        local_path: path.relative(workspaceRoot, item.filePath),
        label: item.file.label,
        key: item.file.key,
        format: item.file.format,
        selected: Boolean(item.file.selected),
      },
    });
  }

  const response = await fetch(`${baseUrl}/api/sdk/files`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify({
      username: credential.username,
      private_key: credential.privateKey,
      files,
    }),
  });
  const text = await response.text();
  let responsePayload = null;
  try {
    responsePayload = text ? JSON.parse(text) : null;
  } catch {
    responsePayload = { error: text };
  }
  if (!response.ok) {
    throw new Error(responsePayload?.error || `OttoAuth file upload failed with status ${response.status}.`);
  }

  const uploadedFiles = Array.isArray(responsePayload?.files) ? responsePayload.files : [];
  let uploadedIndex = 0;
  const uploadedCadFiles = cadFiles.map((file) => {
    const matched = uploadable.find((item) => item.file === file);
    if (!matched || uploadedIndex >= uploadedFiles.length) {
      return file;
    }
    const uploaded = uploadedFiles[uploadedIndex];
    uploadedIndex += 1;
    return {
      ...file,
      local_url: file.url,
      url: uploaded?.url || file.url,
      ottoauth_file_id: uploaded?.id || "",
      ottoauth_sha256: uploaded?.sha256 || "",
      size: uploaded?.size ?? file.size,
    };
  });
  const selectedFile = uploadedCadFiles.find((file) => file.selected) || uploadedCadFiles[0] || null;
  return {
    ...cadPackage,
    selectedFile,
    cadFiles: uploadedCadFiles,
    primarySourceUrl: selectedFile?.url || uploadedCadFiles.find((file) => file.url)?.url || cadPackage.primarySourceUrl || "",
  };
}

function readCredentialOrThrow(workspaceRoot) {
  const credential = readOttoAuthLocalAgentCredential({ workspaceRoot });
  if (!credential) {
    throw new Error(
      "No linked OttoAuth agent credential found. Sign in with Google from CAD Explorer Buy Parts Now first, or set OTTOAUTH_AGENT_USERNAME and OTTOAUTH_PRIVATE_KEY."
    );
  }
  return credential;
}

async function submitToOttoAuth(baseUrl, payload, workspaceRoot, credential) {
  const response = await fetch(`${baseUrl}/api/sdk/checkout`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify({
      ...payload,
      username: credential.username,
      private_key: credential.privateKey,
    }),
  });
  const text = await response.text();
  let responsePayload = null;
  try {
    responsePayload = text ? JSON.parse(text) : null;
  } catch {
    responsePayload = { error: text };
  }
  if (!response.ok) {
    throw new Error(responsePayload?.error || `OttoAuth submit failed with status ${response.status}.`);
  }
  return responsePayload;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || args.h) {
    console.log(usage());
    return;
  }

  const repoRoot = path.resolve(process.env.EXPLORER_WORKSPACE_ROOT || process.env.INIT_CWD || process.cwd());
  const rootDir = args.rootDir == null ? DEFAULT_EXPLORER_ROOT_DIR : String(args.rootDir);
  const catalog = scanCadDirectory({ repoRoot, rootDir });
  const selectedEntry = findEntry(catalog.entries, args.file);
  if (!selectedEntry) {
    throw new Error(args.file ? `No CAD entry matched ${args.file}.` : "No CAD entries found.");
  }

  const cadPackage = buildCadProjectPackage({
    entries: catalog.entries,
    selectedEntry,
    origin: args.assetBaseUrl || "",
    catalogRootDir: catalog.root?.dir || "",
  });
  const payload = buildOttoAuthTaskPayload({
    entry: selectedEntry,
    sourceUrl: cadPackage.primarySourceUrl,
    form: {
      quantity: args.quantity || "1",
      material: args.material || "",
      supplierName: args.supplier || "",
      supplierUrl: args.supplierUrl || "",
      maxSpendUsd: args.maxSpend || "",
      packageSummary: buildCadProjectPackageSummary(cadPackage),
      notes: args.notes || "",
      cadFiles: cadPackage.cadFiles,
      cadParts: cadPackage.parts,
    },
  });

  if (!args.submit) {
    console.log(JSON.stringify({
      ok: true,
      mode: "dry_run",
      payload,
    }, null, 2));
    return;
  }

  const baseUrl = normalizeOttoAuthBaseUrl(
    args.baseUrl || process.env.OTTOAUTH_BASE_URL || "http://localhost:3000"
  );
  const credential = readCredentialOrThrow(repoRoot);
  const uploadedPackage = await uploadCadFilesToOttoAuth(
    baseUrl,
    cadPackage,
    repoRoot,
    credential,
    catalog.root?.dir || ""
  );
  const uploadedPayload = buildOttoAuthTaskPayload({
    entry: selectedEntry,
    sourceUrl: uploadedPackage.primarySourceUrl,
    form: {
      quantity: args.quantity || "1",
      material: args.material || "",
      supplierName: args.supplier || "",
      supplierUrl: args.supplierUrl || "",
      maxSpendUsd: args.maxSpend || "",
      packageSummary: buildCadProjectPackageSummary(uploadedPackage),
      notes: args.notes || "",
      cadFiles: uploadedPackage.cadFiles,
      cadParts: uploadedPackage.parts,
    },
  });
  const result = await submitToOttoAuth(baseUrl, uploadedPayload, repoRoot, credential);
  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
