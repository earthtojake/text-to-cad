import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useEffect, useId, useMemo, useRef } from "react";

import type { FileRendererProps } from "../../file-viewer/types.js";

import {
  SHARED_EDITOR_OPTIONS,
  languageFor,
  monacoModelUri,
  monacoTheme,
} from "./editor/monaco.js";
import { setupMonaco } from "./editor/setup.js";

/** Languages whose source is prose, and therefore wraps. */
const WRAPPED = new Set(["markdown", "plaintext"]);

/**
 * Monaco, for one file in a shared FileViewer.
 *
 * The save keybinding is bound on the editor rather than the window because
 * Cmd/Ctrl+S has to mean "save this file" only while the editor has focus —
 * the same chord in a terminal tab is the shell's.
 *
 * The editor is *uncontrolled*: `value` seeds the model and every later
 * keystroke is the model's. A controlled Monaco (rewriting `value` on every
 * change) loses the cursor position on each keystroke, which is unusable. So
 * the reload path is explicit: when the file's revision changes underneath —
 * an agent's edit, a `git checkout` — the parent remounts by key.
 */
export type CodeRendererData = null;

export default function CodeRenderer({
  file,
  source,
  document,
  appearance,
  onReady,
}: FileRendererProps<CodeRendererData>) {
  setupMonaco();
  const viewId = useId();
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  // The command is registered once, on the editor, and lives as long as it
  // does — so it calls through a ref rather than closing over the `onSave` it
  // was created with. Written in an effect, not in render: a ref is not
  // rendering state, and writing one during render is how a component ends up
  // reading a value React has not committed.
  const saveRef = useRef(document?.save);
  useEffect(() => {
    saveRef.current = document?.save;
  }, [document?.save]);

  const onMount: OnMount = (instance, monaco) => {
    editorRef.current = instance;
    instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => void saveRef.current?.());
  };

  useEffect(() => () => editorRef.current?.dispose(), []);
  useEffect(() => onReady(true), [onReady]);

  const language = languageFor(file.path);
  const modelPath = useMemo(
    () => monacoModelUri(source.id, file.path, document?.key ?? "readonly", viewId),
    [document?.key, file.path, source.id, viewId],
  );

  return (
    <Editor
      language={language}
      loading={<div className="p-4 text-xs text-muted-foreground">Opening…</div>}
      onChange={(next) => document?.setValue(next ?? "")}
      onMount={onMount}
      options={{
        ...SHARED_EDITOR_OPTIONS,
        readOnly: document?.readOnly ?? true,
        // Prose wraps; code does not. A markdown or plain-text file is
        // paragraphs, and reading one by scrolling sideways is not reading.
        wordWrap: WRAPPED.has(language) ? "on" : "off",
      }}
      path={modelPath}
      theme={monacoTheme(appearance.colorScheme)}
      value={document?.value ?? ""}
    />
  );
}
