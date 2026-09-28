import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { migrateLegacyUserData } from "@main/legacy-data";

/**
 * The rename's one loose end: a machine that ran Hardcore has its data under that
 * name, and the first launch as text-to-cad takes a copy of it, once.
 */
describe("migrating the Hardcore data directory", () => {
  let appData: string;
  beforeEach(() => { appData = fs.mkdtempSync(path.join(os.tmpdir(), "text-to-cad-appdata-")); });
  afterEach(() => { fs.rmSync(appData, { recursive: true, force: true }); });

  it("copies the old directory to the new name when only the old one exists, and leaves the old one", () => {
    fs.mkdirSync(path.join(appData, "Hardcore", "nested"), { recursive: true });
    fs.writeFileSync(path.join(appData, "Hardcore", "hardcore.db"), "threads");
    fs.writeFileSync(path.join(appData, "Hardcore", "nested", "strip.json"), "[]");
    expect(migrateLegacyUserData(appData)).toBe("copied");
    expect(fs.readFileSync(path.join(appData, "text-to-cad", "hardcore.db"), "utf8")).toBe("threads");
    expect(fs.readFileSync(path.join(appData, "text-to-cad", "nested", "strip.json"), "utf8")).toBe("[]");
    expect(fs.existsSync(path.join(appData, "Hardcore", "hardcore.db")), "the old app keeps its data").toBe(true);
  });

  it("does nothing when the new directory already exists, even if the old one changed since", () => {
    fs.mkdirSync(path.join(appData, "Hardcore"), { recursive: true });
    fs.writeFileSync(path.join(appData, "Hardcore", "hardcore.db"), "old");
    fs.mkdirSync(path.join(appData, "text-to-cad"), { recursive: true });
    fs.writeFileSync(path.join(appData, "text-to-cad", "hardcore.db"), "new");
    expect(migrateLegacyUserData(appData)).toBe("present");
    expect(fs.readFileSync(path.join(appData, "text-to-cad", "hardcore.db"), "utf8")).toBe("new");
  });

  it("does nothing on a machine that never ran the old app", () => {
    expect(migrateLegacyUserData(appData)).toBe("none");
    expect(fs.existsSync(path.join(appData, "text-to-cad"))).toBe(false);
  });
});
