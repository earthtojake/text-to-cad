import { claudeAdapter } from './impl/claude/adapter';
import { codexAdapter } from './impl/codex/adapter';

export const adapterAssets = [claudeAdapter, codexAdapter] as const;
