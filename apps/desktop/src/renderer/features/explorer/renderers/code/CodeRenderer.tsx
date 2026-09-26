import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { useViewerHost } from "@hardcore/ui/host";
import type { FileRendererProps } from "@hardcore/ui/file-viewer";

import {
  SHARED_EDITOR_OPTIONS,
  languageFor,
  monacoModelUri,
  monacoTheme,
} from "./editor/monaco";
import { setupMonaco } from "./editor/setup";

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
  const host = useViewerHost();
  const [delivery, setDelivery] = useState('');
  const contextRef = useRef({ host, document });
  useEffect(() => {
    contextRef.current = { host, document };
  }, [host, document]);
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
    instance.addAction({ id: 'hardcore.selection-to-prompt', label: 'Use selection in prompt', contextMenuGroupId: 'navigation', contextMenuOrder: 2,
      precondition: 'editorHasSelection', run: () => {
        const selection = instance.getSelection(); const model = instance.getModel();
        if (!selection || !model || selection.isEmpty()) return;
        const current = contextRef.current;
        const text = model.getValueInRange(selection);
        void current.host.promptContext.deliver({ schemaVersion: 1, operationId: crypto.randomUUID(), parts: [
          { id: 'reference', kind: 'reference', reference: { resource: { kind: 'workspace-file', workspaceId: source.id, path: file.path,
            revision: current.document?.dirty ? undefined : current.document?.revision }, target: { kind: 'text-range', start: { line: selection.startLineNumber - 1, character: selection.startColumn - 1 },
            end: { line: selection.endLineNumber - 1, character: selection.endColumn - 1 } } } },
          { id: 'selection', kind: 'text', text },
        ] }).then(result => setDelivery(result.status === 'added' ? 'Added to prompt' : result.status === 'copied' ? 'Copied for prompt' : ('message' in result ? result.message : '') ?? result.status))
          .catch(error => setDelivery(String(error)));
      } });
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
    <div className="flex h-full flex-col"><div className="sr-only" role="status">{delivery}</div><div className="min-h-0 flex-1"><Editor
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
    /></div></div>
  );
}
