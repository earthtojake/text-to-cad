/**
 * Compose the Hardcore plugin into `resources/plugin/` (plan §8).
 *
 * The plugin is the repository's `cad` plugin with one skill swapped: every
 * directory under `skills/` except `cad-viewer` (the viewer is beside the chat
 * in this app, so the skill that starts one and posts links would be wrong
 * here), plus `apps/desktop/skills/hardcore-app-use`, which replaces the hand-off
 * the `cad` skill makes to `$cad-viewer`. The three manifests mirror the
 * repository's — `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
 * `.codex-plugin/plugin.json` — with the plugin named `cad`, the marketplace
 * named `hardcore`, and the version set to the app's, so `cad@hardcore` in an
 * agent's plugin list is exactly "this app's skills at this app's version".
 *
 * Copies, never symlinks (`cpSync` with `dereference`, then a walk that fails
 * the build if a link survived): Codex's plugin installer drops symlinks
 * silently — repo AGENTS.md, and `scripts/github-workflows/check-builds.sh`.
 *
 *   node scripts/build-plugin.mjs                 # -> resources/plugin
 *   node scripts/build-plugin.mjs --out <dir> --repo <root> --version <v>
 *
 * Runs as part of `npm run build` and of packaging (scripts/build.mjs); the
 * flags exist for the unit test, which composes into a temporary directory.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** The skill this app's viewer makes redundant. */
export const EXCLUDED_SKILLS = ["cad-viewer"];
/** The skill only this app installs. */
export const APP_SKILL = "hardcore-app-use";
export const PLUGIN_NAME = "cad";
export const MARKETPLACE_NAME = "hardcore";

/** Never copied out of a skill directory: caches, envs, scratch. */
const SKIP_ENTRIES = new Set(["node_modules", "__pycache__", ".venv", "tmp", ".DS_Store", ".pytest_cache"]);

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function copyTree(from, to) {
  fs.cpSync(from, to, {
    recursive: true,
    dereference: true,
    filter: (source) => !SKIP_ENTRIES.has(path.basename(source)),
  });
}

/** Every symlink under `root`, for the assertion. */
function findSymlinks(root) {
  const links = [];
  const walk = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) {
        links.push(full);
      } else if (entry.isDirectory()) {
        walk(full);
      }
    }
  };
  walk(root);
  return links;
}

/** Which skills the plugin carries: every repo skill but the excluded ones, plus the app's. */
export function planSkills(repoRoot, desktopRoot = appRoot) {
  const repoSkills = path.join(repoRoot, "skills");
  const names = fs
    .readdirSync(repoSkills, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !EXCLUDED_SKILLS.includes(entry.name))
    .filter((entry) => fs.existsSync(path.join(repoSkills, entry.name, "SKILL.md")))
    .map((entry) => ({ name: entry.name, from: path.join(repoSkills, entry.name) }))
    .sort((a, b) => a.name.localeCompare(b.name));
  const appSkill = path.join(desktopRoot, "skills", APP_SKILL);
  if (!fs.existsSync(path.join(appSkill, "SKILL.md"))) {
    throw new Error(`missing ${appSkill}/SKILL.md`);
  }
  return [...names, { name: APP_SKILL, from: appSkill }];
}

export function buildPlugin({ repoRoot, out, version, desktopRoot = appRoot }) {
  const skills = planSkills(repoRoot, desktopRoot);

  // A clean slate, keeping the placeholder that makes the directory exist in git.
  fs.mkdirSync(out, { recursive: true });
  for (const entry of fs.readdirSync(out)) {
    if (entry !== ".gitkeep") {
      fs.rmSync(path.join(out, entry), { recursive: true, force: true });
    }
  }

  for (const skill of skills) {
    copyTree(skill.from, path.join(out, "skills", skill.name));
  }

  const claudePlugin = readJson(path.join(repoRoot, ".claude-plugin", "plugin.json"));
  const claudeMarketplace = readJson(path.join(repoRoot, ".claude-plugin", "marketplace.json"));
  const codexPlugin = readJson(path.join(repoRoot, ".codex-plugin", "plugin.json"));

  const description = "The Hardcore desktop app's CAD, robotics and fabrication skills, versioned with the app.";

  writeJson(path.join(out, ".claude-plugin", "plugin.json"), {
    ...claudePlugin,
    name: PLUGIN_NAME,
    version,
    description,
    skills: "./skills/",
  });

  const [template] = claudeMarketplace.plugins ?? [];
  writeJson(path.join(out, ".claude-plugin", "marketplace.json"), {
    ...claudeMarketplace,
    name: MARKETPLACE_NAME,
    interface: { displayName: "Hardcore" },
    metadata: { description },
    description,
    version,
    plugins: [
      {
        ...(template ?? {}),
        name: PLUGIN_NAME,
        source: "./",
        description,
        version,
      },
    ],
  });

  writeJson(path.join(out, ".codex-plugin", "plugin.json"), {
    ...codexPlugin,
    name: PLUGIN_NAME,
    version,
    description,
    skills: "./skills/",
    interface: {
      ...(codexPlugin.interface ?? {}),
      displayName: "Hardcore",
      shortDescription: description,
    },
  });

  // The record the app reads back: what was composed, at which version.
  writeJson(path.join(out, "hardcore-plugin.json"), {
    name: PLUGIN_NAME,
    marketplace: MARKETPLACE_NAME,
    version,
    skills: skills.map((skill) => skill.name),
  });

  const links = findSymlinks(out);
  if (links.length > 0) {
    throw new Error(`symlinks in the composed plugin (Codex drops them silently):\n  ${links.join("\n  ")}`);
  }
  return { out, version, skills: skills.map((skill) => skill.name) };
}

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--out" || arg === "--repo" || arg === "--version") {
      options[arg.slice(2)] = argv[index + 1];
      index += 1;
    } else {
      throw new Error(`unknown argument ${arg}`);
    }
  }
  return options;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const options = parseArgs(process.argv.slice(2));
  const repoRoot = options.repo ? path.resolve(options.repo) : path.resolve(appRoot, "..", "..");
  const out = options.out ? path.resolve(options.out) : path.join(appRoot, "resources", "plugin");
  const version = options.version ?? appVersion();
  const result = buildPlugin({ repoRoot, out, version });
  console.info(`composed plugin ${PLUGIN_NAME}@${MARKETPLACE_NAME} ${result.version} -> ${result.out}`);
  console.info(`  skills: ${result.skills.join(", ")}`);
}
