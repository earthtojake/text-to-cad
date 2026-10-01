import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ipcChannels, ipcContract } from "@shared/ipc";

const scripts = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "scripts");

describe("the scripts that drive the app", () => {
  it("call only channels the contract still declares", () => {
    // A script runs outside the typechecker, so a channel removed from the
    // contract leaves a call in it that fails only when someone next runs
    // it — perf-cad kept `projects.addPath` a release after it was gone.
    const declared = new Set(ipcChannels(ipcContract).map(([name]) => name));
    const called: string[] = [];
    for (const file of fs.readdirSync(scripts).filter((name) => /\.m?js$/.test(name))) {
      const source = fs.readFileSync(path.join(scripts, file), "utf8");
      for (const match of source.matchAll(/window\.textToCad\.([A-Za-z]+(?:\.[A-Za-z]+)+)/g)) {
        called.push(`${file}: ${match[1]}`);
      }
    }
    expect(called.filter((entry) => !declared.has(entry.split(": ")[1] ?? ""))).toEqual([]);
  });
});
