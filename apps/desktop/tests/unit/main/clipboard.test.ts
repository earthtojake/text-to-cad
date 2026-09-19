import { beforeEach, describe, expect, it, vi } from "vitest";

const native = vi.hoisted(() => ({
  clipboard: { writeText: vi.fn(), readText: vi.fn(), writeImage: vi.fn(), write: vi.fn() },
  image: { isEmpty: vi.fn(() => false), getSize: vi.fn(() => ({ width: 100, height: 80 })) },
  createFromBuffer: vi.fn(),
}));
vi.mock("electron", () => ({ clipboard: native.clipboard, nativeImage: { createFromBuffer: native.createFromBuffer } }));
vi.mock("@main/ipc/register", () => ({ IpcError: class IpcError extends Error {} }));

import { clipboardHandlers } from "@main/ipc/clipboard";
import { ClipboardContentSchema, clipboardContract } from "@shared/ipc/clipboard";

const png = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 1]).toString("base64");
beforeEach(() => {
  vi.clearAllMocks();
  native.image.isEmpty.mockReturnValue(false);
  native.image.getSize.mockReturnValue({ width: 100, height: 80 });
  native.createFromBuffer.mockReturnValue(native.image);
});

describe("native clipboard boundary", () => {
  it("writes a text and PNG bundle together after decoding the image", () => {
    clipboardHandlers.clipboard.writeContent({ text: "part.step#o1", pngBase64: png });
    expect(native.clipboard.write).toHaveBeenCalledExactlyOnceWith({ text: "part.step#o1", image: native.image });
    expect(native.clipboard.writeText).not.toHaveBeenCalled();
  });

  it("rejects invalid PNG bytes before changing either representation", () => {
    expect(() => clipboardHandlers.clipboard.writeContent({ text: "keep together", pngBase64: Buffer.from("not png").toString("base64") })).toThrow("must be a PNG");
    expect(native.clipboard.write).not.toHaveBeenCalled();
    expect(native.createFromBuffer).not.toHaveBeenCalled();
    native.image.isEmpty.mockReturnValue(true);
    expect(() => clipboardHandlers.clipboard.writeImage({ pngBase64: png })).toThrow("invalid or too large");
    expect(native.clipboard.writeImage).not.toHaveBeenCalled();
  });

  it("bounds decoded image dimensions", () => {
    native.image.getSize.mockReturnValue({ width: 16385, height: 80 });
    expect(() => clipboardHandlers.clipboard.writeImage({ pngBase64: png })).toThrow("too large");
    expect(native.clipboard.writeImage).not.toHaveBeenCalled();
  });

  it("only accepts bounded plain text and PNG base64, without arbitrary formats", () => {
    expect(ClipboardContentSchema.safeParse({}).success).toBe(false);
    expect(ClipboardContentSchema.safeParse({ text: "hello", html: "<script>" }).success).toBe(false);
    expect(clipboardContract.clipboard.writeImage.request.safeParse({ pngBase64: "!" }).success).toBe(false);
    expect(clipboardContract.clipboard.writeText.request.safeParse({ text: "x".repeat(1024 * 1024 + 1) }).success).toBe(false);
  });

  it("keeps native text read and write explicit", () => {
    native.clipboard.readText.mockReturnValue("pasted text");
    clipboardHandlers.clipboard.writeText({ text: "reference" });
    expect(native.clipboard.writeText).toHaveBeenCalledExactlyOnceWith("reference");
    expect(clipboardHandlers.clipboard.readText()).toBe("pasted text");
  });
});
