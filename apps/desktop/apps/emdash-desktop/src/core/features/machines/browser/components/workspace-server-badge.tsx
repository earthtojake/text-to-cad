import { Pill } from '@emdash/ui/react/components';
import type { HostServerState, HostServerStatus } from '@core/services/hosts/api';

const statusLabels: Record<HostServerStatus, string> = {
  'not-installed': 'Not found',
  stopped: 'Stopped',
  booting: 'Booting',
  'shutting-down': 'Shutting Down',
  healthy: 'Healthy',
  failed: 'Error',
};

function variantForStatus(status: HostServerStatus): {
  variant: 'neutral' | 'success' | 'info' | 'error';
  pulsing: boolean;
} {
  if (status === 'healthy') {
    return { variant: 'success', pulsing: false };
  }
  if (status === 'booting' || status === 'shutting-down') {
    return { variant: 'info', pulsing: true };
  }
  if (status === 'failed') {
    return { variant: 'error', pulsing: false };
  }
  return { variant: 'neutral', pulsing: false };
}

function labelForStatus(status: HostServerStatus, error: HostServerState['error']): string {
  if (status === 'healthy' && error !== undefined) return 'Running';
  return statusLabels[status];
}

function labelForError(code: string): string {
  switch (code) {
    case 'protocol-upgrade-client':
      return 'App update required';
    case 'protocol-upgrade-server':
      return 'Incompatible runtime';
    default:
      return 'Error';
  }
}

export function WorkspaceServerBadge({
  status,
  error,
}: {
  status: HostServerStatus;
  error?: HostServerState['error'];
}) {
  const { variant, pulsing } = variantForStatus(status);

  return (
    <>
      <Pill variant={variant} dot pulsing={pulsing}>
        {labelForStatus(status, error)}
      </Pill>
      {status !== 'failed' && error !== undefined && (
        <Pill variant="error" title={error.message}>
          {labelForError(error.code)}
        </Pill>
      )}
    </>
  );
}
