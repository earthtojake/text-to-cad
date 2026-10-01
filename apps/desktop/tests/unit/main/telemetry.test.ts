import { beforeEach, describe, expect, it, vi } from "vitest";

const electron = vi.hoisted(() => ({ ready: false }));
const aptabase = vi.hoisted(() => ({
  initialize: vi.fn(async () => undefined),
  trackEvent: vi.fn(async () => undefined),
}));
const stored = vi.hoisted(() => ({ telemetry: true }));

vi.mock("electron", () => ({ app: { isReady: () => electron.ready } }));
vi.mock("@aptabase/electron/main", () => aptabase);
vi.mock("@main/db/repositories", () => ({ settings: { get: () => stored } }));

async function load(key: string) {
  vi.resetModules();
  vi.stubGlobal("__APTABASE_KEY__", key);
  return import("@main/telemetry");
}

beforeEach(() => {
  electron.ready = false;
  stored.telemetry = true;
  aptabase.initialize.mockClear();
  aptabase.trackEvent.mockClear();
});

describe("initTelemetry", () => {
  it("initializes Aptabase before the app is ready and then sends events", async () => {
    const telemetry = await load("A-US-0000000000");
    telemetry.initTelemetry();
    expect(aptabase.initialize).toHaveBeenCalledWith("A-US-0000000000");
    telemetry.track({ name: "file_opened", extension: "step" });
    expect(aptabase.trackEvent).toHaveBeenCalledWith("file_opened", { extension: "step" });
  });

  it("refuses after ready instead of buffering events Aptabase will never send", async () => {
    electron.ready = true;
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const telemetry = await load("A-US-0000000000");
    telemetry.initTelemetry();
    telemetry.track({ name: "app_launched" });
    expect(aptabase.initialize).not.toHaveBeenCalled();
    expect(aptabase.trackEvent).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it("still reads the opt-out per event", async () => {
    const telemetry = await load("A-US-0000000000");
    telemetry.initTelemetry();
    stored.telemetry = false;
    telemetry.track({ name: "app_launched" });
    expect(aptabase.trackEvent).not.toHaveBeenCalled();
  });

  it("is inert without a compiled-in key", async () => {
    const telemetry = await load("");
    telemetry.initTelemetry();
    telemetry.track({ name: "app_launched" });
    expect(aptabase.initialize).not.toHaveBeenCalled();
    expect(aptabase.trackEvent).not.toHaveBeenCalled();
  });
});

describe("changedSettingsKeys", () => {
  it("names only the fields whose value moved", async () => {
    const { changedSettingsKeys } = await load("");
    const previous = { theme: "dark", layout: { collapsed: false, width: 240 }, telemetry: true };
    const next = { theme: "light", layout: { collapsed: false, width: 240 }, telemetry: true };
    expect(changedSettingsKeys(previous, next, { theme: "light", layout: { collapsed: false, width: 240 } })).toEqual([
      "theme",
    ]);
    const dragged = { ...previous, layout: { collapsed: false, width: 300 } };
    expect(changedSettingsKeys(previous, dragged, { layout: dragged.layout })).toEqual(["layout"]);
    expect(changedSettingsKeys(previous, previous, { telemetry: true })).toEqual([]);
  });
});
