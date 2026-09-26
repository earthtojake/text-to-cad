import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import type { WebContents } from "electron";
import { browserHarness } from "../../../src/main/browser/harness";

describe("pinned Browser Use native transport", () => {
  it("keeps the reviewed upstream implementation byte-for-byte", () => {
    const vendor = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../src/main/browser/vendor/generated.ts");
    expect(createHash("sha256").update(fs.readFileSync(vendor)).digest("hex")).toBe("17d8b3718863d4a07046c6badc7e497c2d165d745a2cf9f04324ebb9acedf893");
  });
  it("routes upstream methods only to the supplied native page and rejects a destroyed page", async () => {
    let destroyed = false;
    const sendCommand = vi.fn().mockResolvedValue({ data: "png" });
    const attach = vi.fn();
    const contents = { isDestroyed: () => destroyed, debugger: { isAttached: () => false, attach, sendCommand } } as unknown as WebContents;
    const harness = browserHarness(contents);
    await expect(harness.Page.captureScreenshot({ format: "png" })).resolves.toEqual({ data: "png" });
    expect(attach).toHaveBeenCalledWith("1.3");
    expect(sendCommand).toHaveBeenCalledWith("Page.captureScreenshot", { format: "png" });
    destroyed = true;
    await expect(harness.DOM.focus({ backendNodeId: 42 })).rejects.toThrow("closed");
    expect(sendCommand).toHaveBeenCalledTimes(1);
  });
});
