import { tmpdir } from 'node:os';
import { join } from 'node:path';

/**
 * Environment for every Python process the desktop runs against cadgen: model
 * runs, `cadgen` inspection doors, and the CAD Viewer server. The warm build
 * daemon and the content-addressed cache stay on their defaults; only bytecode
 * caching is disabled so a same-second recipe edit can never rerun stale
 * `.pyc` output.
 */
export function cadToolEnvironment(
  environment: NodeJS.ProcessEnv = process.env
): NodeJS.ProcessEnv {
  return {
    ...environment,
    PYTHONDONTWRITEBYTECODE: '1',
    PYTHONPYCACHEPREFIX: join(tmpdir(), `hardcore-cad-no-bytecode-${process.pid}`),
    PYTHONUNBUFFERED: '1',
  };
}
