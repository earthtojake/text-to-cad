import type { Monaco } from '@monaco-editor/react';
import { cssColorToHex } from '@core/primitives/styling/browser/cssVars';

type MonacoColors = Record<string, string>;

/**
 * Reads all --monaco-* CSS custom properties from an element bearing the given
 * theme class, converts each value to a hex string, and returns a Monaco color
 * token map. Entries where the variable is not defined for that theme are
 * omitted.
 */
function readMonacoVarsForTheme(cssClass: 'emlight' | 'emdark'): MonacoColors {
  const el = document.createElement('div');
  el.className = cssClass;
  el.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none;';
  document.body.appendChild(el);
  const style = getComputedStyle(el);

  const get = (v: string) => style.getPropertyValue(v).trim();

  const mapping: Array<[string, string]> = [
    ['--monaco-bg', 'editor.background'],
    ['--monaco-fg', 'editor.foreground'],
    ['--monaco-line-highlight', 'editor.lineHighlightBackground'],
    ['--monaco-line-number', 'editorLineNumber.foreground'],
    ['--monaco-gutter', 'editorGutter.background'],
    ['--monaco-inserted-text-bg', 'diffEditor.insertedTextBackground'],
    ['--monaco-inserted-line-bg', 'diffEditor.insertedLineBackground'],
    ['--monaco-inserted-text-border', 'diffEditor.insertedTextBorder'],
    ['--monaco-removed-text-bg', 'diffEditor.removedTextBackground'],
    ['--monaco-removed-line-bg', 'diffEditor.removedLineBackground'],
    ['--monaco-removed-text-border', 'diffEditor.removedTextBorder'],
    ['--monaco-unchanged-region-bg', 'diffEditor.unchangedRegionBackground'],
    ['--monaco-diff-border', 'diffEditor.border'],
    ['--monaco-diff-diagonal-fill', 'diffEditor.diagonalFill'],
    ['--monaco-selection-bg', 'editor.selectionBackground'],
    ['--monaco-selection-fg', 'editor.selectionForeground'],
    ['--monaco-inactive-selection-bg', 'editor.inactiveSelectionBackground'],
  ];

  const colors: MonacoColors = {};
  for (const [cssVar, monacoToken] of mapping) {
    const value = get(cssVar);
    if (value) {
      colors[monacoToken] = cssColorToHex(value);
    }
  }

  el.remove();
  return colors;
}

export function defineMonacoThemes(monaco: Monaco): void {
  monaco.editor.defineTheme('custom-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [],
    colors: readMonacoVarsForTheme('emdark'),
  });

  monaco.editor.defineTheme('custom-light', {
    base: 'vs',
    inherit: true,
    rules: [],
    colors: readMonacoVarsForTheme('emlight'),
  });
}

export function getMonacoTheme(effectiveTheme: string): string {
  return effectiveTheme === 'emlight' ? 'custom-light' : 'custom-dark';
}
