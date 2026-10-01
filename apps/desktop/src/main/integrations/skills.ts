/**
 * The skills root every session is given (plan §8, as revised).
 *
 * text-to-cad installs nothing into an agent's global configuration. It ships the
 * skills (`resources/skills/`, composed by `scripts/build-skills.mjs`),
 * materialises them once per app version under
 * `<userData>/skills/<appVersion>/`, and hands that one directory to every
 * `session/new` and `session/load` as an additional directory. Two ways an
 * agent finds them there, so the same root works for both:
 *
 *   <root>/.claude/skills/<skill>/SKILL.md    Claude Code's layout
 *   <root>/.agents/skills/<skill>/SKILL.md    Codex's layout
 *
 * Real copies of the same files, twice. Not symlinks: packaging and some
 * agents drop them (repo AGENTS.md), and a skill that loses half its files is
 * worse than a megabyte of duplication.
 *
 * Agents that ignore additional directories — Gemini, Copilot, OpenCode,
 * Goose, everything but Claude Code and Codex — get the root a second way:
 * `preamble()` names it, and its files in the first prompt of a session,
 * beside the `text-to-cad-workspace` MCP server's `list_skills` / `read_skill`
 * tools which read the same directory.
 *
 * Everything here is plain `node:fs` over paths passed in, so the materialiser
 * is testable without Electron (tests/unit/main/skills.test.ts). Main wires it
 * in `src/main/integrations/index.ts` (`materialiseSkills`).
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

/** Claude Code reads `<dir>/.claude/skills/<name>/SKILL.md` from an added directory. */
export const CLAUDE_LAYOUT = path.join(".claude", "skills");
/** codex-acp registers `<root>/.agents/skills` as an extra skill root. */
export const AGENTS_LAYOUT = path.join(".agents", "skills");
export const SKILL_LAYOUTS = [CLAUDE_LAYOUT, AGENTS_LAYOUT] as const;

/** Written last into a materialised root; its version is what a later launch compares. */
export const ROOT_MANIFEST = "text-to-cad-skills.json";

/** How the MCP server (`resources/text-to-cad-mcp/server.mjs`) is told where the root is. */
export const SKILLS_ROOT_ENV = "TEXT_TO_CAD_SKILLS_ROOT";
/** Carries the reason the root could not be made, so `list_skills` can say it. */
export const SKILLS_ERROR_ENV = "TEXT_TO_CAD_SKILLS_ERROR";

export type SkillSummary = { name: string; description: string };

export type SkillsRoot = {
  /** The versioned directory, or null when no skills were composed into the app. */
  root: string | null;
  skills: SkillSummary[];
  /** Why the root could not be made (a copy failed), else absent: "nothing composed" is no error. */
  error?: string | null;
};

export const EMPTY_SKILLS: SkillsRoot = { root: null, skills: [] };

/* -------------------------------------------------------------------------- */
/* Reading a skill                                                             */
/* -------------------------------------------------------------------------- */

/**
 * `name` and `description` out of a SKILL.md's YAML front matter. Deliberately
 * small: the two scalar keys every skill has, folded onto one line, and
 * nothing else — a YAML parser here would be a dependency for two fields.
 */
export function skillFrontmatter(text: string): { name: string | null; description: string | null } {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!match?.[1]) {
    return { name: null, description: null };
  }
  const fields: Record<string, string> = {};
  let key: string | null = null;
  for (const line of match[1].split(/\r?\n/)) {
    const start = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
    if (start?.[1]) {
      key = start[1];
      fields[key] = start[2] ?? "";
    } else if (key && /^\s+\S/.test(line)) {
      // A folded scalar's continuation lines.
      fields[key] = `${fields[key]} ${line.trim()}`.trim();
    } else {
      key = null;
    }
  }
  const unquote = (value: string | undefined) =>
    value ? value.replace(/^['"]|['"]$/g, "").trim() || null : null;
  return { name: unquote(fields.name), description: unquote(fields.description) };
}

/** Every directory under `source` that holds a SKILL.md, with its front matter. */
export function composedSkills(source: string): SkillSummary[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(source, { withFileTypes: true });
  } catch {
    return [];
  }
  const skills: SkillSummary[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const file = path.join(source, entry.name, "SKILL.md");
    if (!fs.existsSync(file)) {
      continue;
    }
    // The directory is the skill's identity — it is what an agent loads it by
    // and what is copied — so the front matter is read for the description only.
    const front = skillFrontmatter(fs.readFileSync(file, "utf8"));
    skills.push({ name: entry.name, description: front.description ?? "" });
  }
  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

/* -------------------------------------------------------------------------- */
/* Materialising                                                               */
/* -------------------------------------------------------------------------- */

type Manifest = { version: string; skills: string[]; hash: string };

function readManifest(root: string): Manifest | null {
  try {
    const parsed = JSON.parse(fs.readFileSync(path.join(root, ROOT_MANIFEST), "utf8")) as Partial<Manifest>;
    return typeof parsed.version === "string" && Array.isArray(parsed.skills) && typeof parsed.hash === "string"
      ? {
          version: parsed.version,
          skills: parsed.skills.filter((name): name is string => typeof name === "string"),
          hash: parsed.hash,
        }
      : null;
  } catch {
    return null;
  }
}

/**
 * One SHA-256 over every file of the named skills under `dir`: relative path
 * and bytes, in a fixed order, following links the way the copy does. Taken of
 * the source and of each layout of the root, so an edited SKILL.md — in the
 * app's resources (a dev build keeps one version) or in the materialised copy
 * (an agent that got past the read-only modes) — is a mismatch. The skills are
 * under a megabyte, so this costs a few milliseconds per launch.
 */
function treeHash(dir: string, names: readonly string[]): string | null {
  const hash = createHash("sha256");
  const walk = (relative: string): void => {
    const absolute = path.join(dir, relative);
    const stat = fs.statSync(absolute);
    if (stat.isDirectory()) {
      for (const entry of fs.readdirSync(absolute).sort()) {
        walk(path.join(relative, entry));
      }
    } else if (stat.isFile()) {
      hash.update(`${relative.split(path.sep).join("/")}\0${stat.size}\0`);
      hash.update(fs.readFileSync(absolute));
    } else {
      // A FIFO, socket or device is never ours; naming it makes it a mismatch.
      hash.update(`${relative.split(path.sep).join("/")}\0other\0`);
    }
  };
  try {
    for (const name of names) {
      walk(name);
    }
  } catch {
    return null;
  }
  return hash.digest("hex");
}

/**
 * Whether `dir` holds exactly `names` and nothing else. `treeHash` reads only
 * the entries it is given, so without this a skill an agent planted beside
 * ours — `<root>/.claude/skills/<its own>/SKILL.md` — would hash clean, survive
 * every launch, and be loaded by every later session of every agent.
 */
function holdsExactly(dir: string, names: readonly string[]): boolean {
  try {
    const entries = fs.readdirSync(dir).sort();
    const expected = [...names].sort();
    return entries.length === expected.length && entries.every((entry, index) => entry === expected[index]);
  } catch {
    return false;
  }
}

/**
 * Make every FILE under `dir` read-only (0444, execute bits kept), so an
 * agent's — or an injected prompt's — plain write to a SKILL.md fails.
 * Directories stay writable (0755): a read-only directory makes a recursive
 * `rm` of the app's data fail with ENOTEMPTY (the e2e suite's cleanup, CI, a
 * person deleting their app data). An agent can therefore still unlink and
 * replace a file; the defence against that is `treeHash`, which rebuilds any
 * copy that differs from the source on every launch.
 */
function lockFiles(dir: string): void {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      lockFiles(full);
    } else if (entry.isFile()) {
      fs.chmodSync(full, fs.statSync(full).mode & 0o7555);
    }
  }
}

/**
 * Remove a root. Roots written by an earlier build had 0555 directories,
 * which `rmSync` cannot empty, so directories are made writable first.
 */
function removeTree(dir: string): void {
  const writable = (current: string): void => {
    let stat: fs.Stats;
    try {
      stat = fs.lstatSync(current);
    } catch {
      return;
    }
    if (!stat.isDirectory()) {
      return;
    }
    try {
      fs.chmodSync(current, stat.mode | 0o700);
    } catch {
      // Not ours to change; the removal will say so.
    }
    for (const entry of fs.readdirSync(current)) {
      writable(path.join(current, entry));
    }
  };
  writable(dir);
  fs.rmSync(dir, { recursive: true, force: true });
}

/**
 * Make `<base>/<version>/` hold the composed skills in both layouts, and
 * remove every other version under `base`.
 *
 * Idempotent: a root whose manifest records this version, this set of skills
 * and the source's content hash, and whose two layouts still hash to it, is
 * left alone — so the common launch copies nothing. A version bump, a changed
 * skill set, changed skill content (dev builds keep one version while
 * SKILL.md files are edited), an edited copy, anything in the root that is
 * not ours (a skill an agent planted beside them), or a half-written root (the
 * app was killed mid-copy) is rebuilt from scratch. Its files are then made
 * read-only (see `lockFiles`).
 */
export function materialiseSkillsRoot(options: {
  /** `resources/skills` — one directory per skill. */
  source: string;
  /** `<userData>/skills` — one directory per app version. */
  base: string;
  version: string;
}): SkillsRoot {
  const { source, base, version } = options;
  const skills = composedSkills(source);
  if (skills.length === 0) {
    return EMPTY_SKILLS;
  }
  const names = skills.map((skill) => skill.name);
  const root = path.join(base, version);
  const hash = treeHash(source, names);
  if (!hash) {
    throw new Error(`could not read the composed skills in ${source}`);
  }

  const manifest = readManifest(root);
  const fresh =
    manifest?.version === version &&
    manifest.hash === hash &&
    manifest.skills.length === names.length &&
    manifest.skills.every((name, index) => name === names[index]) &&
    holdsExactly(root, [ROOT_MANIFEST, ...SKILL_LAYOUTS.map((layout) => layout.split(path.sep)[0]!)]) &&
    SKILL_LAYOUTS.every(
      (layout) =>
        holdsExactly(path.join(root, path.dirname(layout)), [path.basename(layout)]) &&
        holdsExactly(path.join(root, layout), names) &&
        treeHash(path.join(root, layout), names) === hash,
    );

  if (!fresh) {
    removeTree(root);
    for (const layout of SKILL_LAYOUTS) {
      const target = path.join(root, layout);
      fs.mkdirSync(target, { recursive: true });
      for (const name of names) {
        fs.cpSync(path.join(source, name), path.join(target, name), { recursive: true, dereference: true });
      }
    }
    // Last, so a root that exists without it is rebuilt rather than trusted.
    fs.writeFileSync(
      path.join(root, ROOT_MANIFEST),
      `${JSON.stringify({ version, skills: names, hash } satisfies Manifest, null, 2)}\n`,
    );
    lockFiles(root);
  }

  // Only this app's own versions: `base` is a directory the app owns.
  for (const entry of fs.readdirSync(base)) {
    if (entry !== version) {
      removeTree(path.join(base, entry));
    }
  }

  return { root, skills };
}

/* -------------------------------------------------------------------------- */
/* The preamble                                                                */
/* -------------------------------------------------------------------------- */

/** How much of a skill's description the preamble carries. */
const SUMMARY_CHARS = 60;

function summarise(description: string): string {
  const sentence = description.split(/(?<=\.)\s/)[0] ?? description;
  const collapsed = sentence.replace(/\s+/g, " ").trim();
  return collapsed.length > SUMMARY_CHARS
    ? `${collapsed.slice(0, SUMMARY_CHARS - 1).trimEnd()}…`
    : collapsed;
}

/**
 * The text block that goes in front of the first prompt of a session, for an
 * agent that does not load an additional directory's skills by itself
 * (`skillRoots: "preamble"` in the registry). One paragraph: where the skills
 * are, what they are, and which one to read before CAD work. It is sent once —
 * the transcript keeps it — and never on a resumed session.
 */
export function skillsPreamble(root: string, skills: readonly SkillSummary[]): string | null {
  if (skills.length === 0) {
    return null;
  }
  const opening = [
    `You are running inside text-to-cad. Additional skills are at ${path.join(root, CLAUDE_LAYOUT)}.`,
    "Read the skill that fits the task using file tools or the workspace MCP list_skills/read_skill tools.",
    "Workspace tools open resources in the app; domain integrations operate on their contents.",
    "Tabs belong to this workspace. Add to prompt captures context without submitting it.",
  ].join(" ");
  const list = skills.map((skill) => `- ${skill.name}: ${summarise(skill.description)}`).join("\n");
  return `${opening}\n\n${list}`;
}
