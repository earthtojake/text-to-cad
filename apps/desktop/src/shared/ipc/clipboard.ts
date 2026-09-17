import { z } from "zod";

import { defineIpc, invoke } from "./define";

export const MAX_CLIPBOARD_PNG_BYTES = 16 * 1024 * 1024;
const text = z.string().max(1024 * 1024);
const pngBase64 = z.string().min(1).max(Math.ceil(MAX_CLIPBOARD_PNG_BYTES / 3) * 4)
  .regex(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/);
export const ClipboardContentSchema = z.object({ text: text.optional(), pngBase64: pngBase64.optional() })
  .strict().refine(value => value.text !== undefined || value.pngBase64 !== undefined, "Clipboard content is empty");

/** Only plain text and encoded PNGs cross the native clipboard bridge. */
export const clipboardContract = defineIpc({
  clipboard: {
    writeText: invoke(z.object({ text }).strict(), z.void()),
    readText: invoke(z.void(), text),
    writeImage: invoke(z.object({ pngBase64 }).strict(), z.void()),
    writeContent: invoke(ClipboardContentSchema, z.void()),
  },
});
