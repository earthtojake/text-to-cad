import { readFileSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const repoRoot = path.resolve(appRoot, "../..");
const appRequire = createRequire(path.join(appRoot, "package.json"));
const uiRequire = createRequire(path.join(repoRoot, "packages/ui/package.json"));
const coreRequire = createRequire(path.join(repoRoot, "packages/core/package.json"));

/** Installed workspaces must share React contexts and Three.js object identities. */
describe("shared package installation", () => {
  it("declares shared packages without a dependency on another app", () => {
    const app = JSON.parse(readFileSync(path.join(appRoot, "package.json"), "utf8"));
    const dependencies = { ...app.dependencies, ...app.devDependencies };
    expect(dependencies["@hardcore/core"]).toBe("*");
    expect(dependencies["@hardcore/ui"]).toBe("*");
    expect(dependencies["cad-viewer"]).toBeUndefined();
    expect(dependencies["@hardcore/web"]).toBeUndefined();
  });

  for (const peer of ["react", "react-dom", "three", "radix-ui"]) {
    it(`shares ${peer} with the UI package`, () => {
      expect(realpathSync(uiRequire.resolve(peer))).toBe(realpathSync(appRequire.resolve(peer)));
    });
  }
  it("shares Three.js with core", () => {
    expect(realpathSync(coreRequire.resolve("three"))).toBe(realpathSync(appRequire.resolve("three")));
  });
  it("exports compiled FileViewer modules and package-owned declarations", () => {
    const ui = JSON.parse(readFileSync(path.join(repoRoot, "packages/ui/package.json"), "utf8"));
    for (const entry of ["./file-viewer", "./navigation", "./renderers/cad", "./renderers/code/editor"]) {
      const target = ui.exports[entry] || { import: `./dist/${entry.slice(2)}/index.js`, types: `./dist/${entry.slice(2)}/index.d.ts` };
      expect(readFileSync(path.join(repoRoot, "packages/ui", target.import), "utf8")).not.toMatch(/@renderer\/|apps\/web|apps\/viewer/);
      expect(readFileSync(path.join(repoRoot, "packages/ui", target.types), "utf8")).toBeTruthy();
    }
  });
});
