import { describe, expect, it } from 'vitest';
import { acpBootstrapStatusLabel, type AcpBootstrapPhase } from './acp-bootstrap-status';

describe('acpBootstrapStatusLabel', () => {
  it.each<[AcpBootstrapPhase, string]>([
    ['queued', 'Waiting to start agent…'],
    ['starting', 'Starting agent…'],
    ['retrying', 'Retrying agent…'],
    ['connecting', 'Connecting chat…'],
    ['history', 'Loading chat history…'],
  ])('maps %s to a clear user-facing status', (phase, label) => {
    expect(acpBootstrapStatusLabel(phase)).toBe(label);
  });
});
