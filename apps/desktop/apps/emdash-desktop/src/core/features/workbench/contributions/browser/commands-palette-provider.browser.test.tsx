import { Command } from 'cmdk';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { settingsCommand } from '@core/features/workbench/contributions/commands';
import { defineCommandPaletteItem } from '@core/primitives/palette/api';
import type { BoundCommand } from '@core/primitives/view-scopes/api';
import { commandsPaletteProviderDef, type CommandPaletteMatch } from './commands-palette-provider';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('commands palette row', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('executes an enabled command and dismisses the palette', async () => {
    const execute = vi.fn(() => true);
    const dismiss = vi.fn();
    const match: CommandPaletteMatch = {
      id: settingsCommand.id,
      item: defineCommandPaletteItem({ command: settingsCommand }),
      bound: {
        def: settingsCommand,
        availability: { kind: 'enabled' },
        presentation: undefined,
        execute: vi.fn(),
      } satisfies BoundCommand<typeof settingsCommand>,
      chord: null,
      title: settingsCommand.title,
      subtitle: settingsCommand.description,
      relevance: { band: 'exact', score: 1 },
      execute,
    };
    const Renderer = commandsPaletteProviderDef.render;

    await act(async () => {
      root.render(
        <Command>
          <Renderer match={match} value={`commands:${match.id}`} onSelect={dismiss} />
        </Command>
      );
    });
    const row = host.querySelector<HTMLElement>('[cmdk-item]');
    expect(row?.textContent).toContain(settingsCommand.title);

    await act(async () => row?.click());

    expect(execute).toHaveBeenCalledOnce();
    expect(dismiss).toHaveBeenCalledOnce();
    expect(dismiss.mock.invocationCallOrder[0]).toBeLessThan(execute.mock.invocationCallOrder[0]!);
  });

  it('shows a disabled reason and does not select the command', async () => {
    const execute = vi.fn(() => false);
    const dismiss = vi.fn();
    const match: CommandPaletteMatch = {
      id: settingsCommand.id,
      item: defineCommandPaletteItem({ command: settingsCommand }),
      bound: {
        def: settingsCommand,
        availability: { kind: 'disabled', reason: 'Settings are unavailable' },
        presentation: undefined,
        execute: vi.fn(),
      } satisfies BoundCommand<typeof settingsCommand>,
      chord: null,
      title: settingsCommand.title,
      subtitle: settingsCommand.description,
      disabledReason: 'Settings are unavailable',
      relevance: { band: 'exact', score: 1 },
      execute,
    };
    const Renderer = commandsPaletteProviderDef.render;

    await act(async () => {
      root.render(
        <Command>
          <Renderer match={match} value={`commands:${match.id}`} onSelect={dismiss} />
        </Command>
      );
    });
    const row = host.querySelector<HTMLElement>('[cmdk-item]');
    expect(row?.getAttribute('aria-disabled')).toBe('true');
    expect(row?.textContent).toContain('Settings are unavailable');

    await act(async () => row?.click());

    expect(execute).not.toHaveBeenCalled();
    expect(dismiss).not.toHaveBeenCalled();
  });
});
