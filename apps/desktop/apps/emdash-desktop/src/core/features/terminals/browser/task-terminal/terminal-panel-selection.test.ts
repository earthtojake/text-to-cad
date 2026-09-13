import { describe, expect, it } from 'vitest';
import { resolveTerminalPanelActiveItem } from './terminal-panel-selection';

describe('resolveTerminalPanelActiveItem', () => {
  it('keeps a selected lifecycle script when it is still available', () => {
    expect(
      resolveTerminalPanelActiveItem({
        requestedActiveItem: { kind: 'script', id: 'script-lifecycle-run' },
        activeTerminalId: 'terminal-1',
        terminalIds: ['terminal-1'],
        scriptIds: ['script-lifecycle-run'],
      })
    ).toEqual({ kind: 'script', id: 'script-lifecycle-run' });
  });

  it('uses a requested terminal even when the drawer was previously showing a lifecycle script', () => {
    expect(
      resolveTerminalPanelActiveItem({
        requestedActiveItem: { kind: 'terminal', id: 'terminal-2' },
        activeTerminalId: 'terminal-2',
        terminalIds: ['terminal-1', 'terminal-2'],
        scriptIds: ['script-lifecycle-run'],
      })
    ).toEqual({ kind: 'terminal', id: 'terminal-2' });
  });

  it('falls back to the active terminal when the requested item is gone', () => {
    expect(
      resolveTerminalPanelActiveItem({
        requestedActiveItem: { kind: 'script', id: 'script-lifecycle-setup' },
        activeTerminalId: 'terminal-1',
        terminalIds: ['terminal-1'],
        scriptIds: ['script-lifecycle-run'],
      })
    ).toEqual({ kind: 'terminal', id: 'terminal-1' });
  });

  it('falls back to the active terminal when no item is requested', () => {
    expect(
      resolveTerminalPanelActiveItem({
        requestedActiveItem: undefined,
        activeTerminalId: 'terminal-1',
        terminalIds: ['terminal-1'],
        scriptIds: ['script-lifecycle-run'],
      })
    ).toEqual({ kind: 'terminal', id: 'terminal-1' });
  });

  it('falls back to the first script when no item is requested and no active terminal exists', () => {
    expect(
      resolveTerminalPanelActiveItem({
        requestedActiveItem: undefined,
        activeTerminalId: undefined,
        terminalIds: [],
        scriptIds: ['script-lifecycle-run'],
      })
    ).toEqual({ kind: 'script', id: 'script-lifecycle-run' });
  });
});
