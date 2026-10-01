import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FileRendererProps, FileSource } from "@text-to-cad/ui/file-viewer";
import { ViewerHostContext } from "@text-to-cad/ui/host";

const loading = vi.hoisted(() => ({ reject: (_reason: unknown) => {} }));
vi.mock("pdfjs-dist/legacy/build/pdf.mjs", () => ({
  getDocument: () => ({
    promise: new Promise((_resolve, reject) => { loading.reject = reject; }),
    destroy: async () => {},
  }),
  PDFWorker: { create: () => ({ destroy() {} }) },
  TextLayer: class {},
}));
vi.mock("pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker", () => ({ default: class { terminate() {} } }));
vi.mock("pdfjs-dist/web/pdf_viewer.css", () => ({}));

import mainFs from "../../../src/main/explorer/fs.ts?raw";
import { FileLoadError, PREVIEW_LIMIT_BYTES } from "@renderer/features/explorer/FileLoadError";
import ImageRenderer from "@renderer/features/explorer/renderers/image/ImageRenderer";
import PdfRenderer from "@renderer/features/explorer/renderers/pdf/PdfRenderer";

import { testViewerHost } from "../../viewer-host";

const openDefault = vi.fn();
const host = () => testViewerHost({ fileActions: { perform: { "open-default": openDefault } } });
const source = (size: number): FileSource => ({
  id: "root", rootName: "Root",
  stat: async (filePath) => ({ path: filePath, name: filePath, kind: "file", size, extension: "png", mediaType: "image" }) as never,
});
const props = (name: string, extension: string): FileRendererProps<never> => ({
  data: { url: "blob:x", bytes: new Uint8Array() } as never,
  file: { path: name, name, kind: "file", size: 1_258_291, extension, mediaType: "image" },
  source: source(0), document: null, openPanel: "", panelSlot: null, onPanelOpen: vi.fn(), onReady: vi.fn(), onOpenFile: vi.fn(),
  appearance: { colorScheme: "dark" }, state: undefined, onStateChange: vi.fn(), reload: vi.fn(),
});

describe("previews that cannot be shown", () => {
  it("says a corrupt image could not be decoded, and offers Open externally", () => {
    render(<ViewerHostContext.Provider value={host()}><ImageRenderer {...props("broken.png", "png")} /></ViewerHostContext.Provider>);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText("This image could not be decoded.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open externally" }));
    expect(openDefault).toHaveBeenCalledWith({ path: "broken.png", kind: "file" });
  });

  it("names the size and the limit of a file too large to preview, with Open externally", async () => {
    render(<ViewerHostContext.Provider value={host()}><FileLoadError message="that file is too large to preview" path="photos/big.png" source={source(30 * 1024 * 1024)} /></ViewerHostContext.Provider>);
    expect(await screen.findByText("big.png is 30 MB; previews open files up to 24 MB.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open externally" })).toBeInTheDocument();
  });

  it("keeps other failures as they were", () => {
    render(<ViewerHostContext.Provider value={host()}><FileLoadError message="no such file" path="a.png" source={source(1)} /></ViewerHostContext.Provider>);
    expect(screen.getByText("Could not open that file")).toBeInTheDocument();
    expect(screen.getByText("no such file")).toBeInTheDocument();
  });

  it("mirrors the main process's binary limit", () => {
    expect(/MAX_BINARY_BYTES = (\d+) \* 1024 \* 1024/.exec(mainFs)?.[1]).toBe(String(PREVIEW_LIMIT_BYTES / 1024 / 1024));
  });

  it("says a PDF could not be opened, with PDF.js's reason, and hides the page toolbar", async () => {
    render(<ViewerHostContext.Provider value={host()}><PdfRenderer {...props("bad.pdf", "pdf")} /></ViewerHostContext.Provider>);
    expect(screen.getByLabelText("Previous page")).toBeInTheDocument();
    const failure = Object.assign(new Error("Invalid PDF structure."), { name: "InvalidPDFException" });
    loading.reject(failure);
    expect(await screen.findByText("This PDF could not be opened: Invalid PDF structure.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Previous page")).toBeNull();
    expect(screen.queryByText(/InvalidPDFException/)).toBeNull();
  });
});
