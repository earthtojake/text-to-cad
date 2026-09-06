import { formatCommandOutputTail } from '@emdash/core/primitives/host-dependencies/api';
import type { HostDependencyError } from '@emdash/core/primitives/host-dependencies/api';

export function getHostDependencyErrorMessage(error: HostDependencyError): string {
  switch (error.type) {
    case 'unknown-dependency':
      return `Unknown dependency: ${error.id}`;
    case 'missing':
      return `Dependency is missing: ${error.id}`;
    case 'stale-selection':
      return `Selected path no longer exists: ${error.path}`;
    case 'invalid-selection':
      return error.message;
    case 'no-install-command':
      return `No install command is available for ${error.id}.`;
    case 'not-detected-after-install':
      return `Installed ${error.id}, but the binary was not detected on PATH.`;
    case 'no-update-command':
      return `No update command is available for ${error.id}.`;
    case 'installer-missing':
      return `The installer \`${error.tool}\` is not installed on this machine, so ${error.id} cannot be installed. Install \`${error.tool}\` or choose a different install method.`;
    case 'permission-denied':
      return error.message;
    case 'command-failed': {
      const tail = formatCommandOutputTail(error.output);
      return tail ? `${error.message}\n${tail}` : error.message;
    }
    case 'io':
      return error.message;
  }
}
