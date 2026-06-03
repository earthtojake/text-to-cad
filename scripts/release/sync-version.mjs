#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const canonicalVersionPath = "plugins/cad/VERSION";
const semverPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

const jsonTargets = [
  { path: "docs/package.json", fields: [["version"]] },
  { path: "docs/package-lock.json", fields: [["version"], ["packages", "", "version"]] },
  { path: "packages/cadjs/package.json", fields: [["version"]] },
  { path: "packages/cadjs/package-lock.json", fields: [["version"], ["packages", "", "version"]] },
  { path: "viewer/package.json", fields: [["version"]] },
  {
    path: "viewer/package-lock.json",
    fields: [
      ["version"],
      ["packages", "", "version"],
      ["packages", "packages/cadjs", "version"],
    ],
  },
  { path: "skills/cad-viewer/scripts/viewer/package.json", fields: [["version"]] },
  { path: "plugins/cad/skills/cad-viewer/scripts/viewer/package.json", fields: [["version"]] },
  { path: "plugins/cad/.claude-plugin/plugin.json", fields: [["version"]] },
  { path: "plugins/cad/.codex-plugin/plugin.json", fields: [["version"]] },
  { path: ".claude-plugin/marketplace.json", fields: [["version"]], pluginEntries: ["cad"] },
  { path: "viewer/packages/cadjs/package.json", fields: [["version"]], required: false },
  { path: "viewer/packages/cadjs/package-lock.json", fields: [["version"], ["packages", "", "version"]], required: false },
  { path: "skills/cad-viewer/scripts/viewer/packages/cadjs/package.json", fields: [["version"]], required: false },
  {
    path: "skills/cad-viewer/scripts/viewer/packages/cadjs/package-lock.json",
    fields: [["version"], ["packages", "", "version"]],
    required: false,
  },
  { path: "plugins/cad/skills/cad-viewer/scripts/viewer/packages/cadjs/package.json", fields: [["version"]], required: false },
  {
    path: "plugins/cad/skills/cad-viewer/scripts/viewer/packages/cadjs/package-lock.json",
    fields: [["version"], ["packages", "", "version"]],
    required: false,
  },
];

const tomlTargets = [
  "packages/cadpy/pyproject.toml",
  "packages/cadpy_metadata/pyproject.toml",
  "viewer/moveit2_server/pyproject.toml",
  "viewer/packages/cadpy/pyproject.toml",
  "skills/cad-viewer/scripts/viewer/moveit2_server/pyproject.toml",
  "skills/cad-viewer/scripts/viewer/packages/cadpy/pyproject.toml",
  "skills/cad/scripts/packages/cadpy/pyproject.toml",
  "skills/sdf/scripts/packages/cadpy_metadata/pyproject.toml",
  "skills/srdf/scripts/packages/cadpy_metadata/pyproject.toml",
  "skills/urdf/scripts/packages/cadpy_metadata/pyproject.toml",
  "plugins/cad/skills/cad/scripts/packages/cadpy/pyproject.toml",
  "plugins/cad/skills/cad-viewer/scripts/viewer/moveit2_server/pyproject.toml",
  "plugins/cad/skills/cad-viewer/scripts/viewer/packages/cadpy/pyproject.toml",
  "plugins/cad/skills/sdf/scripts/packages/cadpy_metadata/pyproject.toml",
  "plugins/cad/skills/srdf/scripts/packages/cadpy_metadata/pyproject.toml",
  "plugins/cad/skills/urdf/scripts/packages/cadpy_metadata/pyproject.toml",
];

function usage() {
  console.log(`Usage:
  scripts/release/sync-version.mjs [--check]

Synchronizes duplicate package and plugin metadata versions from
plugins/cad/VERSION. Release preparation edits the canonical VERSION file, then
stamps derived metadata from it; bundle and publish workflows re-check the same
metadata before production output is written.

Options:
  --check  Fail if derived version metadata is stale.
  -h, --help`);
}

function parseArgs(argv) {
  const options = { check: false };
  for (const arg of argv) {
    if (arg === "--check") {
      options.check = true;
    } else if (arg === "-h" || arg === "--help") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return options;
}

function repoPath(relativePath) {
  return path.join(repoRoot, relativePath);
}

function readRequiredText(relativePath) {
  return readFileSync(repoPath(relativePath), "utf8");
}

function readOptionalText(relativePath, required = true) {
  try {
    return readRequiredText(relativePath);
  } catch (error) {
    if (!required && error && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function canonicalVersion() {
  const version = readRequiredText(canonicalVersionPath).trim();
  if (!semverPattern.test(version)) {
    throw new Error(`${canonicalVersionPath} must contain a plain X.Y.Z semver version`);
  }
  return version;
}

function formatJsonPath(parts) {
  const labels = [];
  for (const part of parts) {
    if (part === "") {
      labels[labels.length - 1] = `${labels[labels.length - 1]}[""]`;
    } else {
      labels.push(part);
    }
  }
  return labels.join(".");
}

function syncJsonField(data, fieldPath, version, staleLabels) {
  let cursor = data;
  for (const key of fieldPath.slice(0, -1)) {
    if (!cursor || typeof cursor !== "object" || Array.isArray(cursor) || !(key in cursor)) {
      throw new Error(`missing JSON path: ${formatJsonPath(fieldPath)}`);
    }
    cursor = cursor[key];
  }
  const key = fieldPath[fieldPath.length - 1];
  if (!cursor || typeof cursor !== "object" || Array.isArray(cursor) || !(key in cursor)) {
    throw new Error(`missing JSON path: ${formatJsonPath(fieldPath)}`);
  }
  if (cursor[key] !== version) {
    cursor[key] = version;
    staleLabels.push(formatJsonPath(fieldPath));
  }
}

function syncPluginEntry(data, pluginName, version, staleLabels) {
  if (!Array.isArray(data.plugins)) {
    throw new Error("plugins must be an array");
  }
  const matches = data.plugins.filter((entry) => entry && typeof entry === "object" && entry.name === pluginName);
  if (matches.length !== 1) {
    throw new Error(`expected exactly one plugin entry named ${JSON.stringify(pluginName)}`);
  }
  if (matches[0].version !== version) {
    matches[0].version = version;
    staleLabels.push(`plugins[${pluginName}].version`);
  }
}

function syncJsonTarget(target, version) {
  const text = readOptionalText(target.path, target.required !== false);
  if (text === null) {
    return null;
  }
  const data = JSON.parse(text);
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error(`${target.path} must contain a JSON object`);
  }
  const staleLabels = [];
  for (const field of target.fields) {
    syncJsonField(data, field, version, staleLabels);
  }
  for (const pluginName of target.pluginEntries ?? []) {
    syncPluginEntry(data, pluginName, version, staleLabels);
  }
  if (staleLabels.length === 0) {
    return null;
  }
  return {
    path: target.path,
    labels: staleLabels,
    text: `${JSON.stringify(data, null, 2)}\n`,
  };
}

function syncTomlTarget(relativePath, version) {
  const text = readOptionalText(relativePath);
  if (text === null) {
    return null;
  }
  const matches = [...text.matchAll(/^(version\s*=\s*)"([^"]+)"/gm)];
  if (matches.length !== 1) {
    throw new Error(`${relativePath} must contain exactly one double-quoted version field`);
  }
  const match = matches[0];
  if (match[2] === version) {
    return null;
  }
  const start = match.index + match[1].length + 1;
  const end = start + match[2].length;
  return {
    path: relativePath,
    labels: ["version"],
    text: `${text.slice(0, start)}${version}${text.slice(end)}`,
  };
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const version = canonicalVersion();
  const changes = [];

  for (const target of jsonTargets) {
    const change = syncJsonTarget(target, version);
    if (change) {
      changes.push(change);
    }
  }
  for (const target of tomlTargets) {
    const change = syncTomlTarget(target, version);
    if (change) {
      changes.push(change);
    }
  }

  if (options.check) {
    if (changes.length > 0) {
      console.error(`Derived version metadata is stale for ${version}:`);
      for (const change of changes) {
        console.error(`- ${change.path} (${change.labels.join(", ")})`);
      }
      process.exit(1);
    }
    console.log(`Derived version metadata is synced from ${canonicalVersionPath}: ${version}`);
    return;
  }

  for (const change of changes) {
    writeFileSync(repoPath(change.path), change.text, "utf8");
  }
  if (changes.length === 0) {
    console.log(`Derived version metadata already synced from ${canonicalVersionPath}: ${version}`);
    return;
  }
  console.log(`Synced derived version metadata from ${canonicalVersionPath}: ${version}`);
  for (const change of changes) {
    console.log(`- ${change.path} (${change.labels.join(", ")})`);
  }
}

try {
  main();
} catch (error) {
  console.error(`error: ${error.message}`);
  process.exit(1);
}
