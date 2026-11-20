#!/usr/bin/env node
import { readdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const canonicalVersionPath = "VERSION";
const semverPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

export const jsonTargets = [
  ...["package.json", "apps/docs/package.json", "packages/core/package.json", "packages/ui/package.json", "apps/web/package.json", "apps/mcp/package.json"].map(path => ({ path, fields: [["version"]] })),
  { path: "package-lock.json", fields: [["version"], ["packages", "", "version"], ...["apps/docs", "apps/web", "apps/mcp", "packages/core", "packages/ui"].map(name => ["packages", name, "version"])] },
  { path: ".claude-plugin/plugin.json", fields: [["version"]] },
  { path: ".codex-plugin/plugin.json", fields: [["version"]] },
  { path: ".cursor-plugin/plugin.json", fields: [["version"]] },
  { path: ".grok-plugin/plugin.json", fields: [["version"]] },
  { path: "gemini-extension.json", fields: [["version"]] },
  { path: ".antigravity-plugin/plugin.json", fields: [["version"]] },
  { path: ".kimi-plugin/plugin.json", fields: [["version"]] },
  { path: ".devin-plugin/plugin.json", fields: [["version"]] },
  { path: ".muse-plugin/plugin.json", fields: [["version"]] },
  { path: ".claude-plugin/marketplace.json", fields: [["version"]], pluginEntries: ["text-to-cad"] },
  { path: ".muse-plugin/marketplace.json", fields: [], pluginEntries: ["text-to-cad"] },
];

// The four projects released together: cad (the library, the server and the shim) and its three aliases.
export const tomlTargets = [
  "packages/cad/pyproject.toml",
  "packages/aliases/cad-server/pyproject.toml",
  "packages/aliases/cad-mcp/pyproject.toml",
  "packages/aliases/cadgen/pyproject.toml",
];

// The development environment's lock (uv.lock, beside the root pyproject.toml): it records the version of cad, the
// workspace's one member, and `uv sync --locked` refuses a lock whose cad is not the pyproject's. Its entry is
// stamped as the pyproject is, so a release needs no `uv lock` of its own.
export const lockTargets = [{ path: "uv.lock", name: "cad", source: "packages/cad" }];

// The release written into a file the release does not stamp by a version field: cad as a requirement
// (`cad==X`, with an extra or not: the aliases', each skill's setup block) or as uvx runs it (`cad@X`: Codex's
// server line). `cad` stands alone (`my-cad==` is another name, `text-to-cad@earthtojake` a plugin) and the
// version is three dotted numbers, so a pattern such as `Bash(... cad==*)`, `cad@latest`, or a number with no
// `cad==` or `cad@` before it (the setup block's fixed "older than 0.11.12") is never touched.
const releaseName = String.raw`\d+\.\d+\.\d+(?:[0-9A-Za-z.+_-]*[0-9A-Za-z])?`;
export const pinPattern = new RegExp(String.raw`(?<![\w.-])(cad(?:\[[a-z0-9_,.-]+\])?(?:==|@))(${releaseName})`, "g");

// Files that name the release that way: the aliases, which require cad at their own release, and the line
// Codex runs to start the CAD app's server (`cad@X mcp`). A file may also be a TOML target (those pyprojects);
// its pin is stamped on top of that change, not over it.
export const pinTargets = [
  "packages/aliases/cad-server/pyproject.toml",
  "packages/aliases/cad-mcp/pyproject.toml",
  "packages/aliases/cadgen/pyproject.toml",
  "codex.mcp.json",
];

// Each skill's setup block names the cad it was written for, `cad==X`; no command names a version. Every
// Markdown file under `skills/` is stamped in place by `pinPattern`, and one at least must name it
// (tests/python/global/test_skill_requirements.py holds the block).
export const skillsDir = "skills";

function skillDocuments(dir = skillsDir) {
  let entries;
  try {
    entries = readdirSync(repoPath(dir), { withFileTypes: true });
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return [];
    }
    throw error;
  }
  return entries
    .sort((a, b) => a.name.localeCompare(b.name))
    .flatMap((entry) => {
      const relative = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        return entry.name === "__pycache__" ? [] : skillDocuments(relative);
      }
      return entry.isFile() && entry.name.endsWith(".md") ? [relative] : [];
    });
}

function syncSkillTargets(version) {
  const documents = skillDocuments();
  const changes = [];
  let named = 0;
  for (const relativePath of documents) {
    const text = readRequiredText(relativePath);
    named += [...text.matchAll(new RegExp(pinPattern.source, "g"))].length;
    const stamped = text.replace(new RegExp(pinPattern.source, "g"), (_, prefix) => `${prefix}${version}`);
    if (stamped !== text) {
      changes.push({ path: relativePath, labels: ["the release the skill was written for"], text: stamped });
    }
  }
  if (documents.length > 0 && named === 0) {
    throw new Error(`no skill under ${skillsDir}/ names the release it was written for (cad==<version>)`);
  }
  return changes;
}

function usage() {
  console.log(`Usage:
  scripts/release/sync-version.mjs [--check]

Synchronizes duplicate package and plugin metadata versions from the canonical
VERSION file, and the release named as cad==<version> or cad@<version> (the aliases, Codex's server line, each
skill's setup block). Release preparation edits that file, then
stamps derived metadata from it; the bundle script and the Publish Release
workflow re-check the same metadata before production output is written.

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

function syncLockTarget(target, version) {
  const text = readRequiredText(target.path);
  const escape = (value) => value.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  const entry = new RegExp(
    String.raw`^(\[\[package\]\]\r?\nname = "${escape(target.name)}"\r?\nversion = ")([^"]+)("\r?\nsource = \{ editable = "${escape(target.source)}" \})`,
    "gm");
  const matches = [...text.matchAll(entry)];
  if (matches.length !== 1) {
    throw new Error(`${target.path} must hold exactly one entry for ${target.name}, editable from ${target.source}`);
  }
  if (matches[0][2] === version) {
    return null;
  }
  return {
    path: target.path,
    labels: [`${target.name} version`],
    text: text.replace(entry, (_, head, _old, tail) => `${head}${version}${tail}`),
  };
}

function syncPinTarget(relativePath, version, text = readRequiredText(relativePath)) {
  const pin = new RegExp(pinPattern.source, "g");
  const matches = [...text.matchAll(pin)];
  if (matches.length === 0) {
    throw new Error(`${relativePath} must name cad==<version> or cad@<version>`);
  }
  if (matches.every((match) => match[2] === version)) {
    return null;
  }
  return {
    path: relativePath,
    labels: ["release pin"],
    text: text.replace(pin, (_, prefix) => `${prefix}${version}`),
  };
}

/** Merge targets that are the SAME FILE into one, unioning their fields.
 *
 * The mirrored viewer/skill paths are symlinks to the canonical package in the development
 * layout, so several targets can name one file. Every target reads that file BEFORE any write
 * happens, so two of them stamping it means the last write wins -- and when the mirror declares
 * FEWER fields than the canonical target, the field only the canonical one knows about is
 * silently reverted. That is how the 0.4.10 release gate came to reject its own bump:
 * The former per-package lockfile was stamped with a package version and then
 * overwritten through its own symlink, which did not carry that field.
 */
export function mergeTargetsByRealPath(targets) {
  const merged = [];
  const byRealPath = new Map();
  const sameField = (a, b) => a.length === b.length && a.every((part, index) => part === b[index]);
  for (const target of targets) {
    let key = target.path;
    try {
      key = realpathSync(repoPath(target.path));
    } catch {
      // Absent: an optional mirror in a layout that does not have it. Keep it distinct and let
      // syncJsonTarget apply its own required/optional policy.
    }
    const existing = byRealPath.get(key);
    if (!existing) {
      const copy = { ...target, fields: target.fields.map((field) => [...field]) };
      byRealPath.set(key, copy);
      merged.push(copy);
      continue;
    }
    for (const field of target.fields) {
      if (!existing.fields.some((known) => sameField(known, field))) {
        existing.fields.push([...field]);
      }
    }
    if (target.pluginEntries?.length) {
      existing.pluginEntries = [...new Set([...(existing.pluginEntries ?? []), ...target.pluginEntries])];
    }
    // One required target makes the file required, however optional its mirrors are.
    if (target.required !== false) {
      existing.required = true;
    }
  }
  return merged;
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const version = canonicalVersion();
  const changes = [];

  for (const target of mergeTargetsByRealPath(jsonTargets)) {
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
  for (const target of lockTargets) {
    const change = syncLockTarget(target, version);
    if (change) {
      changes.push(change);
    }
  }
  for (const target of pinTargets) {
    const pending = changes.find((change) => change.path === target);
    const change = syncPinTarget(target, version, pending?.text);
    if (change && pending) {
      pending.text = change.text;
      pending.labels.push(...change.labels);
    } else if (change) {
      changes.push(change);
    }
  }

  changes.push(...syncSkillTargets(version));

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

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (error) {
    console.error(`error: ${error.message}`);
    process.exit(1);
  }
}
