#!/usr/bin/env node
import { existsSync, readdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
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
  { path: "gemini-extension.json", fields: [["version"]] },
  { path: "plugin.json", fields: [["version"]] },
  { path: ".claude-plugin/marketplace.json", fields: [["version"]], pluginEntries: ["text-to-cad"] },
];

const tomlTargets = [
  "packages/cadgen/pyproject.toml",
];

// Skills pin CLI/bootstrap commands, and the cadgen an environment of one's own installs, to the
// same release. `cadgen run` gives a project's environment the engine's own cadgen; one a person
// made needs a cadgen compatible with the engine (protocol, document format, kernel line), not the
// same release.
function skillLaunchTargets() {
  const skills = path.join(repoRoot, "skills");
  if (!existsSync(skills)) {
    return [];
  }
  return readdirSync(skills, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    // Runtime setup has one dedicated guide; historical migration examples stay untouched.
    .flatMap((entry) => ["SKILL.md", "references/setup.md"].map((file) => `skills/${entry.name}/${file}`))
    .filter((relative) => existsSync(path.join(repoRoot, relative)))
    .filter((relative) => /cadgen(?:\[[a-z0-9_,.-]+\])?==|cadgen(?:\.cmd)? \+\d/.test(readFileSync(path.join(repoRoot, relative), "utf8")))
    .sort();
}

// Files that pin the cadgen runtime by a requirement string rather than a version field: the
// commands the agent apps run to start CAD's MCP server, the install page's Claude Desktop config
// and installer command, and every cadgen skill's install command and `cadgen +<version>`. A file
// may also be a JSON target (the Gemini extension carries both); its pin is stamped on top of that
// change, not over it.
export const pinTargets = [
  "codex.mcp.json",
  "claude.mcp.json",
  "cursor.mcp.json",
  "mcp.json",
  "gemini-extension.json",
  "docs/install.md",
  "packages/cadgen/README.md",
  // The turn-off command the privacy policy prints, the plugin's own launch line. The README and
  // the docs site's homepage pin nothing: a target without a pin is refused.
  "apps/docs/src/app/privacy-policy/page.tsx",
  ...skillLaunchTargets(),
];

// The one-line installer's scripts carry the release they were published with, which each installs
// when the version feed cannot be read. Neither is a pin target: each runs `cadgen==$version`, a
// variable a pin's stamp would overwrite.
export const bootstrapTargets = [
  { path: "scripts/install/install.sh", pattern: /^(CADGEN_VERSION=")([^"\n]*)(")$/m },
  { path: "scripts/install/install.ps1", pattern: /^([ \t]*\$CadgenVersion = ")([^"\n]*)(")$/m },
];

function usage() {
  console.log(`Usage:
  scripts/release/sync-version.mjs [--check]

Synchronizes duplicate package and plugin metadata versions from the canonical
VERSION file. Release preparation edits that file, then
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

// A skill runs its version by the `cadgen` command (`cadgen +0.8.0`), and says it in the
// command's refusal ("it says 0.8.0 is not installed").
export const skillVersionPattern = /(cadgen(?:\.cmd)? \+|it says )(\d[^\s`"'\\)]*)/g;

function syncPinTarget(relativePath, version, text = readRequiredText(relativePath)) {
  const pin = /(cadgen(?:\[[a-z0-9_,.-]+\])?==)([^"'`\s]+)/g;
  const matches = [...text.matchAll(pin)];
  const named = [...text.matchAll(skillVersionPattern)];
  if (matches.length === 0 && named.length === 0) {
    throw new Error(`${relativePath} must pin cadgen==<version> or cadgen +<version>`);
  }
  const labels = [];
  if (!matches.every((match) => match[2] === version)) {
    labels.push("cadgen pin");
  }
  if (!named.every((match) => match[2] === version)) {
    labels.push("cadgen +<version>");
  }
  if (labels.length === 0) {
    return null;
  }
  return {
    path: relativePath,
    labels,
    text: text
      .replace(pin, (_, prefix) => `${prefix}${version}`)
      .replace(skillVersionPattern, (_, prefix) => `${prefix}${version}`),
  };
}

function syncBootstrapTarget(target, version) {
  const text = readRequiredText(target.path);
  const matches = [...text.matchAll(new RegExp(target.pattern.source, "gm"))];
  if (matches.length !== 1) {
    throw new Error(`${target.path} must stamp exactly one fallback version (${target.pattern.source})`);
  }
  if (matches[0][2] === version) {
    return null;
  }
  return {
    path: target.path,
    labels: ["fallback version"],
    text: text.replace(target.pattern, (_, before, _stale, after) => `${before}${version}${after}`),
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
  for (const target of bootstrapTargets) {
    const change = syncBootstrapTarget(target, version);
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
