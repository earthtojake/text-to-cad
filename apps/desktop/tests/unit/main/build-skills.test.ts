import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

// The script is what `npm run build` runs; the test composes into a temporary
// directory from this repository, so what is asserted is what ships.
import { APP_SKILL, EXCLUDED_SKILLS, buildSkills, planSkills } from "../../../scripts/build-skills.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");

const temps: string[] = [];
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

function walk(root: string): Array<{ path: string; link: boolean }> {
  const out: Array<{ path: string; link: boolean }> = [];
  const visit = (directory: string) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      out.push({ path: path.relative(root, full), link: entry.isSymbolicLink() });
      if (entry.isDirectory() && !entry.isSymbolicLink()) {
        visit(full);
      }
    }
  };
  visit(root);
  return out;
}

describe("the composed skills", () => {
  it("is every repo skill but cad-viewer, plus hardcore-app-use", () => {
    const names = planSkills(repoRoot, appRoot).map((skill: { name: string }) => skill.name);
    const repoSkills = fs
      .readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
    expect(repoSkills).toContain("cad-viewer");
    expect(repoSkills).toContain("cad");
    for (const excluded of EXCLUDED_SKILLS) {
      expect(names).not.toContain(excluded);
    }
    expect(names).toContain("cad");
    expect(names.at(-1)).toBe(APP_SKILL);
    expect(new Set(names).size).toBe(names.length);
  });

  it("lands as copies, one directory per skill, with nothing else in it", () => {
    const out = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-skills-out-"));
    temps.push(out);
    fs.writeFileSync(path.join(out, ".gitkeep"), "");
    fs.writeFileSync(path.join(out, "stale.txt"), "from a previous build");

    const result = buildSkills({ repoRoot, out, desktopRoot: appRoot });

    const files = walk(out);
    // Copies, never symlinks: some installers drop links silently.
    expect(files.filter((file) => file.link)).toEqual([]);
    // A clean slate, keeping the placeholder git needs.
    expect(fs.existsSync(path.join(out, "stale.txt"))).toBe(false);
    expect(fs.existsSync(path.join(out, ".gitkeep"))).toBe(true);

    expect(fs.existsSync(path.join(out, "cad", "SKILL.md"))).toBe(true);
    expect(fs.existsSync(path.join(out, APP_SKILL, "SKILL.md"))).toBe(true);
    expect(fs.existsSync(path.join(out, "cad-viewer"))).toBe(false);
    // The cad skill's references travel with it.
    expect(fs.existsSync(path.join(out, "cad", "references"))).toBe(true);
    // Nothing a checkout leaves behind travels.
    expect(files.some((file) => /(^|\/)(node_modules|__pycache__|\.venv)(\/|$)/.test(file.path))).toBe(false);

    // No plugin manifest, no marketplace, no version stamp: the app hands
    // these directories to a session itself.
    const top = fs
      .readdirSync(out, { withFileTypes: true })
      .filter((entry) => entry.name !== ".gitkeep")
      .map((entry) => ({ name: entry.name, directory: entry.isDirectory() }));
    expect(top.every((entry) => entry.directory)).toBe(true);
    expect(top.map((entry) => entry.name).sort()).toEqual([...result.skills].sort());
  });

  it("keeps the hardcore-app-use skill short and pointed at the tools", () => {
    const skill = fs.readFileSync(path.join(appRoot, "skills", APP_SKILL, "SKILL.md"), "utf8");
    expect(skill.split("\n").length).toBeLessThanOrEqual(130);
    expect(skill).toMatch(/^name: hardcore-app-use$/m);
    for (const tool of ["open_file", "reveal", "attach_snapshot", "list_open_tabs", "viewer_state", "open_url"]) {
      expect(skill).toContain(`\`${tool}`);
    }
    expect(skill).toContain("cadgen viewer");
    expect(skill).toContain("$cad-viewer");
    // The runtime ships with the app and is already on the session's PATH.
    expect(skill).toMatch(/never install cadgen/i);
    // Nothing about a plugin: the app installs nothing into an agent.
    expect(skill.toLowerCase()).not.toContain("plugin");
  });
});
