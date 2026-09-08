import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The app compiles the CAD Viewer's source, so the viewer's dependencies are
 * this app's build inputs. They are declared here (`file:` links to the two
 * sibling packages) rather than borrowed from a sibling's `node_modules`,
 * which is an accident of a developer's machine that a clean `npm ci` does not
 * reproduce — the shape of a build that passed locally and failed on CI.
 *
 * What this asserts: every package the linked siblings depend on resolves from
 * THIS app, at the version the sibling asked for. A peer added over there and
 * not installed here fails now, in a unit test, rather than in a bundler
 * message about an import nobody in this repository wrote.
 */
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");

function read(manifest: string): Record<string, unknown> {
  return JSON.parse(readFileSync(manifest, "utf8")) as Record<string, unknown>;
}

function dependenciesOf(manifest: string): Record<string, string> {
  return (read(manifest).dependencies ?? {}) as Record<string, string>;
}

/**
 * Enough of semver for the ranges these two manifests use: an exact version, a
 * caret, a tilde, or a `||` of those. A dependency is not worth pulling in to
 * compare four shapes of string, and a range this file cannot read is a
 * failure rather than a pass.
 */
function satisfies(version: string, range: string): boolean {
  return range.split("||").some((part) => matches(version, part.trim()));
}

function matches(version: string, range: string): boolean {
  const got = version.split(".").map(Number);
  const operator = range.startsWith("^") ? "^" : range.startsWith("~") ? "~" : "=";
  const want = range.replace(/^[\^~]/, "").split(".").map(Number);
  if (got.length !== 3 || want.length !== 3 || [...got, ...want].some(Number.isNaN)) {
    return false;
  }
  const atLeast =
    got[0]! > want[0]! ||
    (got[0] === want[0] && (got[1]! > want[1]! || (got[1] === want[1] && got[2]! >= want[2]!)));
  if (operator === "=") {
    return got.every((n, i) => n === want[i]);
  }
  if (operator === "~") {
    return atLeast && got[0] === want[0] && got[1] === want[1];
  }
  return atLeast && got[0] === want[0];
}

/** A `file:` range is a link to a sibling, not a version to match. */
function isLink(range: string): boolean {
  return range.startsWith("file:") || range.startsWith("link:");
}

const linked = {
  "cad-viewer": path.join(repoRoot, "apps", "viewer", "package.json"),
  "cadgen-js": path.join(repoRoot, "packages", "cadgen-js", "package.json"),
};

describe("the viewer's peers are this app's build inputs", () => {
  const own = read(path.join(appRoot, "package.json"));
  const declared = {
    ...((own.dependencies ?? {}) as Record<string, string>),
    ...((own.devDependencies ?? {}) as Record<string, string>),
  };

  it("declares both siblings as dependencies, by link", () => {
    for (const name of Object.keys(linked)) {
      expect(declared[name], `${name} is not declared here`).toBeDefined();
      expect(isLink(declared[name]!), `${name} must be a file: link`).toBe(true);
    }
  });

  for (const [sibling, manifest] of Object.entries(linked)) {
    describe(`${sibling}'s dependencies`, () => {
      for (const [name, range] of Object.entries(dependenciesOf(manifest))) {
        if (isLink(range) || name in linked) {
          continue;
        }
        it(`${name} resolves from this app`, () => {
          const installed = path.join(appRoot, "node_modules", name, "package.json");
          expect(
            () => readFileSync(installed, "utf8"),
            `${name} is a dependency of ${sibling} but is not installed here`,
          ).not.toThrow();
        });

        it(`${name} is a version ${sibling} asked for`, () => {
          const got = String(read(path.join(appRoot, "node_modules", name, "package.json")).version);
          expect(satisfies(got, range), `${name}: ${sibling} wants ${range}, this app has ${got}`).toBe(true);
        });

      }
    });
  }
});
