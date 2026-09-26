import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("electron", () => ({ app: { isPackaged: false, getPath: () => os.tmpdir() } }));

import { createSampleProject, onboardingEnabled } from "../../../src/main/onboarding";

describe("onboardingEnabled", () => {
  it("is on for a person and off under the test suites unless a spec asks for it", () => {
    expect(onboardingEnabled({})).toBe(true);
    expect(onboardingEnabled({ NODE_ENV: "production" })).toBe(true);
    expect(onboardingEnabled({ NODE_ENV: "test" })).toBe(false);
    expect(onboardingEnabled({ NODE_ENV: "test", HARDCORE_ONBOARDING: "1" })).toBe(true);
  });
});

describe("createSampleProject", () => {
  let directory: string;
  let source: string;
  let target: string;

  beforeEach(() => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-sample-"));
    source = path.join(directory, "bundle");
    target = path.join(directory, "Documents", "Hardcore Sample");
    fs.mkdirSync(source);
    fs.writeFileSync(path.join(source, "part.py"), "print('bundled')\n");
  });

  afterEach(() => {
    fs.rmSync(directory, { recursive: true, force: true });
  });

  it("copies the bundled sample the first time and answers with its folder", () => {
    expect(createSampleProject(target, source)).toBe(target);
    expect(fs.readFileSync(path.join(target, "part.py"), "utf8")).toBe("print('bundled')\n");
  });

  it("reuses a copy that is already there instead of overwriting the person's edits", () => {
    fs.mkdirSync(target, { recursive: true });
    fs.writeFileSync(path.join(target, "part.py"), "print('edited')\n");
    expect(createSampleProject(target, source)).toBe(target);
    expect(fs.readFileSync(path.join(target, "part.py"), "utf8")).toBe("print('edited')\n");
  });

  it("says so when the build has no sample", () => {
    expect(() => createSampleProject(target, path.join(directory, "missing"))).toThrow(/sample project is missing/);
  });

  it("ships a sample in this checkout", () => {
    const bundled = path.resolve(__dirname, "../../../resources/sample");
    expect(fs.existsSync(path.join(bundled, "l_bracket.py"))).toBe(true);
    expect(fs.existsSync(path.join(bundled, "l_bracket.step"))).toBe(true);
  });
});
