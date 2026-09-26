import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

// The script is what `npm run build` runs; the test composes into a temporary
// directory from this repository, so what is asserted is what ships.
import { APP_SKILLS, EXCLUDED_SKILLS, buildSkills, planSkills } from "../../../scripts/build-skills.mjs";

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
  it("composes repo authoring skills and registered domain skills with the app cad-viewer override", () => {
    const names = planSkills(repoRoot, appRoot).map((skill: { name: string }) => skill.name);
    const repoSkills = fs
      .readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
    expect(repoSkills).toContain("cad-viewer");
    expect(repoSkills).toContain("cad");
    const planned = planSkills(repoRoot, appRoot);
    for (const excluded of EXCLUDED_SKILLS) {
      expect(planned.some((skill: { from: string }) => skill.from === path.join(repoRoot, 'skills', excluded))).toBe(false);
    }
    for (const relative of APP_SKILLS) {
      expect(planned).toContainEqual({ name: path.basename(relative), from: path.join(appRoot, relative) });
    }
    expect(names).not.toContain('hardcore-app-use');
    expect(names).toContain("cad");
    expect(planned.find((skill: { name: string }) => skill.name === 'cad-viewer')?.from).toBe(path.join(appRoot, 'skills', 'cad-viewer'));
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
    for (const relative of APP_SKILLS) expect(fs.existsSync(path.join(out, path.basename(relative), 'SKILL.md'))).toBe(true);
    expect(fs.existsSync(path.join(out, 'hardcore-app-use'))).toBe(false);
    expect(fs.readFileSync(path.join(out, 'cad-viewer', 'SKILL.md'), 'utf8')).toBe(fs.readFileSync(path.join(appRoot, 'skills', 'cad-viewer', 'SKILL.md'), 'utf8'));
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

  it('gives each registered domain skill its declared identity and useful instructions', () => {
    for (const relative of APP_SKILLS) {
      const name = path.basename(relative);
      const skill = fs.readFileSync(path.join(appRoot, relative, 'SKILL.md'), 'utf8');
      const declared = /^name:\s*["']?([^"'\n]+)["']?$/m.exec(skill)?.[1]?.trim();
      expect(declared).toBe(name);
      expect(skill).toMatch(/^description:\s*\S/m);
      expect(skill).toMatch(/^#\s+\S/m);
    }
    const cad = fs.readFileSync(path.join(appRoot, 'skills', 'cad-viewer', 'SKILL.md'), 'utf8');
    for (const tool of ['viewer_state', 'select_reference', 'capture_view']) expect(cad).toContain(tool);
    expect(cad).toMatch(/never install cadgen/i);
  });
});
