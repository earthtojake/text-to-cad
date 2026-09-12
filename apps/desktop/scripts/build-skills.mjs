/**
 * Compose the app's skills into `resources/skills/` (plan §8, as revised).
 *
 * Hardcore ships the repository's skills and hands them to every session
 * itself — nothing is installed into an agent's global configuration. What
 * ships is every directory under `skills/` except `cad-viewer` (the viewer is
 * beside the chat in this app, so the skill that starts one and posts links
 * would be wrong here), plus `apps/desktop/skills/hardcore-app-use`, which
 * replaces the hand-off the `cad` skill makes to `$cad-viewer`. One skill per
 * directory, exactly as it is in the repository: no plugin manifest, no
 * marketplace, no version stamp — the version is the app's, and
 * `src/main/cad/skills.ts` records it where it materialises the root.
 *
 * Copies, never symlinks (`cpSync` with `dereference`, then a walk that fails
 * the build if a link survived): agent installers disagree about symlinks and
 * one drops them silently — repo AGENTS.md, and
 * `scripts/github-workflows/check-builds.sh`.
 *
 *   node scripts/build-skills.mjs                 # -> resources/skills
 *   node scripts/build-skills.mjs --out <dir> --repo <root>
 *
 * Runs as part of `npm run build` and of packaging (scripts/build.mjs); the
 * flags exist for the unit test, which composes into a temporary directory.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** The skill this app's viewer makes redundant. */
export const EXCLUDED_SKILLS = ["cad-viewer"];
/** The skill only this app ships. */
export const APP_SKILL = "hardcore-app-use";

/** Never copied out of a skill directory: caches, envs, scratch. */
const SKIP_ENTRIES = new Set(["node_modules", "__pycache__", ".venv", "tmp", ".DS_Store", ".pytest_cache"]);

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

/** Which skills the app carries: every repo skill but the excluded ones, plus the app's. */
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

export function buildSkills({ repoRoot, out, desktopRoot = appRoot }) {
  const skills = planSkills(repoRoot, desktopRoot);

  // A clean slate, keeping the placeholder that makes the directory exist in git.
  fs.mkdirSync(out, { recursive: true });
  for (const entry of fs.readdirSync(out)) {
    if (entry !== ".gitkeep") {
      fs.rmSync(path.join(out, entry), { recursive: true, force: true });
    }
  }

  for (const skill of skills) {
    copyTree(skill.from, path.join(out, skill.name));
  }

  const links = findSymlinks(out);
  if (links.length > 0) {
    throw new Error(`symlinks in the composed skills (some installers drop them silently):\n  ${links.join("\n  ")}`);
  }
  return { out, skills: skills.map((skill) => skill.name) };
}

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--out" || arg === "--repo") {
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
  const out = options.out ? path.resolve(options.out) : path.join(appRoot, "resources", "skills");
  const result = buildSkills({ repoRoot, out });
  console.info(`composed ${result.skills.length} skills -> ${result.out}`);
  console.info(`  ${result.skills.join(", ")}`);
}
