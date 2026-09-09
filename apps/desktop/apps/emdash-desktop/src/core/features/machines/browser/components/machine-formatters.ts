import type { ConnectionState, SshConfig } from '@core/primitives/ssh/api';

export function authLabel(connection: SshConfig): string {
  switch (connection.authType) {
    case 'password':
      return 'Password';
    case 'key':
      return connection.privateKeyPath ? `SSH key ${connection.privateKeyPath}` : 'SSH key';
    case 'agent':
      return 'SSH agent';
  }
}

export function stateLabel(state: ConnectionState): string {
  switch (state) {
    case 'connected':
      return 'Connected';
    case 'connecting':
      return 'Connecting';
    case 'reconnecting':
      return 'Reconnecting';
    case 'error':
      return 'Error';
    case 'disconnected':
      return 'Disconnected';
  }
}

export function projectUsageText(projects: Array<{ id: string; name: string }>): string {
  if (projects.length === 0) return 'No projects';
  if (projects.length === 1) return projects[0].name;
  return `${projects.length} projects`;
}

export function projectUsageNamesText(
  projects: Array<{ id: string; name: string }>,
  visibleCount = 3
): string | null {
  if (projects.length <= 1) return null;

  const visibleProjects = projects.slice(0, visibleCount);
  const remainingCount = projects.length - visibleProjects.length;
  const visibleNames = visibleProjects.map((project) => project.name).join(', ');

  if (remainingCount === 0) return visibleNames;
  return `${visibleNames}, +${remainingCount} more`;
}
