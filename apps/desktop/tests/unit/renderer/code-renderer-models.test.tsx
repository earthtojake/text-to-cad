import { loader } from "@monaco-editor/react";
import { act, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { DocumentSession, FileRendererProps } from "@text-to-cad/ui/file-viewer";
import { ViewerHostContext } from "@text-to-cad/ui/host";
import CodeRenderer from "@renderer/features/explorer/renderers/code/CodeRenderer";

import { testViewerHost } from "../../viewer-host";

/**
 * Every model a code view creates is gone once the view is. The URI carries
 * the view's own id, so nothing ever reuses one: a model left behind is a
 * model leaked, on every tab switch, reload and save-driven remount.
 *
 * This runs the real @monaco-editor/react against a fake monaco, because the
 * leak is in the order of the two cleanups: the wrapper disposes the model it
 * finds on the editor, and an editor disposed before that has none.
 */

vi.mock("@renderer/features/explorer/renderers/code/editor/setup", () => ({ setupMonaco: vi.fn() }));

type FakeModel = { uri: string; disposed: boolean; dispose: () => void };
const models: FakeModel[] = [];
const created: Array<Record<string, unknown>> = [];
const noop = () => ({ dispose: () => undefined });

const fakeMonaco = {
  Uri: { parse: (value: string) => ({ path: value, toString: () => value }) },
  KeyMod: { CtrlCmd: 2048 },
  KeyCode: { KeyS: 49 },
  editor: {
    EditorOption: { readOnly: 1 },
    getModel: (uri: { toString(): string }) => models.find((model) => !model.disposed && model.uri === uri.toString()) ?? null,
    createModel: (_value: string, _language: string, uri?: { toString(): string }) => {
      const model: FakeModel = { uri: String(uri), disposed: false, dispose: () => { model.disposed = true; } };
      models.push(model);
      return model;
    },
    // Like monaco's: a disposed editor has detached its model.
    create: (_element: HTMLElement, options: { model: FakeModel | null }) => {
      created.push(options);
      let model = options.model;
      return {
        getModel: () => model,
        setModel: (next: FakeModel) => { model = next; },
        dispose: () => { model = null; },
        saveViewState: () => null,
        restoreViewState: () => undefined,
        updateOptions: () => undefined,
        getOption: () => false,
        getValue: () => "",
        setValue: () => undefined,
        revealLine: () => undefined,
        onDidChangeModelContent: noop,
        addAction: noop,
        addCommand: () => null,
        getSelection: () => null,
      };
    },
    setTheme: () => undefined,
    setModelLanguage: () => undefined,
    onDidChangeMarkers: noop,
    getModelMarkers: () => [],
  },
};

loader.config({ monaco: fakeMonaco as never });

const document: DocumentSession = {
  key: "document-1",
  value: "a = 1\n",
  readOnly: false,
  dirty: false,
  saving: false,
  stale: false,
  error: null,
  setValue: vi.fn(),
  save: vi.fn(async () => ({ status: "unavailable" as const })),
  reload: vi.fn(),
  keepMine: vi.fn(),
};

const props: FileRendererProps<null> = {
  data: null,
  file: { path: "part.py", name: "part.py", kind: "file", size: 6, extension: "py", mediaType: "text" },
  source: { id: "root:fixture", rootName: "Fixture", stat: async () => { throw new Error("unused"); } },
  document,
  openPanel: "",
  panelSlot: null,
  onPanelOpen: vi.fn(),
  onReady: vi.fn(),
  onOpenFile: vi.fn(),
  appearance: { colorScheme: "dark" },
  state: undefined,
  onStateChange: vi.fn(),
  reload: vi.fn(),
};

it("disposes every model it created once the view unmounts", async () => {
  for (let mount = 0; mount < 3; mount += 1) {
    const view = render(<ViewerHostContext.Provider value={testViewerHost()}><CodeRenderer {...props} /></ViewerHostContext.Provider>);
    // The loader resolves, then the editor is created in an effect.
    await act(async () => { await Promise.resolve(); });
    view.unmount();
  }

  expect(models).toHaveLength(3);
  expect(models.filter((model) => !model.disposed)).toEqual([]);
});

it("names the editor's text field for the file, not Monaco's \"Editor content\"", async () => {
  created.length = 0;
  const view = render(<ViewerHostContext.Provider value={testViewerHost()}><CodeRenderer {...props} /></ViewerHostContext.Provider>);
  await act(async () => { await Promise.resolve(); });
  expect(created[0]).toMatchObject({ ariaLabel: "part.py" });
  view.unmount();
});
