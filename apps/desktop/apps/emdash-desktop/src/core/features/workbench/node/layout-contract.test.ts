import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Workbench layout-contract conformance checks.
 *
 * Durable encoding of the workbench state architecture end state
 * (`.scratch/workbench-state-architecture/spec.md` §End state, §Laws):
 * panel visibility is store-driven conditional rendering, pixel sizes belong
 * to the panel library alone, persistence goes through mementos, and nothing
 * programs the panels imperatively. These are content assertions with a
 * documented allowlist, not a style preference — a new match means either a
 * contract regression or a new legitimate exception that must be reviewed
 * and allowlisted with a reason.
 *
 * Scope: `apps/emdash-desktop/src` app code (test and story files excluded —
 * tests may simulate panel behavior). "Surface dirs" below are the workbench
 * chrome surfaces named by the spec: the workbench, tasks, and source-control
 * features plus the renderer layout shell.
 */

const SRC_ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../../..');

const SURFACE_DIRS = [
  'core/features/workbench/',
  'core/features/tasks/',
  'core/features/source-control/',
  'renderer/lib/layout/',
];

const wholeSrc = () => true;
const surfaceDirs = (relPath: string) => SURFACE_DIRS.some((dir) => relPath.startsWith(dir));

interface AllowlistEntry {
  /** Path relative to `apps/emdash-desktop/src`, forward slashes. */
  path: string;
  reason: string;
}

interface ContractCheck {
  name: string;
  /** Matched per line. */
  pattern: RegExp;
  scope: (relPath: string) => boolean;
  allowlist: AllowlistEntry[];
  rationale: string;
}

const checks: ContractCheck[] = [
  {
    name: 'no direct react-resizable-panels imports',
    pattern: /from\s+['"]react-resizable-panels|(?:require|import)\(['"]react-resizable-panels/,
    scope: wholeSrc,
    allowlist: [],
    rationale:
      'Consumers depend on @emdash/ui (Resizable, useCollapsiblePanelBinding, ' +
      'useResizableDefaultLayout), which deliberately does not re-export imperative panel ' +
      'handles. A direct import would reopen the imperative escape hatch.',
  },
  {
    name: 'no imperative panel programming',
    pattern: /ImperativePanel(?:Group)?Handle|\.setLayout\(|\.collapse\(\)|\.expand\(\)/,
    scope: wholeSrc,
    allowlist: [],
    rationale:
      'Visibility is store-driven conditional rendering; closed panels unmount. With zero ' +
      'programmatic writes nothing can echo, so no echo guards are needed anywhere.',
  },
  {
    name: 'no .resize() calls on workbench surfaces',
    pattern: /\.resize\(/,
    scope: surfaceDirs,
    allowlist: [],
    rationale:
      'Pixel sizes belong to the panel library alone; only user drags change them. xterm/PTY ' +
      '.resize() lives in the terminals/conversations features, outside these directories; a ' +
      'match here means panel programming (or misplaced terminal plumbing).',
  },
  {
    name: 'no display/hidden visibility toggling of workbench surfaces',
    pattern:
      /(?<!aria-)hidden=\{|(?<!aria-)\bhidden\s*\/?>|style=\{\{\s*display|\.style\.display\s*=/,
    scope: surfaceDirs,
    allowlist: [],
    rationale:
      'Workbench surface visibility must be conditional rendering, not display:none-style ' +
      'toggling: a display:none mount discards the panel defaultLayout. Tab keep-alive via ' +
      'visibility:hidden + inert (pane-content, browser/conversation/file tab providers) is a ' +
      'documented exception and lives outside these directories.',
  },
  {
    name: 'no ShowHide on workbench surfaces',
    pattern: /\bShowHide\b/,
    scope: surfaceDirs,
    allowlist: [],
    rationale:
      'ShowHide is display:none-based. Workbench chrome (sidebars, drawer, changes sections) ' +
      'must unmount when closed so panel layouts mount fresh from persisted defaults.',
  },
  {
    name: 'no onResize handlers',
    pattern: /\bonResize\b/,
    scope: wholeSrc,
    allowlist: [],
    rationale:
      'onResize is a measurement channel only and must never write to stores. No legitimate ' +
      'use exists in app code today; a genuine measurement-only use may be allowlisted with a ' +
      'reason after review.',
  },
  {
    name: 'no localStorage on workbench surfaces',
    pattern: /\blocalStorage\b|useLocalStorage/,
    scope: surfaceDirs,
    allowlist: [
      {
        path: 'core/features/tasks/contributions/browser/task-config/initial-conversation-section.tsx',
        reason:
          'New-conversation preferences (auto-approve, chat-ui opt-in) — user preferences, ' +
          'not layout state. Layout persistence goes through mementos.',
      },
      {
        path: 'core/features/tasks/browser/start-blank-chat.ts',
        reason:
          'Last-used agent provider — a user preference used to seed new chats, not layout ' +
          'state. Layout persistence still goes through mementos.',
      },
    ],
    rationale:
      'All layout state persists via mementos on the one hydration clock. localStorage layout ' +
      'persistence is retired; it bypasses the hydration gate and the persistence clock.',
  },
  {
    name: 'no localStorage passed as layout storage',
    pattern:
      /storage:\s*(?:window\.)?localStorage|createLayoutStorage\(\s*(?:window\.)?localStorage/,
    scope: wholeSrc,
    allowlist: [],
    rationale:
      'useResizableDefaultLayout defaults to localStorage when no storage is passed; the app ' +
      'must always inject the memento-backed LayoutStorage facade.',
  },
  {
    name: 'no retired sync/persistence identifiers',
    pattern:
      /TabPersistenceAdapter|zenModeSnapshotRef|programmaticRef|appliedExpanded|\bsetPaneSizes\b/,
    scope: wholeSrc,
    allowlist: [],
    rationale:
      'The hand-rolled store↔panel sync guards and the synchronous tab persistence adapter ' +
      'were deleted with the surface conversions (tickets 06–12). These names coming back ' +
      'means a retired pattern is being reintroduced.',
  },
];

function listSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('_') || entry.name === 'node_modules') continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...listSourceFiles(full));
      continue;
    }
    if (!/\.(ts|tsx)$/.test(entry.name)) continue;
    if (/\.(test|stories)\.(ts|tsx)$/.test(entry.name)) continue;
    files.push(full);
  }
  return files;
}

const sourceFiles = listSourceFiles(SRC_ROOT).map((file) => ({
  relPath: relative(SRC_ROOT, file).replaceAll('\\', '/'),
  lines: readFileSync(file, 'utf8').split('\n'),
}));

describe('workbench layout contract', () => {
  it('scans a plausible source tree', () => {
    // Guard against the walker silently scanning nothing (e.g. after a move).
    expect(sourceFiles.length).toBeGreaterThan(500);
    expect(sourceFiles.some((file) => surfaceDirs(file.relPath))).toBe(true);
  });

  for (const check of checks) {
    it(check.name, () => {
      const allowed = new Set(check.allowlist.map((entry) => entry.path));
      const violations: string[] = [];
      const matchedAllowlistPaths = new Set<string>();

      for (const file of sourceFiles) {
        if (!check.scope(file.relPath)) continue;
        file.lines.forEach((line, index) => {
          if (!check.pattern.test(line)) return;
          if (allowed.has(file.relPath)) {
            matchedAllowlistPaths.add(file.relPath);
            return;
          }
          violations.push(`${file.relPath}:${index + 1}  ${line.trim()}`);
        });
      }

      expect(
        violations,
        `Layout-contract violation (${check.name}).\n${check.rationale}\n` +
          'If this is a reviewed, legitimate exception, add an allowlist entry with a reason.'
      ).toEqual([]);

      const stale = check.allowlist.filter((entry) => !matchedAllowlistPaths.has(entry.path));
      expect(
        stale.map((entry) => entry.path),
        `Stale allowlist entries for "${check.name}" — the exception no longer matches; remove it.`
      ).toEqual([]);
    });
  }
});
