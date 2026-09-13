import { join, normalize, sep } from 'node:path';
import { net, protocol } from 'electron';
import { APP_NAME_LOWER } from '@core/primitives/app-identity/api/app-identity';

export const APP_SCHEME = 'app';
export const APP_ORIGIN = `${APP_SCHEME}://${APP_NAME_LOWER}`;

export function registerAppScheme(): void {
  protocol.registerSchemesAsPrivileged([
    {
      scheme: APP_SCHEME,
      privileges: {
        standard: true,
        secure: true,
        supportFetchAPI: true,
        corsEnabled: true,
        // Let Blink persist V8 code cache for app:// scripts, so repeat
        // launches skip recompiling the renderer bundle.
        codeCache: true,
      },
    },
  ]);
}

export function setupAppProtocol(rendererRoot: string): void {
  const root = normalize(rendererRoot);

  protocol.handle(APP_SCHEME, async (request) => {
    const { pathname } = new URL(request.url);
    const relPath = decodeURIComponent(pathname).replace(/^\/+/, '');
    const resolved = normalize(join(root, relPath || 'index.html'));

    if (!resolved.startsWith(root + sep) && resolved !== root) {
      return new Response(null, { status: 403 });
    }

    try {
      return await net.fetch(`file://${resolved}`);
    } catch {
      return net.fetch(`file://${join(root, 'index.html')}`);
    }
  });
}
