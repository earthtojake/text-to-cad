import { defineFileRenderer } from "@hardcore/ui/file-viewer";

const TEXT_MIME = /^(?:text\/|application\/(?:json|(?:[a-z0-9.+-]+\+)?json|xml|(?:[a-z0-9.+-]+\+)?xml|javascript|x-javascript|yaml|x-yaml|toml))(?:;|$)/i;

export const codeRenderer = defineFileRenderer<null>({
  id: "code",
  priority: 0,
  matches: (file) => file.mediaType === "text" || TEXT_MIME.test(file.mime ?? ""),
  async prepare({ file, source, signal }) {
    if (!source.readText) throw new Error(`This file source cannot read text files: ${file.path}`);
    const text = await source.readText(file.path, { signal });
    return { data: null, text };
  },
  load: () => import("./CodeRenderer"),
});

export { languageFor, monacoModelUri, monacoTheme } from "./editor/monaco";
export type { CodeRendererData } from "./CodeRenderer";
