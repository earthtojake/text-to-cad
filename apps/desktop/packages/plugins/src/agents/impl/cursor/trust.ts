import type {
  ITrustBehavior,
  PluginFs,
  TrustContext,
} from '@emdash/core/services/agent-plugins/api/plugins';

export function buildCursorTrustBehavior(): ITrustBehavior {
  return {
    async trustWorkspace(fs: PluginFs, ctx: TrustContext): Promise<void> {
      const markerPath = [
        '.cursor',
        'projects',
        slugifyPath(ctx.workspacePath),
        '.workspace-trusted',
      ].join('/');

      if (await fs.exists(markerPath)) return;

      await fs.write(
        markerPath,
        JSON.stringify(createTrustMarker(ctx.workspacePath), null, 2) + '\n'
      );
    },
  };
}

function slugifyPath(value: string): string {
  return value
    .replace(/[^a-zA-Z0-9]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function createTrustMarker(workspacePath: string): Record<string, string> {
  return {
    trustedAt: new Date().toISOString(),
    workspacePath,
    trustMethod: 'emdash-auto-trust',
  };
}
