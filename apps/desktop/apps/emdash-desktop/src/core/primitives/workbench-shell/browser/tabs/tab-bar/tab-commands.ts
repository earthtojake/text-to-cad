import type React from 'react';

/**
 * A single actionable entry in a tab context menu (close, rename, …).
 * Renderer-local type — not part of the engine authoring contract.
 */
export interface TabCommand {
  id: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  /** Grouping key for separator placement. */
  group?: 'close' | (string & {});
  /**
   * Shortcut hint from a contributed command or a raw chord getter.
   */
  shortcut?: { readonly commandId: string } | { readonly chord: () => string | undefined };
  /** Hides the command when false (default: always visible). */
  isAvailable?(): boolean;
  run(): void | Promise<void>;
}
