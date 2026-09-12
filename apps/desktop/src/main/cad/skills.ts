/**
 * The skills root every session is given (plan §8, as revised).
 *
 * Hardcore installs nothing into an agent's global configuration. It ships the
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
 * beside the `hardcore` MCP server's `list_skills` / `read_skill` tools which
 * read the same directory.
 *
 * Everything here is plain `node:fs` over paths passed in, so the materialiser
 * is testable without Electron (tests/unit/main/skills.test.ts). Main wires it
 * in `src/main/cad/index.ts`.
 */
import fs from "node:fs";
import path from "node:path";

/** Claude Code reads `<dir>/.claude/skills/<name>/SKILL.md` from an added directory. */
export const CLAUDE_LAYOUT = path.join(".claude", "skills");
/** codex-acp registers `<root>/.agents/skills` as an extra skill root. */
export const AGENTS_LAYOUT = path.join(".agents", "skills");
export const SKILL_LAYOUTS = [CLAUDE_LAYOUT, AGENTS_LAYOUT] as const;

/** Written last into a materialised root; its version is what a later launch compares. */
export const ROOT_MANIFEST = "hardcore-skills.json";

/** How the MCP server (`resources/hardcore-mcp/server.mjs`) is told where the root is. */
export const SKILLS_ROOT_ENV = "HARDCORE_SKILLS_ROOT";

export type SkillSummary = { name: string; description: string };

export type SkillsRoot = {
  /** The versioned directory, or null when no skills were composed into the app. */
  root: string | null;
  skills: SkillSummary[];
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

type Manifest = { version: string; skills: string[] };

function readManifest(root: string): Manifest | null {
  try {
    const parsed = JSON.parse(fs.readFileSync(path.join(root, ROOT_MANIFEST), "utf8")) as Partial<Manifest>;
    return typeof parsed.version === "string" && Array.isArray(parsed.skills)
      ? { version: parsed.version, skills: parsed.skills.filter((name): name is string => typeof name === "string") }
      : null;
  } catch {
    return null;
  }
}

/** Both layouts hold every named skill, with its SKILL.md. */
function complete(root: string, names: readonly string[]): boolean {
  return names.every((name) =>
    SKILL_LAYOUTS.every((layout) => fs.existsSync(path.join(root, layout, name, "SKILL.md"))),
  );
}

/**
 * Make `<base>/<version>/` hold the composed skills in both layouts, and
 * remove every other version under `base`.
 *
 * Idempotent: a root whose manifest records this version and this set of
 * skills, and whose files are all there, is left alone — so the common launch
 * copies nothing. A version bump, a changed skill set, or a half-written root
 * (the app was killed mid-copy) is rebuilt from scratch.
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

  const manifest = readManifest(root);
  const fresh =
    manifest?.version === version &&
    manifest.skills.length === names.length &&
    manifest.skills.every((name, index) => name === names[index]) &&
    complete(root, names);

  if (!fresh) {
    fs.rmSync(root, { recursive: true, force: true });
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
      `${JSON.stringify({ version, skills: names } satisfies Manifest, null, 2)}\n`,
    );
  }

  // Only this app's own versions: `base` is a directory the app owns.
  for (const entry of fs.readdirSync(base)) {
    if (entry !== version) {
      fs.rmSync(path.join(base, entry), { recursive: true, force: true });
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
    `You are running inside Hardcore, whose skills are at ${path.join(root, CLAUDE_LAYOUT)} —`,
    "a folder each, with a SKILL.md. Nothing loads them for you: read the one that fits the task",
    "before you start, with your file tools or the `hardcore` MCP server's `list_skills` and",
    "`read_skill`. Read cad/SKILL.md before any CAD, STEP, DXF, mesh or robot-description work, and",
    "hardcore-app-use/SKILL.md before showing the person a file — this app has its own tools for that.",
  ].join(" ");
  const list = skills.map((skill) => `- ${skill.name}: ${summarise(skill.description)}`).join("\n");
  return `${opening}\n\n${list}`;
}
