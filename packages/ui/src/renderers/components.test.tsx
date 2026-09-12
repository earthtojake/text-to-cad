import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentSession, FileRendererProps, FileSource } from "../file-viewer/types.js";
import CodeRenderer from "./code/CodeRenderer.js";
import ImageRenderer from "./image/ImageRenderer.js";
import PdfRenderer from "./pdf/PdfRenderer.js";
import UnsupportedRenderer from "./unsupported/UnsupportedRenderer.js";

// The package build uses automatic JSX. This focused no-config Vitest command
// also executes legacy .jsx primitives whose transform expects React global.
Object.assign(globalThis, { React });

let editorProps: Record<string, unknown> | null = null;

vi.mock("@monaco-editor/react", () => ({
  default: (props: Record<string, unknown>) => {
    editorProps = props;
    return <div data-testid="monaco-editor" />;
  },
}));
vi.mock("./code/editor/setup.js", () => ({ setupMonaco: vi.fn() }));

const source = (overrides: Partial<FileSource> = {}): FileSource => ({
  id: "root:fixture",
  rootName: "Fixture",
  stat: async () => { throw new Error("unused"); },
  ...overrides,
});

const documentSession = (overrides: Partial<DocumentSession> = {}): DocumentSession => ({
  key: "document-1",
  value: "const answer = 42;",
  readOnly: false,
  dirty: false,
  saving: false,
  stale: false,
  error: null,
  setValue: vi.fn(),
  save: vi.fn(async () => {}),
  reload: vi.fn(),
  keepMine: vi.fn(),
  ...overrides,
});

function common<T>(data: T, overrides: Partial<FileRendererProps<T>> = {}): FileRendererProps<T> {
  return {
    data,
    file: { path: "src/main.ts", name: "main.ts", kind: "file", size: 2048, extension: "ts", mediaType: "text" },
    source: source(),
    document: null,
    openPanel: "",
    panelSlot: null,
    onPanelOpen: vi.fn(),
    onReady: vi.fn(),
    onOpenFile: vi.fn(),
    appearance: { colorScheme: "dark" },
    state: undefined,
    onStateChange: vi.fn(),
    reload: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  editorProps = null;
  vi.clearAllMocks();
});

describe("CodeRenderer", () => {
  it("preserves editor options, appearance, edits, save binding, and isolated model identity", () => {
    const document = documentSession();
    const props = common(null, { document });
    const first = render(<CodeRenderer {...props} />);
    expect(screen.getByTestId("monaco-editor")).toBeTruthy();
    expect(editorProps?.language).toBe("typescript");
    expect(editorProps?.theme).toBe("hardcore-dark");
    expect(editorProps?.value).toBe(document.value);
    expect(editorProps?.options).toMatchObject({
      fontSize: 12.5,
      lineHeight: 20,
      minimap: { enabled: false },
      readOnly: false,
      wordWrap: "off",
    });
    const firstPath = editorProps?.path;
    expect(firstPath).toMatch(/^hardcore-file:\/\/model\//);

    (editorProps?.onChange as (value: string) => void)("changed");
    expect(document.setValue).toHaveBeenCalledWith("changed");
    let saveCommand: (() => void) | undefined;
    (editorProps?.onMount as (instance: unknown, monaco: unknown) => void)(
      { addCommand: (_key: number, command: () => void) => { saveCommand = command; }, dispose: vi.fn() },
      { KeyMod: { CtrlCmd: 1 }, KeyCode: { KeyS: 2 } },
    );
    saveCommand?.();
    expect(document.save).toHaveBeenCalledOnce();

    const second = render(<CodeRenderer {...props} />);
    expect(editorProps?.path).not.toBe(firstPath);
    first.unmount();
    second.unmount();
  });

  it("keeps prose wrapped and honors read-only documents", () => {
    render(<CodeRenderer {...common(null, {
      file: { path: "README.md", name: "README.md", kind: "file", size: 4, extension: "md" },
      document: documentSession({ readOnly: true }),
    })} />);
    expect(editorProps?.options).toMatchObject({ readOnly: true, wordWrap: "on" });
  });
});

describe("asset and fallback renderers", () => {
  it("keeps image fit/actual-size controls and reports intrinsic dimensions", () => {
    render(<ImageRenderer {...common({ url: "blob:image", mime: "image/png" }, {
      file: { path: "image.png", name: "image.png", kind: "file", size: 2048, extension: "png", mediaType: "image" },
    })} />);
    const image = screen.getByRole("img", { name: "image.png" });
    Object.defineProperties(image, {
      naturalWidth: { configurable: true, value: 640 },
      naturalHeight: { configurable: true, value: 480 },
    });
    fireEvent.load(image);
    expect(screen.getByText("640 × 480 · 2.0 KB")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Actual size" }));
    expect(screen.getByRole("button", { name: "Fit" })).toBeTruthy();
  });

  it("keeps the PDF in Chromium's sandboxed viewer", () => {
    render(<PdfRenderer {...common({ url: "blob:pdf", mime: "application/pdf" }, {
      file: { path: "paper.pdf", name: "paper.pdf", kind: "file", size: 9, extension: "pdf", mediaType: "pdf" },
    })} />);
    const frame = screen.getByTitle("paper.pdf");
    expect(frame.getAttribute("src")).toBe("blob:pdf");
    expect(frame.getAttribute("sandbox")).toBe("");
  });

  it("offers the existing OS fallback only when the host provides it", () => {
    const openDefault = vi.fn();
    render(<UnsupportedRenderer {...common(null, {
      file: { path: "archive.zip", name: "archive.zip", kind: "file", size: 2048, extension: "zip", mediaType: "binary" },
      source: source({ actions: { perform: { "open-default": openDefault } } }),
    })} />);
    fireEvent.click(screen.getByRole("button", { name: "Open externally" }));
    expect(openDefault).toHaveBeenCalledWith({ path: "archive.zip", kind: "file" });
    expect(screen.getByText(/Hardcore has no preview/)).toBeTruthy();
  });
});
