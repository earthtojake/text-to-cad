import type * as monaco from 'monaco-editor';
import { configureMonacoTypeScript } from './monaco-config';
import { defineMonacoThemes, getMonacoTheme } from './monaco-themes';

let instance: typeof monaco | null = null;
let initPromise: Promise<typeof monaco> | null = null;

/**
 * Monaco (and its Vite worker wrappers) read `window` at module scope, so all
 * browser-only modules are imported here inside init() rather than at the top
 * of the file. This keeps the bootstrap itself import-safe for the node test
 * environment, which reaches it through the tab-provider contribution graph.
 */
async function loadMonaco(): Promise<typeof monaco> {
  const [{ loader }, monacoNamespace, editorWorker, cssWorker, htmlWorker, jsonWorker, tsWorker] =
    await Promise.all([
      import('@monaco-editor/react'),
      import('monaco-editor'),
      import('monaco-editor/esm/vs/editor/editor.worker?worker'),
      import('monaco-editor/esm/vs/language/css/css.worker?worker'),
      import('monaco-editor/esm/vs/language/html/html.worker?worker'),
      import('monaco-editor/esm/vs/language/json/json.worker?worker'),
      import('monaco-editor/esm/vs/language/typescript/ts.worker?worker'),
    ]);

  self.MonacoEnvironment = {
    getWorker(_workerId: string, label: string): Worker {
      switch (label) {
        case 'json':
          return new jsonWorker.default();
        case 'css':
        case 'scss':
        case 'less':
          return new cssWorker.default();
        case 'html':
        case 'handlebars':
        case 'razor':
          return new htmlWorker.default();
        case 'typescript':
        case 'javascript':
          return new tsWorker.default();
        default:
          return new editorWorker.default();
      }
    },
  };
  // Serve Monaco from the bundled package instead of the default CDN so the
  // editor works offline; loader.init() resolves with this instance.
  loader.config({ monaco: monacoNamespace });
  return loader.init();
}

/**
 * Shared Monaco bootstrap — the single entry point for loading Monaco,
 * defining themes, and configuring TypeScript support.
 *
 * Both EditorProvider (code editor) and StickyDiffEditor (diff editor) use this
 * instead of maintaining separate pools. Bootstrap is idempotent: subsequent
 * calls to init() return the same promise. The resolved instance is exposed via
 * globalThis.__monaco so module-level code (e.g. monaco-comment-manager) can
 * access it without importing the bootstrap directly.
 */
export const monacoBootstrap = {
  /** Load Monaco once, set up themes and TypeScript. Safe to call multiple times. */
  init(): Promise<typeof monaco> {
    if (initPromise) return initPromise;
    initPromise = (async () => {
      const m = await loadMonaco();
      instance = m;
      // oxlint-disable-next-line typescript/no-explicit-any
      (globalThis as any).__monaco = m;
      defineMonacoThemes(m as Parameters<typeof defineMonacoThemes>[0]);
      configureMonacoTypeScript(m);
      return m;
    })();
    return initPromise;
  },

  /** Returns the loaded Monaco namespace, or null if init() has not yet resolved. */
  getMonaco(): typeof monaco | null {
    return instance;
  },

  /** Update the active Monaco theme across all editor instances simultaneously. */
  setTheme(effectiveTheme: string): void {
    if (!instance) return;
    defineMonacoThemes(instance as Parameters<typeof defineMonacoThemes>[0]);
    instance.editor.setTheme(getMonacoTheme(effectiveTheme));
  },
};
