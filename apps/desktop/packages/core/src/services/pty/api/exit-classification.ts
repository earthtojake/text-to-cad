import type { PtyExitInfo } from './types';

export function isUnexpectedPtyExit({ exitCode, signal }: PtyExitInfo): boolean {
  return exitCode !== 0 || signal !== null;
}
