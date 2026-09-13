import { readdirSync, readFileSync } from 'node:fs';
import { THEME_MANIFEST } from '@emdash/theme/manifest';
import { describe, expect, it } from 'vitest';
// This convergence test reads generated files from disk, so it lives in the
// node surface even though the constants under test are browser code.
import {
  THEME_CLASS_DARK,
  THEME_CLASS_LIGHT,
  THEME_CLASSES,
  THEME_STORAGE_KEY,
} from '../browser/theme-classes';

function manifestClass(id: string): string {
  const entry = THEME_MANIFEST.find((e) => e.id === id);
  if (!entry) throw new Error(`THEME_MANIFEST has no theme with id "${id}"`);
  return entry.selector.replace(/^\./, '');
}

function rendererSourceFiles(directory: URL): URL[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(entry.isDirectory() ? `${entry.name}/` : entry.name, directory);
    if (entry.isDirectory()) return rendererSourceFiles(child);
    return entry.name.endsWith('.tsx') ? [child] : [];
  });
}

describe('theme class-name convergence with @emdash/theme', () => {
  // The app relies on its theme classes being the exact class names the
  // generated @emdash/theme selectors target (.emlight/.emdark). One classList
  // write must flip both the app palette and the --em-* palette. A rename on
  // either side silently splits the two systems — these tests are the guard.
  it('app light/dark classes equal the THEME_MANIFEST selectors', () => {
    expect(THEME_CLASS_LIGHT).toBe(manifestClass('light'));
    expect(THEME_CLASS_DARK).toBe(manifestClass('dark'));
    expect(THEME_CLASSES).toEqual([THEME_CLASS_LIGHT, THEME_CLASS_DARK]);
  });

  it('index.html pre-paint script uses the same class names and storage key', () => {
    // The inline script cannot import modules, so it hardcodes the literals.
    const html = readFileSync(new URL('../../../../renderer/index.html', import.meta.url), 'utf8');
    expect(html).toContain(`'${THEME_CLASS_LIGHT}'`);
    expect(html).toContain(`'${THEME_CLASS_DARK}'`);
    expect(html).toContain(`localStorage.getItem('${THEME_STORAGE_KEY}')`);
  });

  it('keeps generated utilities and shared controls on the same nonzero radius ladder', () => {
    const utilityCss = readFileSync(
      new URL('../../../../renderer/index.css', import.meta.url),
      'utf8'
    );
    const sharedCss = readFileSync(
      new URL('../../../../renderer/design-system.css', import.meta.url),
      'utf8'
    );
    const roles = [
      ['xs', '4px'],
      ['sm', '6px'],
      ['md', '8px'],
      ['lg', '10px'],
      ['xl', '14px'],
      ['2xl', '20px'],
    ] as const;

    for (const [role, value] of roles) {
      expect(utilityCss).toContain(`--radius-${role}: var(--hc-radius-${role}, ${value});`);
      expect(sharedCss).toContain(`--hc-radius-${role}: ${value};`);
      expect(sharedCss).toContain(`--radius-${role}: var(--hc-radius-${role});`);
      expect(sharedCss).toContain(`--em-radius-${role}: var(--hc-radius-${role});`);
    }

    expect(utilityCss).toContain('--radius-full: var(--hc-radius-full, 9999px);');
    expect(sharedCss).toContain('--hc-radius-full: 9999px;');
    expect(sharedCss).toContain('--em-radius-full: var(--hc-radius-full);');
    expect(utilityCss).toContain('border-radius: var(--hc-radius-full, 9999px);');
    expect(utilityCss).toContain('border-radius: var(--hc-radius-sm, 6px);');
  });

  it('keeps the editable design-system file as the final visual token authority', () => {
    const rendererEntry = readFileSync(
      new URL('../../../../renderer/main.tsx', import.meta.url),
      'utf8'
    );
    const sharedCss = readFileSync(
      new URL('../../../../renderer/design-system.css', import.meta.url),
      'utf8'
    );

    expect(rendererEntry.indexOf("import './design-system.css';")).toBeGreaterThan(
      rendererEntry.indexOf("import './index.css';")
    );
    expect(sharedCss).toContain('--font-sans:');
    expect(sharedCss).toContain('--font-mono:');
    expect(sharedCss).toContain('--em-text-sm: 13px;');
    expect(sharedCss).toContain('--em-shadow-sm:');
    expect(sharedCss).toContain('--em-surface-base-hover:');
    expect(sharedCss).toContain('--chat-fg: var(--foreground);');
    expect(sharedCss).toContain('--chat-code-inline-bg: color-mix(');
    expect(sharedCss).toContain('--hc-cad-scene:');
    expect(sharedCss).toContain('--hc-cad-scene-grid:');
  });

  it('keeps product labels and destructive hover states on semantic tokens', () => {
    const sources = rendererSourceFiles(new URL('../../../../', import.meta.url));
    for (const source of sources) {
      const contents = readFileSync(source, 'utf8');
      expect(contents, source.pathname).not.toMatch(/text-\[(?:10|11)px\]/);
      expect(contents, source.pathname).not.toContain('hover:bg-red-500 hover:text-white');
    }
  });
});
