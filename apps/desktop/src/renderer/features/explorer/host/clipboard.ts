import type { ClipboardPort } from "@hardcore/ui/host";

async function pngBase64(content: Blob | Promise<Blob>): Promise<string> {
  const blob = await content;
  if (blob.type !== "image/png" || blob.size > 16 * 1024 * 1024) throw new Error("Clipboard image must be a PNG of at most 16 MiB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const encoded = typeof reader.result === "string" ? reader.result.split(",")[1] : undefined;
      if (encoded) resolve(encoded); else reject(new Error("Clipboard image could not be encoded."));
    };
    reader.onerror = () => reject(new Error("Clipboard image could not be read."));
    reader.readAsDataURL(blob);
  });
}

/** Native clipboard effects go through validated main/preload operations only. */
export const desktopClipboard: ClipboardPort = {
  writeText: text => window.hardcore.clipboard.writeText({ text }),
  readText: () => window.hardcore.clipboard.readText(),
  writeImage: async image => window.hardcore.clipboard.writeImage({ pngBase64: await pngBase64(image) }),
  writeContent: async ({ text, image }) => window.hardcore.clipboard.writeContent({
    ...(text === undefined ? {} : { text }),
    ...(image === undefined ? {} : { pngBase64: await pngBase64(image) }),
  }),
};
