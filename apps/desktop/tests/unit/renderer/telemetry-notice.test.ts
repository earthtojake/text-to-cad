import { describe, expect, it } from "vitest";

import { shouldShowTelemetryNotice, TELEMETRY_NOTICE_TEXT } from "@renderer/features/settings/telemetry-notice";
import { telemetryStatusLine } from "@renderer/features/settings/pages/GeneralPage";
import { defaultSettings } from "@shared/types";

const can = { available: true, reason: null, variable: null } as const;

/** The first-launch notice shows once, only where telemetry could actually send. */
describe("the telemetry notice", () => {
  it("shows once, when this build can send, telemetry is on and the notice has not been shown", () => {
    expect(shouldShowTelemetryNotice(can, defaultSettings())).toBe(true);
    expect(shouldShowTelemetryNotice(can, { ...defaultSettings(), telemetryNoticeShown: true })).toBe(false);
    expect(shouldShowTelemetryNotice(can, { ...defaultSettings(), telemetry: false })).toBe(false);
  });

  it("never shows where nothing could be sent: no key, an environment that said no, or no answer", () => {
    expect(shouldShowTelemetryNotice({ available: false, reason: "no-key", variable: null }, defaultSettings())).toBe(false);
    expect(shouldShowTelemetryNotice({ available: false, reason: "environment", variable: "DO_NOT_TRACK" }, defaultSettings())).toBe(false);
    expect(shouldShowTelemetryNotice(null, defaultSettings())).toBe(false);
    expect(shouldShowTelemetryNotice(can, null)).toBe(false);
  });

  it("names the four events and what they never carry", () => {
    for (const word of ["launches", "sessions", "file types", "settings"]) expect(TELEMETRY_NOTICE_TEXT).toContain(word);
    expect(TELEMETRY_NOTICE_TEXT).toMatch(/Never a file name, a path, a prompt/);
  });

  it("Settings says why nothing is sent, by the variable's name", () => {
    expect(telemetryStatusLine(can)).toBeNull();
    expect(telemetryStatusLine({ available: false, reason: "no-key", variable: null })).toMatch(/no telemetry key/);
    expect(telemetryStatusLine({ available: false, reason: "environment", variable: "CI" })).toMatch(/CI is set/);
  });
});
