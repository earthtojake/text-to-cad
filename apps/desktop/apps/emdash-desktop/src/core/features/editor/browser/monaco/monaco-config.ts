/**
 * Monaco Editor configuration for TypeScript/JavaScript support
 * Configures language services to match project's tsconfig.json
 */
import type * as monaco from 'monaco-editor';
import { log } from '@core/primitives/logging/browser/logger';

const DIAGNOSTICS_OPTIONS: monaco.typescript.DiagnosticsOptions = {
  // Monaco runs without the full project/type environment here, so semantic
  // errors are often misleading in the file editor.
  noSemanticValidation: true,
  noSyntaxValidation: false,
};

/**
 * Configure Monaco editor's TypeScript language services
 * @param monacoInstance - Monaco namespace
 */
export function configureMonacoTypeScript(monacoInstance: typeof monaco): void {
  try {
    configureTypeScriptDefaults(monacoInstance);
    configureJavaScriptDefaults(monacoInstance);
  } catch (error) {
    log.warn('Failed to configure Monaco TypeScript settings:', error);
  }
}

/**
 * Configure TypeScript language defaults
 */
function configureTypeScriptDefaults(monacoInstance: typeof monaco): void {
  const ts = monacoInstance.typescript;

  ts.typescriptDefaults.setCompilerOptions({
    target: ts.ScriptTarget.ES2020,
    lib: ['es2020', 'dom', 'dom.iterable'],
    allowJs: false,
    skipLibCheck: true,
    esModuleInterop: true,
    allowSyntheticDefaultImports: true,
    strict: true,
    forceConsistentCasingInFileNames: true,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.NodeJs,
    resolveJsonModule: true,
    isolatedModules: true,
    noEmit: true,
    jsx: ts.JsxEmit.ReactJSX,
    baseUrl: '.',
    paths: {
      '@/*': ['./src/renderer/*'],
      '@core/*': ['./src/core/*'],
      '@renderer/*': ['./src/renderer/*'],
      '#types/*': ['./src/types/*'],
      '#types': ['./src/types/index.ts'],
    },
    typeRoots: ['./node_modules/@types'],
    types: ['react', 'react-dom', 'node'],
  });
  ts.typescriptDefaults.setDiagnosticsOptions(DIAGNOSTICS_OPTIONS);
  ts.typescriptDefaults.setEagerModelSync(true);
}

/**
 * Configure JavaScript language defaults
 */
function configureJavaScriptDefaults(monacoInstance: typeof monaco): void {
  const ts = monacoInstance.typescript;

  ts.javascriptDefaults.setCompilerOptions({
    target: ts.ScriptTarget.ES2020,
    lib: ['es2020', 'dom', 'dom.iterable'],
    allowJs: true,
    checkJs: false,
    jsx: ts.JsxEmit.React,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.NodeJs,
  });
  ts.javascriptDefaults.setDiagnosticsOptions(DIAGNOSTICS_OPTIONS);
  ts.javascriptDefaults.setEagerModelSync(true);
}

/**
 * Configure Monaco editor instance options
 * @param editor - Monaco editor instance
 */
export function configureMonacoEditor(editor: monaco.editor.IStandaloneCodeEditor): void {
  editor.updateOptions({
    quickSuggestions: {
      other: true,
      comments: false,
      strings: true,
    },
    suggestOnTriggerCharacters: true,
    parameterHints: {
      enabled: true,
    },
    wordBasedSuggestions: 'off',
    suggest: {
      showKeywords: true,
      showSnippets: true,
      showClasses: true,
      showFunctions: true,
      showVariables: true,
    },
  });
}

/**
 * Add keyboard shortcuts to editor
 * @param editor - Monaco editor instance
 * @param monacoInstance - Monaco namespace
 * @param handlers - Keyboard shortcut handlers
 */
export function addMonacoKeyboardShortcuts(
  editor: monaco.editor.IStandaloneCodeEditor,
  monacoInstance: typeof monaco,
  handlers: {
    onSave?: () => void;
    onSaveAll?: () => void;
  }
): void {
  if (handlers.onSave) {
    editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, handlers.onSave);
  }

  if (handlers.onSaveAll) {
    editor.addCommand(
      monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyMod.Shift | monacoInstance.KeyCode.KeyS,
      handlers.onSaveAll
    );
  }
}
