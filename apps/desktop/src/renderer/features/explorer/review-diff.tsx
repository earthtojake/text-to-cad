import type { IDisposable, editor as MonacoEditor } from "monaco-editor";
import Editor, { DiffEditor } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";

import {
  SHARED_EDITOR_OPTIONS,
  languageFor,
  monacoTheme,
} from "@renderer/features/explorer/renderers/code/editor";
import type { FileDiff } from "./types";

/**
 * One file's diff in the review, sized to what it shows.
 *
 * Monaco has no intrinsic height, so the block starts from an estimate and
 * then takes the editor's own content height as soon as it has one — which,
 * for the inline diff, already counts the deleted lines' view zones and the
 * collapsed "N hidden lines" bands. A seven-line file is seven lines tall,
 * not a fixed 390px slab; a long one stops at `MAX_DIFF_HEIGHT` and scrolls
 * inside, with the wheel handed back to the page at either end.
 *
 * A file that only exists on one side — added, untracked, deleted — is not a
 * diff at all. Monaco cannot give a side zero lines (an empty model is one
 * empty line), so a diff of `""` against a new file draws a phantom deleted
 * "line 1" above it. Those files show the side that exists, tinted as wholly
 * inserted or removed.
 *
 * `data-review-ready` goes on once the block has drawn what it shows: the one
 * side's editor has mounted, or the diff editor has its models and its first
 * computed diff (the worker's answer, which the inline rows are drawn from).
 * Before that the block is an estimate-sized box — a reader, or a test,
 * waiting on the diff waits on this.
 */

/** The selection "Request revision" quotes, if any. */
export type ReviewSelection = { side: string; start: number; end: number; text: string };

export const LINE_HEIGHT = SHARED_EDITOR_OPTIONS.lineHeight;
/** Past this a block scrolls inside itself rather than growing. */
export const MAX_DIFF_HEIGHT = 560;
const MIN_DIFF_HEIGHT = 2 * LINE_HEIGHT;
const PADDING = { top: 6, bottom: 6 } as const;

/** Which side stands alone, or null for a real two-sided diff. */
export function singleSide(diff: FileDiff): "added" | "deleted" | null {
  if (diff.status === "added" || diff.status === "untracked" || diff.before === null) {
    return diff.after === null ? null : "added";
  }
  if (diff.status === "deleted" || diff.after === null) {
    return "deleted";
  }
  return null;
}

/**
 * The one side's text, without git's final newline: Monaco draws a file's
 * trailing newline as an extra empty line, and on a wholly-added file that is
 * a `+` line git itself does not count.
 */
export function sideText(text: string): string {
  return text.endsWith("\n") ? text.slice(0, -1) : text;
}

/**
 * The two sides of a two-sided diff, each without git's final newline when
 * both have one — the rule `sideText` keeps for a one-sided file. Left on,
 * Monaco draws the newline as an empty last line that is on neither side of
 * git's diff. One side ending without it is itself the change, and is kept.
 */
export function diffTexts(diff: FileDiff): { original: string; modified: string } {
  const original = diff.before ?? "";
  const modified = diff.after ?? "";
  return original.endsWith("\n") && modified.endsWith("\n")
    ? { original: sideText(original), modified: sideText(modified) }
    : { original, modified };
}

/** The last segment of a repository path, which is what the editors are named for. */
const fileName = (path: string) => path.split("/").pop() || path;

const lineCount = (text: string) => (text === "" ? 1 : text.split("\n").length);

/**
 * The height before Monaco has measured itself: the whole side for a
 * one-sided file; for a diff, the change plus the context Monaco keeps around
 * each collapsed band — `hideUnchangedRegions` folds the rest, so sizing by the
 * file's length would leave a screen of blank editor under a four-line edit.
 */
export function estimateHeight(diff: FileDiff): number {
  const side = singleSide(diff);
  const lines =
    side === "added"
      ? lineCount(sideText(diff.after ?? ""))
      : side === "deleted"
        ? lineCount(sideText(diff.before ?? ""))
        : Math.min(
            lineCount(diffTexts(diff).modified) + diff.deletions,
            diff.insertions + diff.deletions + 8,
          );
  return clampHeight(lines * LINE_HEIGHT + PADDING.top + PADDING.bottom);
}

export const clampHeight = (height: number) =>
  Math.min(MAX_DIFF_HEIGHT, Math.max(MIN_DIFF_HEIGHT, Math.ceil(height)));

const OPTIONS = {
  ...SHARED_EDITOR_OPTIONS,
  readOnly: true,
  overviewRulerLanes: 0,
  scrollBeyondLastLine: false,
  padding: PADDING,
  // The cursor's line band on an unfocused review reads as a highlighted change.
  renderLineHighlightOnlyWhenFocus: true,
  // A capped block scrolls inside itself, and at either end the wheel goes
  // back to the page — a review is read top to bottom, not file by file.
  scrollbar: { alwaysConsumeMouseWheel: false, verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
} as const satisfies MonacoEditor.IStandaloneEditorConstructionOptions;

// Monaco's own diff decorations — the classes and the `+`/`−` codicons its
// inline diff draws — so a one-sided file is tinted by the same theme colours
// as a diff, in both themes. A Tailwind class cannot be used here: Monaco turns
// every character outside [a-z0-9-_] in a decoration class into a space, so
// `bg-green-500/[0.08]` arrives as `bg-green-500`, a solid slab.
const SIDE_DECORATION = {
  added: {
    className: "line-insert",
    marginClassName: "gutter-insert",
    linesDecorationsClassName: "insert-sign codicon codicon-diff-insert",
  },
  deleted: {
    className: "line-delete",
    marginClassName: "gutter-delete",
    linesDecorationsClassName: "delete-sign codicon codicon-diff-remove",
  },
} as const;

export function ReviewDiff({
  diff,
  path,
  theme,
  onSelect,
}: {
  diff: FileDiff;
  path: string;
  theme: "light" | "dark";
  /** Told what is selected in either side, for Request revision to quote. */
  onSelect: (selection: ReviewSelection | null) => void;
}) {
  const [measured, setMeasured] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const listeners = useRef<IDisposable[]>([]);
  useEffect(
    () => () => {
      listeners.current.forEach((listener) => listener.dispose());
    },
    [],
  );

  const side = singleSide(diff);
  const height = measured === null ? estimateHeight(diff) : clampHeight(measured);

  /** Size to `sizer`'s content and remember what is selected in each editor. */
  const track = (
    sizer: MonacoEditor.ICodeEditor,
    editors: ReadonlyArray<readonly [string, MonacoEditor.ICodeEditor]>,
  ) => {
    listeners.current.forEach((listener) => listener.dispose());
    onSelect(null);
    setMeasured(sizer.getContentHeight());
    listeners.current = [
      sizer.onDidContentSizeChange((event) => {
        if (event.contentHeightChanged) setMeasured(event.contentHeight);
      }),
      ...editors.flatMap(([name, code]) => {
        const remember = () => {
          const range = code.getSelection();
          const text = range && !range.isEmpty() ? code.getModel()?.getValueInRange(range) : "";
          onSelect(range && text ? { side: name, text, start: range.startLineNumber, end: range.endLineNumber } : null);
        };
        return [code.onDidChangeCursorSelection(remember), code.onDidFocusEditorText(remember)];
      }),
    ];
  };

  if (side) {
    const text = sideText((side === "added" ? diff.after : diff.before) ?? "");
    return (
      <div data-review-diff={side} data-review-ready={ready || undefined} style={{ height }}>
        <Editor
          language={languageFor(path)}
          onMount={(code, monaco) => {
            const lines = code.getModel()?.getLineCount() ?? 1;
            // Goes with the editor: the collection belongs to it.
            code.createDecorationsCollection([
              {
                range: new monaco.Range(1, 1, lines, 1),
                options: { isWholeLine: true, ...SIDE_DECORATION[side] },
              },
            ]);
            track(code, [[side === "added" ? "modified" : "original", code]]);
            setReady(true);
          }}
          options={{ ...OPTIONS, lineDecorationsWidth: 14, ariaLabel: `${fileName(path)}, ${side === "added" ? "added" : "deleted"}` }}
          theme={monacoTheme(theme)}
          value={text}
        />
      </div>
    );
  }

  const texts = diffTexts(diff);
  return (
    <div data-review-diff="modified" data-review-ready={ready || undefined} style={{ height }}>
      <DiffEditor
        // The wrapper disposes both text models and only then the widget, which
        // monaco 0.56 reports as an uncaught "TextModel got disposed before
        // DiffEditorWidget model got reset" on every unmount — a scope change, a
        // commit, a closed section. So the models outlive the wrapper's cleanup and
        // go when the widget itself has gone.
        keepCurrentModifiedModel
        keepCurrentOriginalModel
        language={languageFor(path)}
        modified={texts.modified}
        onMount={(editor) => {
          // The diff widget itself never fires onDidDispose (monaco 0.56's
          // DelegatingEditor creates the emitter and nothing fires it); its inner
          // code editors do. Deferred a tick so the widget's own teardown, which
          // still holds the models, has finished before they go.
          const models = editor.getModel();
          editor.getModifiedEditor().onDidDispose(() => {
            setTimeout(() => {
              models?.original.dispose();
              models?.modified.dispose();
            }, 0);
          });
          // Inline mode draws everything in the modified editor — deleted lines
          // are view zones in it — so its content height is the block's.
          track(editor.getModifiedEditor(), [
            ["original", editor.getOriginalEditor()],
            ["modified", editor.getModifiedEditor()],
          ]);
          // Mounted is not drawn: the wrapper sets both models on mount, and the
          // rows come from the diff the worker computes after that. Ready is the
          // first computed diff — already there, or when it lands.
          const settle = () => {
            if (editor.getLineChanges() !== null) setReady(true);
          };
          listeners.current.push(editor.onDidUpdateDiff(settle));
          settle();
        }}
        options={{
          ...OPTIONS,
          // Codex's review is a unified diff, and a pane this wide has
          // no room for two columns.
          renderSideBySide: false,
          renderOverviewRuler: false,
          hideUnchangedRegions: { enabled: true, revealLineCount: 3, minimumLineCount: 3 },
          // Each side's text field is named for the file and the side: two unnamed
          // "Editor content" fields per file is what a screen reader heard.
          originalAriaLabel: `${fileName(path)}, before`,
          modifiedAriaLabel: `${fileName(path)}, after`,
        }}
        original={texts.original}
        theme={monacoTheme(theme)}
      />
    </div>
  );
}
