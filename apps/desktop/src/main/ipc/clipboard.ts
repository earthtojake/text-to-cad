import { clipboard, nativeImage } from "electron";

import { MAX_CLIPBOARD_PNG_BYTES } from "../../shared/ipc/clipboard";
import type { clipboardContract } from "../../shared/ipc/clipboard";
import type { IpcHandlers } from "../../shared/ipc/define";
import { IpcError } from "./register";

const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function decodePng(encoded: string) {
  const bytes = Buffer.from(encoded, "base64");
  if (bytes.length > MAX_CLIPBOARD_PNG_BYTES || !bytes.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new IpcError("Clipboard image must be a PNG of at most 16 MiB.");
  }
  const image = nativeImage.createFromBuffer(bytes);
  const { width, height } = image.getSize();
  if (image.isEmpty() || width > 16384 || height > 16384 || width * height > 64 * 1024 * 1024) {
    throw new IpcError("Clipboard PNG is invalid or too large.");
  }
  return image;
}

export const clipboardHandlers = {
  clipboard: {
    writeText: ({ text }) => clipboard.writeText(text),
    readText: () => clipboard.readText(),
    writeImage: ({ pngBase64 }) => clipboard.writeImage(decodePng(pngBase64)),
  },
} satisfies IpcHandlers<typeof clipboardContract>;
