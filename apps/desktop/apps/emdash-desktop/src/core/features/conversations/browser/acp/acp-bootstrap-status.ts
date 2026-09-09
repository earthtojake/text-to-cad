import type { AcpStartupPhase } from './acp-startup-coordinator';

export type AcpBootstrapPhase = AcpStartupPhase | 'history';

export function acpBootstrapStatusLabel(phase: AcpBootstrapPhase): string {
  switch (phase) {
    case 'queued':
      return 'Waiting to start agent…';
    case 'starting':
      return 'Starting agent…';
    case 'retrying':
      return 'Retrying agent…';
    case 'connecting':
      return 'Connecting chat…';
    case 'history':
      return 'Loading chat history…';
  }
}
