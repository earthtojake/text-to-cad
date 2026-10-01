import * as monaco from "monaco-editor";
import { expect, it, vi } from "vitest";

import {
  MONACO_DARK,
  MONACO_LIGHT,
  MONACO_TRANSCRIPT_DARK,
  MONACO_TRANSCRIPT_LIGHT,
  SHARED_EDITOR_OPTIONS,
  setupMonaco,
} from "@renderer/features/explorer/renderers/code/editor";
import { configureMonaco } from "@renderer/lib/monaco";

it("the transcript's themes do not replace the review's: each name is registered once, the shell's with the shell background", () => {
  const define = vi.spyOn(monaco.editor, "defineTheme");
  // Both doors, in either order and repeatedly: the transcript's diff and the review's.
  configureMonaco();
  setupMonaco();
  configureMonaco();

  const colors = (name: string) => {
    const calls = define.mock.calls.filter(([theme]) => theme === name);
    expect(calls).toHaveLength(1);
    return calls[0]![1].colors;
  };
  expect(define.mock.calls.map(([name]) => name)).toEqual([
    MONACO_LIGHT,
    MONACO_DARK,
    MONACO_TRANSCRIPT_LIGHT,
    MONACO_TRANSCRIPT_DARK,
  ]);
  expect(colors(MONACO_DARK)["editor.background"]).toBe("#292929");
  expect(colors(MONACO_LIGHT)["editor.background"]).toBe("#ffffff");
  expect(colors(MONACO_TRANSCRIPT_DARK)["editor.background"]).toBe("#00000000");
  // The transcript keeps the shell's diff colours rather than Monaco's defaults.
  expect(colors(MONACO_TRANSCRIPT_DARK)["diffEditor.insertedLineBackground"]).toBe(
    colors(MONACO_DARK)["diffEditor.insertedLineBackground"],
  );
  define.mockRestore();
});

it("an editor opens in the Code font Settings chose, as the row promises the editor and diffs", () => {
  document.documentElement.style.setProperty("--font-mono", '"JetBrains Mono", monospace');
  try {
    expect({ ...SHARED_EDITOR_OPTIONS }.fontFamily).toBe('"JetBrains Mono", monospace');
  } finally {
    document.documentElement.style.removeProperty("--font-mono");
  }
  expect({ ...SHARED_EDITOR_OPTIONS }.fontFamily).toMatch(/monospace$/);
});
