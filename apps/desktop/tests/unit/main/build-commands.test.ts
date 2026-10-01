import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { electronViteBuild } from "../../../scripts/build.mjs";
import { electronBuilder } from "../../../scripts/package.mjs";

/**
 * How the build scripts start the build tools. On Windows `npx` and every
 * `node_modules/.bin` entry is a `.cmd` shim, which Node (18.20.2, 20.12.2,
 * 22+) refuses to spawn without a shell — EINVAL, and the Windows release leg
 * dies at its first build. So each tool is its package's own JS entry, run by
 * this Node (scripts/node-bin.mjs), and no script names a shim at all.
 */
const scripts = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "scripts");

describe("the build scripts' commands", () => {
  it("run electron-vite with this Node, from its own bin entry", () => {
    const [command, args] = electronViteBuild();
    expect(command).toBe(process.execPath);
    expect(args[0]).toMatch(/[\\/]electron-vite[\\/]bin[\\/]electron-vite\.js$/);
    expect(fs.existsSync(args[0]!)).toBe(true);
    expect(args.slice(1)).toEqual(["build"]);
  });

  it("run electron-builder with this Node, from its own cli.js", () => {
    const [command, args] = electronBuilder(["--mac", "--arm64"], { version: "1.2.3", notarize: true });
    expect(command).toBe(process.execPath);
    expect(args[0]).toMatch(/[\\/]electron-builder[\\/]cli\.js$/);
    expect(fs.existsSync(args[0]!)).toBe(true);
    expect(args.slice(1)).toEqual([
      "--mac", "dmg", "zip", "--arm64",
      "--config.extraMetadata.version=1.2.3",
      "--config.mac.notarize=true",
      "--publish", "never",
    ]);
  });

  it("never name npx, a .cmd/.bat shim, or a shell", () => {
    const offenders = fs
      .readdirSync(scripts)
      .filter((name) => name.endsWith(".mjs"))
      .flatMap((name) => {
        const source = fs.readFileSync(path.join(scripts, name), "utf8");
        return [/["']npx(\.cmd)?["']/, /\.(cmd|bat)["']/, /shell:\s*true/]
          .filter((pattern) => pattern.test(source))
          .map((pattern) => `${name}: ${pattern}`);
      });
    expect(offenders).toEqual([]);
  });
});
