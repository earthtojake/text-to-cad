import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  AGENTS_LAYOUT,
  CLAUDE_LAYOUT,
  ROOT_MANIFEST,
  composedSkills,
  materialiseSkillsRoot,
  skillFrontmatter,
  skillsPreamble,
} from "../../../src/main/cad/skills";

const temps: string[] = [];
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

function temp(prefix: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  temps.push(dir);
  return dir;
}

/** A composed `resources/skills`: one directory per skill, a SKILL.md in each. */
function source(skills: Record<string, string>): string {
  const dir = temp("hardcore-skills-source-");
  for (const [name, description] of Object.entries(skills)) {
    fs.mkdirSync(path.join(dir, name, "references"), { recursive: true });
    fs.writeFileSync(
      path.join(dir, name, "SKILL.md"),
      `---\nname: ${name}\ndescription: ${description}\n---\n\n# ${name}\n`,
    );
    fs.writeFileSync(path.join(dir, name, "references", "notes.md"), "detail\n");
  }
  return dir;
}

describe("SKILL.md front matter", () => {
  it("reads name and description, including a description folded over lines", () => {
    expect(
      skillFrontmatter("---\nname: cad\ndescription: Create parts.\n  And assemblies.\n---\nbody"),
    ).toEqual({ name: "cad", description: "Create parts. And assemblies." });
  });

  it("answers nulls for a file with no front matter", () => {
    expect(skillFrontmatter("# just a heading\n")).toEqual({ name: null, description: null });
  });

  it("takes the directory as the skill's name, whatever the front matter says", () => {
    const dir = temp("hardcore-skills-name-");
    fs.mkdirSync(path.join(dir, "cad"));
    fs.writeFileSync(path.join(dir, "cad", "SKILL.md"), "---\nname: something-else\ndescription: d\n---\n");
    expect(composedSkills(dir)).toEqual([{ name: "cad", description: "d" }]);
  });
});

describe("the skills root", () => {
  it("materialises both layouts under the app's version, with the whole skill", () => {
    const from = source({ cad: "Make CAD.", "hardcore-app-use": "Use this app." });
    const base = temp("hardcore-userdata-");

    const result = materialiseSkillsRoot({ source: from, base, version: "1.2.3" });

    expect(result.root).toBe(path.join(base, "1.2.3"));
    expect(result.skills).toEqual([
      { name: "cad", description: "Make CAD." },
      { name: "hardcore-app-use", description: "Use this app." },
    ]);
    for (const layout of [CLAUDE_LAYOUT, AGENTS_LAYOUT]) {
      expect(fs.existsSync(path.join(result.root!, layout, "cad", "SKILL.md"))).toBe(true);
      expect(fs.existsSync(path.join(result.root!, layout, "hardcore-app-use", "SKILL.md"))).toBe(true);
      // Not just the SKILL.md: a skill's references travel with it.
      expect(fs.readFileSync(path.join(result.root!, layout, "cad", "references", "notes.md"), "utf8")).toBe("detail\n");
    }
    // Real files, both times — not a link from one layout to the other.
    for (const layout of [CLAUDE_LAYOUT, AGENTS_LAYOUT]) {
      expect(fs.lstatSync(path.join(result.root!, layout, "cad")).isSymbolicLink()).toBe(false);
    }
    expect(JSON.parse(fs.readFileSync(path.join(result.root!, ROOT_MANIFEST), "utf8"))).toEqual({
      version: "1.2.3",
      skills: ["cad", "hardcore-app-use"],
    });
  });

  it("is idempotent: a second call with the same version copies nothing", () => {
    const from = source({ cad: "Make CAD." });
    const base = temp("hardcore-userdata-");

    const first = materialiseSkillsRoot({ source: from, base, version: "1.2.3" });
    const marker = path.join(first.root!, CLAUDE_LAYOUT, "cad", "SKILL.md");
    // A file only a copy would replace.
    fs.appendFileSync(marker, "\n<!-- kept -->\n");

    const second = materialiseSkillsRoot({ source: from, base, version: "1.2.3" });

    expect(second.root).toBe(first.root);
    expect(fs.readFileSync(marker, "utf8")).toContain("<!-- kept -->");
  });

  it("rebuilds when the composed set changed, and when the root is half written", () => {
    const base = temp("hardcore-userdata-");
    const one = materialiseSkillsRoot({ source: source({ cad: "Make CAD." }), base, version: "1.2.3" });
    const stamp = path.join(one.root!, CLAUDE_LAYOUT, "cad", "SKILL.md");
    fs.appendFileSync(stamp, "\n<!-- stale -->\n");

    const two = materialiseSkillsRoot({
      source: source({ cad: "Make CAD.", dxf: "Draw." }),
      base,
      version: "1.2.3",
    });
    expect(two.skills.map((skill) => skill.name)).toEqual(["cad", "dxf"]);
    expect(fs.readFileSync(stamp, "utf8")).not.toContain("<!-- stale -->");

    // A root whose manifest never got written (the app was killed mid-copy).
    fs.rmSync(path.join(two.root!, ROOT_MANIFEST));
    fs.appendFileSync(stamp, "\n<!-- also stale -->\n");
    const three = materialiseSkillsRoot({ source: source({ cad: "Make CAD.", dxf: "Draw." }), base, version: "1.2.3" });
    expect(fs.existsSync(path.join(three.root!, ROOT_MANIFEST))).toBe(true);
    expect(fs.readFileSync(stamp, "utf8")).not.toContain("<!-- also stale -->");
  });

  it("removes the roots of every other version", () => {
    const base = temp("hardcore-userdata-");
    fs.mkdirSync(path.join(base, "1.0.0", CLAUDE_LAYOUT, "cad"), { recursive: true });
    fs.mkdirSync(path.join(base, "1.1.0"), { recursive: true });

    const result = materialiseSkillsRoot({ source: source({ cad: "Make CAD." }), base, version: "1.2.3" });

    expect(fs.readdirSync(base)).toEqual(["1.2.3"]);
    expect(result.root).toBe(path.join(base, "1.2.3"));
  });

  it("answers no root when nothing was composed into the app", () => {
    const base = temp("hardcore-userdata-");
    const result = materialiseSkillsRoot({ source: path.join(base, "not-built"), base, version: "1.2.3" });
    expect(result).toEqual({ root: null, skills: [] });
    expect(fs.readdirSync(base)).toEqual([]);
  });
});

describe("the preamble", () => {
  const skills = [
    { name: "cad", description: "Create, modify, inspect and validate parametric CAD parts. Use for STEP." },
    { name: "hardcore-app-use", description: "How to work inside the Hardcore desktop app." },
  ];

  it("names the root, lists the skills, and says to read cad first", () => {
    const text = skillsPreamble("/data/skills/1.2.3", skills)!;
    expect(text).toContain(path.join("/data/skills/1.2.3", CLAUDE_LAYOUT));
    expect(text).toContain("- cad: Create, modify, inspect and validate parametric CAD parts.");
    expect(text).toContain("- hardcore-app-use: How to work inside the Hardcore desktop app.");
    expect(text).toMatch(/read cad\/SKILL\.md before any CAD/i);
    expect(text).toContain("list_skills");
  });

  it("stays short enough to sit in front of a prompt", () => {
    const many = Array.from({ length: 14 }, (_, index) => ({
      name: `skill-${index}`,
      description:
        "A very long description of the kind a real skill has, listing every trigger word it wants to match, " +
        "over several clauses, so that the cap is what decides the length rather than the author.",
    }));
    expect(skillsPreamble("/data/skills/1.2.3", many)!.length).toBeLessThan(1_500);
  });

  it("is nothing at all when there are no skills", () => {
    expect(skillsPreamble("/data/skills/1.2.3", [])).toBeNull();
  });
});
