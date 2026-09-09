import { useEffect, useMemo, useRef } from "react";
import { DiffEditor, type DiffOnMount } from "@monaco-editor/react";

import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { configureMonaco, languageForPath } from "@renderer/lib/monaco";

const LINE_HEIGHT = 18;
const MIN_LINES = 3;
const MAX_LINES = 28;

/**
 * One file's change, in Monaco's diff editor in inline mode — the form
 * Codex expands an edit row into. Read-only; the explorer's Review tab
 * (P3) is where changes are acted on.
 *
 * The module is the default export so `React.lazy` can defer Monaco until a
 * diff is actually opened.
 */
export default function DiffView({
  path,
  oldText,
  newText,
}: {
  path: string;
  oldText: string;
  newText: string;
}) {
  const theme = useResolvedTheme();
  configureMonaco();
  // @monaco-editor/react disposes the two text models on unmount while the
  // widget still holds them, and Monaco throws ("TextModel got disposed
  // before DiffEditorWidget model got reset"). Detaching first, from the
  // parent's cleanup which runs before the child's, keeps that quiet.
  const editorRef = useRef<Parameters<DiffOnMount>[0] | null>(null);
  useEffect(
    () => () => {
      const editor = editorRef.current;
      const models = editor?.getModel();
      editor?.setModel(null);
      models?.original.dispose();
      models?.modified.dispose();
    },
    [],
  );
  const language = useMemo(() => languageForPath(path), [path]);
  const lines = Math.max(oldText.split("\n").length, newText.split("\n").length);
  const height = Math.min(MAX_LINES, Math.max(MIN_LINES, lines + 1)) * LINE_HEIGHT;

  return (
    <div className="overflow-hidden rounded-md border" data-testid="diff-view" style={{ height }}>
      <DiffEditor
        height={height}
        language={language}
        modified={newText}
        onMount={(editor) => {
          editorRef.current = editor;
        }}
        options={{
          readOnly: true,
          renderSideBySide: false,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          renderOverviewRuler: false,
          lineNumbersMinChars: 3,
          folding: false,
          fontSize: 12,
          lineHeight: LINE_HEIGHT,
          automaticLayout: true,
          scrollbar: { alwaysConsumeMouseWheel: false, verticalScrollbarSize: 8 },
          hideUnchangedRegions: { enabled: true, contextLineCount: 3 },
          renderIndicators: true,
          glyphMargin: false,
          overviewRulerLanes: 0,
          diffWordWrap: "off",
        }}
        original={oldText}
        theme={theme === "dark" ? "hardcore-dark" : "hardcore-light"}
      />
    </div>
  );
}
