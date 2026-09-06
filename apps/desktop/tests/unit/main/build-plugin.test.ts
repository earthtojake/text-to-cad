import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

// The script is what `npm run build` runs; the test composes into a temporary
// directory from this repository, so what is asserted is what ships.
import { APP_SKILL, EXCLUDED_SKILLS, MARKETPLACE_NAME, PLUGIN_NAME, buildPlugin, planSkills } from "../../../scripts/build-plugin.mjs";

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

describe("the composed plugin", () => {
  it("is every repo skill but cad-viewer, plus hardcore-app", () => {
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

  it("lands as copies, with the three manifests renamed and versioned", () => {
    const out = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-plugin-out-"));
    temps.push(out);
    fs.writeFileSync(path.join(out, ".gitkeep"), "");
    fs.writeFileSync(path.join(out, "stale.txt"), "from a previous build");

    const result = buildPlugin({ repoRoot, out, version: "1.2.3", desktopRoot: appRoot });
    expect(result.version).toBe("1.2.3");

    const files = walk(out);
    // Copies, never symlinks: Codex drops links silently.
    expect(files.filter((file) => file.link)).toEqual([]);
    // A clean slate, keeping the placeholder git needs.
    expect(fs.existsSync(path.join(out, "stale.txt"))).toBe(false);
    expect(fs.existsSync(path.join(out, ".gitkeep"))).toBe(true);

    expect(fs.existsSync(path.join(out, "skills", "cad", "SKILL.md"))).toBe(true);
    expect(fs.existsSync(path.join(out, "skills", APP_SKILL, "SKILL.md"))).toBe(true);
    expect(fs.existsSync(path.join(out, "skills", "cad-viewer"))).toBe(false);
    // The cad skill's references travel with it.
    expect(fs.existsSync(path.join(out, "skills", "cad", "references"))).toBe(true);
    // Nothing a checkout leaves behind travels.
    expect(files.some((file) => /(^|\/)(node_modules|__pycache__|\.venv)(\/|$)/.test(file.path))).toBe(false);

    const claude = JSON.parse(fs.readFileSync(path.join(out, ".claude-plugin", "plugin.json"), "utf8"));
    expect(claude).toMatchObject({ name: PLUGIN_NAME, version: "1.2.3", skills: "./skills/" });
    const marketplace = JSON.parse(fs.readFileSync(path.join(out, ".claude-plugin", "marketplace.json"), "utf8"));
    expect(marketplace.name).toBe(MARKETPLACE_NAME);
    expect(marketplace.version).toBe("1.2.3");
    expect(marketplace.plugins).toHaveLength(1);
    expect(marketplace.plugins[0]).toMatchObject({ name: PLUGIN_NAME, source: "./", version: "1.2.3" });
    const codex = JSON.parse(fs.readFileSync(path.join(out, ".codex-plugin", "plugin.json"), "utf8"));
    expect(codex).toMatchObject({ name: PLUGIN_NAME, version: "1.2.3", skills: "./skills/" });

    const manifest = JSON.parse(fs.readFileSync(path.join(out, "hardcore-plugin.json"), "utf8"));
    expect(manifest).toMatchObject({ name: PLUGIN_NAME, marketplace: MARKETPLACE_NAME, version: "1.2.3" });
    expect(manifest.skills).toEqual(result.skills);
  });

  it("keeps the hardcore-app skill short and pointed at the tools", () => {
    const skill = fs.readFileSync(path.join(appRoot, "skills", APP_SKILL, "SKILL.md"), "utf8");
    expect(skill.split("\n").length).toBeLessThanOrEqual(120);
    expect(skill).toMatch(/^name: hardcore-app$/m);
    for (const tool of ["open_file", "reveal", "attach_snapshot", "list_open_tabs", "viewer_state", "open_url"]) {
      expect(skill).toContain(`\`${tool}`);
    }
    expect(skill).toContain("cadgen viewer");
    expect(skill).toContain("$cad-viewer");
  });
});
