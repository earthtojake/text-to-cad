import { describe, expect, it } from "vitest";

import { environmentOptOut } from "@main/telemetry-env";

/** The environment's say on telemetry, and which variable said it. */
describe("environmentOptOut", () => {
  it("sends when nothing says no", () => {
    expect(environmentOptOut({})).toBeNull();
    expect(environmentOptOut({ DO_NOT_TRACK: "0", CI: "", TEXT_TO_CAD_TELEMETRY: "1", NODE_ENV: "production" })).toBeNull();
  });

  it("honours DO_NOT_TRACK whatever its truthy value", () => {
    expect(environmentOptOut({ DO_NOT_TRACK: "1" })).toEqual({ variable: "DO_NOT_TRACK", value: "1" });
    expect(environmentOptOut({ DO_NOT_TRACK: "true" })).toEqual({ variable: "DO_NOT_TRACK", value: "true" });
    expect(environmentOptOut({ DO_NOT_TRACK: "false" })).toBeNull();
  });

  it("has an off switch of its own, and treats any CI as not a person", () => {
    expect(environmentOptOut({ TEXT_TO_CAD_TELEMETRY: "0" })).toEqual({ variable: "TEXT_TO_CAD_TELEMETRY", value: "0" });
    expect(environmentOptOut({ TEXT_TO_CAD_TELEMETRY: "false" })?.variable).toBe("TEXT_TO_CAD_TELEMETRY");
    expect(environmentOptOut({ CI: "true" })).toEqual({ variable: "CI", value: "true" });
    expect(environmentOptOut({ GITHUB_ACTIONS: "true" }), "only CI itself, which every runner sets").toBeNull();
  });

  it("is off under the test suites, and DO_NOT_TRACK wins the naming", () => {
    expect(environmentOptOut({ NODE_ENV: "test" })).toEqual({ variable: "NODE_ENV", value: "test" });
    expect(environmentOptOut({ NODE_ENV: "test", DO_NOT_TRACK: "1" })?.variable).toBe("DO_NOT_TRACK");
  });
});
