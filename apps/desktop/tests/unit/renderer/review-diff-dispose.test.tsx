import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ReviewDiff } from "@renderer/features/explorer/review-diff";
import type { FileDiff } from "@renderer/features/explorer/types";

/**
 * The review keeps its two diff models past @monaco-editor/react's cleanup
 * (which would dispose them before the widget and make monaco 0.56 throw) and
 * disposes them itself once the widget has gone. What it listens to matters:
 * monaco 0.56's DiffEditorWidget never fires its own onDidDispose, only its
 * inner code editors do. The fake here behaves the same way, so a listener on
 * the widget leaks both models and this test fails.
 */

const listener = () => {
  const callbacks: Array<() => void> = [];
  return {
    on: (callback: () => void) => {
      callbacks.push(callback);
      return { dispose: () => undefined };
    },
    fire: () => callbacks.forEach((callback) => callback()),
  };
};

const fakeCode = () => {
  const disposed = listener();
  return {
    disposed,
    editor: {
      onDidDispose: disposed.on,
      getContentHeight: () => 40,
      onDidContentSizeChange: () => ({ dispose: () => undefined }),
      onDidChangeCursorSelection: () => ({ dispose: () => undefined }),
      onDidFocusEditorText: () => ({ dispose: () => undefined }),
      getSelection: () => null,
      getModel: () => null,
    },
  };
};

let models: { original: { dispose: () => void }; modified: { dispose: () => void } };
let shown: { original?: string; modified?: string } = {};
let editorOptions: Record<string, unknown> = {};
// The real wrapper mounts after monaco's loader resolves, and the widget's diff
// arrives from a worker after that; `mountNow` and `diffUpdated` stand for both.
let deferMount = false;
let mountNow: () => void = () => undefined;
let computed: unknown[] | null = null;
let diffUpdated = listener();

vi.mock("@monaco-editor/react", async () => {
  const { useEffect, useRef } = await import("react");
  function DiffEditor({ onMount, original, modified, options }: { onMount: (editor: unknown) => void; original: string; modified: string; options: Record<string, unknown> }) {
    shown = { original, modified };
    editorOptions = options;
    // Mounted once, like the real wrapper, whatever the parent re-renders.
    const mount = useRef(onMount);
    useEffect(() => {
      const originalCode = fakeCode();
      const modifiedCode = fakeCode();
      const widget = {
        getModel: () => models,
        getOriginalEditor: () => originalCode.editor,
        getModifiedEditor: () => modifiedCode.editor,
        // Created and never fired, as in monaco 0.56's DelegatingEditor.
        onDidDispose: listener().on,
        getLineChanges: () => computed,
        onDidUpdateDiff: diffUpdated.on,
      };
      mountNow = () => mount.current(widget);
      if (!deferMount) mountNow();
      // The wrapper's cleanup disposes the widget, which disposes its inner
      // editors; with keepCurrent*Model it leaves the models alone.
      return () => {
        originalCode.disposed.fire();
        modifiedCode.disposed.fire();
      };
    }, []);
    return <div data-testid="diff-editor" />;
  }
  function Editor({ options }: { options: Record<string, unknown> }) {
    editorOptions = options;
    return <div data-testid="editor" />;
  }
  return { default: Editor, DiffEditor };
});
vi.mock("@renderer/features/explorer/renderers/code/editor/setup", () => ({ setupMonaco: vi.fn() }));

const diff: FileDiff = {
  path: "part.py",
  status: "modified",
  before: "a = 1\n",
  after: "a = 2\n",
  insertions: 1,
  deletions: 1,
} as FileDiff;

beforeEach(() => {
  vi.useFakeTimers();
  models = { original: { dispose: vi.fn() }, modified: { dispose: vi.fn() } };
  deferMount = false;
  computed = null;
  diffUpdated = listener();
});

afterEach(() => {
  vi.useRealTimers();
});

it("disposes both kept diff models once the diff editor has unmounted", () => {
  const view = render(<ReviewDiff diff={diff} onSelect={() => undefined} path="part.py" theme="light" />);
  expect(models.original.dispose).not.toHaveBeenCalled();

  view.unmount();
  // Not in the same tick: the widget's own teardown still holds them.
  expect(models.modified.dispose).not.toHaveBeenCalled();
  act(() => {
    vi.runAllTimers();
  });

  expect(models.original.dispose).toHaveBeenCalledTimes(1);
  expect(models.modified.dispose).toHaveBeenCalledTimes(1);
});

it("draws no empty last row for the final newline both sides share", () => {
  // notes.txt → notes-renamed.txt with a line added: before the fix Monaco was handed
  // both files whole and drew a fifth, empty row that is on neither side of git's diff.
  const renamed = { ...diff, path: "notes-renamed.txt", status: "renamed", oldPath: "notes.txt", before: "one\ntwo\nthree\n", after: "one\ntwo\nthree\nfour\n" } as FileDiff;
  render(<ReviewDiff diff={renamed} onSelect={() => undefined} path="notes-renamed.txt" theme="light" />);
  expect(shown).toEqual({ original: "one\ntwo\nthree", modified: "one\ntwo\nthree\nfour" });
});

it("keeps a final newline that only one side has: that is the change", () => {
  render(<ReviewDiff diff={{ ...diff, before: "a = 1", after: "a = 1\n" }} onSelect={() => undefined} path="part.py" theme="light" />);
  expect(shown).toEqual({ original: "a = 1", modified: "a = 1\n" });
});

it("is marked ready only once the diff editor has mounted and drawn its first computed diff", () => {
  deferMount = true;
  const view = render(<ReviewDiff diff={diff} onSelect={() => undefined} path="part.py" theme="light" />);
  const block = view.container.querySelector("[data-review-diff=modified]");
  expect(block?.hasAttribute("data-review-ready")).toBe(false);

  act(() => mountNow());
  // Mounted with both models, but nothing computed to draw rows from yet.
  expect(block?.hasAttribute("data-review-ready")).toBe(false);

  computed = [];
  act(() => diffUpdated.fire());
  expect(block?.getAttribute("data-review-ready")).toBe("true");
});

it("is ready at mount when the diff was already computed", () => {
  computed = [];
  const view = render(<ReviewDiff diff={diff} onSelect={() => undefined} path="part.py" theme="light" />);
  expect(view.container.querySelector("[data-review-diff=modified]")?.getAttribute("data-review-ready")).toBe("true");
});

it("names each side's text field for the file, so a screen reader does not hear two unnamed editors", () => {
  render(<ReviewDiff diff={{ ...diff, path: "parts/part.py" }} onSelect={() => undefined} path="parts/part.py" theme="light" />);
  expect(editorOptions).toMatchObject({ originalAriaLabel: "part.py, before", modifiedAriaLabel: "part.py, after" });
  render(<ReviewDiff diff={{ ...diff, status: "added", before: null }} onSelect={() => undefined} path="parts/new.py" theme="light" />);
  expect(editorOptions).toMatchObject({ ariaLabel: "new.py, added" });
});
