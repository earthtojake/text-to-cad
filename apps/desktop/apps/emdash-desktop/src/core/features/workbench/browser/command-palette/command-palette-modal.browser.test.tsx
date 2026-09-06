import '@emdash/ui/style.css';
import { Command } from 'cmdk';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  definePaletteProviderCatalog,
  type PaletteProviderDef,
  type PaletteProviderMatch,
} from '@core/primitives/palette/api';
import { CommandPaletteView } from './command-palette-modal';

function match(id: string, title: string): PaletteProviderMatch {
  return { id, title, relevance: { band: 'exact', score: 1 } };
}

function rowProvider(
  options: Omit<PaletteProviderDef, 'minQueryLength' | 'render'> & {
    minQueryLength?: number;
  }
): PaletteProviderDef {
  return {
    minQueryLength: 1,
    render: ({ match: item, value, onSelect }) => (
      <Command.Item value={value} onSelect={onSelect}>
        {item.title}
      </Command.Item>
    ),
    ...options,
  };
}

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('CommandPaletteView', () => {
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

  it('shows keyword mode and returns to unified provider results when cleared', async () => {
    const commandSearch = vi.fn(() => [match('toggle-theme', 'Toggle Theme')]);
    const fileSearch = vi.fn(() => [match('theme-file', 'theme.ts')]);
    const catalog = definePaletteProviderCatalog([
      rowProvider({
        kind: 'commands',
        keyword: '@commands',
        search: commandSearch,
      }),
      rowProvider({
        kind: 'files',
        keyword: '@files',
        minQueryLength: 2,
        search: fileSearch,
      }),
    ]);
    const onClose = vi.fn();

    await act(async () => {
      root.render(<CommandPaletteView providerCatalog={catalog} context={{}} onClose={onClose} />);
    });
    const input = host.querySelector<HTMLInputElement>('input')!;
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setValue?.call(input, '@commands theme');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    await vi.waitFor(() => {
      expect(
        host.querySelector<HTMLButtonElement>('button[aria-label="Clear @commands mode"]')
      ).not.toBeNull();
      expect(host.textContent).toContain('Toggle Theme');
    });
    expect(host.textContent).not.toContain('theme.ts');
    expect(commandSearch).toHaveBeenLastCalledWith({ query: 'theme', context: {} });
    expect(fileSearch).not.toHaveBeenCalled();

    await act(async () => {
      host.querySelector<HTMLButtonElement>('button[aria-label="Clear @commands mode"]')!.click();
    });
    await vi.waitFor(() => expect(host.textContent).toContain('theme.ts'));
    expect(fileSearch).toHaveBeenLastCalledWith({ query: 'theme', context: {} });

    await act(async () => {
      [...host.querySelectorAll<HTMLElement>('[cmdk-item]')]
        .find((item) => item.textContent === 'Toggle Theme')!
        .click();
    });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('removes stale rows as soon as the input changes', async () => {
    let resolveNext: ((matches: PaletteProviderMatch[]) => void) | undefined;
    const nextResults = new Promise<PaletteProviderMatch[]>((resolve) => {
      resolveNext = resolve;
    });
    const catalog = definePaletteProviderCatalog([
      rowProvider({
        kind: 'commands',
        keyword: '@commands',
        search: ({ query }) => (query === 'old' ? [match('old', 'Old result')] : nextResults),
      }),
    ]);
    const onClose = vi.fn();

    await act(async () => {
      root.render(<CommandPaletteView providerCatalog={catalog} context={{}} onClose={onClose} />);
    });
    const input = host.querySelector<HTMLInputElement>('input')!;
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;

    await act(async () => {
      setValue?.call(input, 'old');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await vi.waitFor(() => expect(host.textContent).toContain('Old result'));

    await act(async () => {
      setValue?.call(input, 'new');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    expect(host.textContent).not.toContain('Old result');
    await act(async () => {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    });
    expect(onClose).not.toHaveBeenCalled();

    resolveNext?.([match('new', 'New result')]);
    await vi.waitFor(() => expect(host.textContent).toContain('New result'));
  });

  it('supports every provider keyword mode', async () => {
    const searches = {
      commands: vi.fn(() => [match('commands-result', 'Commands result')]),
      tasks: vi.fn(() => [match('tasks-result', 'Tasks result')]),
      conversations: vi.fn(() => [match('conversations-result', 'Conversations result')]),
      files: vi.fn(() => [match('files-result', 'Files result')]),
      projects: vi.fn(() => [match('projects-result', 'Projects result')]),
    };
    const catalog = definePaletteProviderCatalog([
      rowProvider({ kind: 'commands', keyword: '@commands', search: searches.commands }),
      rowProvider({ kind: 'tasks', keyword: '@tasks', search: searches.tasks }),
      rowProvider({
        kind: 'conversations',
        keyword: '@conversations',
        search: searches.conversations,
      }),
      rowProvider({
        kind: 'files',
        keyword: '@files',
        minQueryLength: 2,
        search: searches.files,
      }),
      rowProvider({ kind: 'projects', keyword: '@projects', search: searches.projects }),
    ]);

    await act(async () => {
      root.render(<CommandPaletteView providerCatalog={catalog} context={{}} onClose={vi.fn()} />);
    });
    const input = host.querySelector<HTMLInputElement>('input')!;
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;

    for (const [index, [kind, keyword]] of (
      [
        ['commands', '@commands'],
        ['tasks', '@tasks'],
        ['conversations', '@conversations'],
        ['files', '@files'],
        ['projects', '@projects'],
      ] as const
    ).entries()) {
      if (index > 0) {
        await act(async () => {
          host.querySelector<HTMLButtonElement>('button[aria-label^="Clear @"]')?.click();
        });
      }
      await act(async () => {
        setValue?.call(input, `${keyword} xx`);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
      await vi.waitFor(() => expect(host.textContent).toContain(`${capitalize(kind)} result`));
      expect(host.querySelectorAll('[cmdk-item]')).toHaveLength(1);
      expect(searches[kind]).toHaveBeenLastCalledWith({ query: 'xx', context: {} });
    }
  });

  it('renders provider-owned idle results for app, project, and task contexts', async () => {
    const catalog = definePaletteProviderCatalog([
      rowProvider({
        kind: 'commands',
        keyword: '@commands',
        idle: (context) => [
          match(
            'action',
            context.taskId ? 'Task actions' : context.projectId ? 'Project actions' : 'App actions'
          ),
        ],
        search: () => [],
      }),
      rowProvider({
        kind: 'tasks',
        keyword: '@tasks',
        idle: (context) => [
          match('recent-task', 'Recent tasks'),
          ...(context.taskId ? [match('notification', 'Task notifications')] : []),
        ],
        search: () => [],
      }),
      rowProvider({
        kind: 'conversations',
        keyword: '@conversations',
        idle: (context) =>
          context.taskId ? [match('recent-conversation', 'Recent conversations')] : [],
        search: () => [],
      }),
      rowProvider({
        kind: 'files',
        keyword: '@files',
        minQueryLength: 2,
        search: () => [],
      }),
      rowProvider({
        kind: 'projects',
        keyword: '@projects',
        idle: (context) => (context.taskId ? [] : [match('other-project', 'Other projects')]),
        search: () => [],
      }),
    ]);

    await act(async () => {
      root.render(<CommandPaletteView providerCatalog={catalog} context={{}} onClose={vi.fn()} />);
    });
    await vi.waitFor(() => expect(host.textContent).toContain('App actions'));
    expect(host.textContent).toContain('Recent tasks');
    expect(host.textContent).toContain('Other projects');
    expect(host.textContent).not.toContain('Recent conversations');

    await act(async () => {
      root.render(
        <CommandPaletteView
          providerCatalog={catalog}
          context={{ projectId: 'project-1' }}
          onClose={vi.fn()}
        />
      );
    });
    await vi.waitFor(() => expect(host.textContent).toContain('Project actions'));

    await act(async () => {
      root.render(
        <CommandPaletteView
          providerCatalog={catalog}
          context={{ projectId: 'project-1', taskId: 'task-1' }}
          onClose={vi.fn()}
        />
      );
    });
    await vi.waitFor(() => expect(host.textContent).toContain('Task actions'));
    expect(host.textContent).toContain('Task notifications');
    expect(host.textContent).toContain('Recent conversations');
    expect(host.textContent).not.toContain('Other projects');
  });

  it('preserves the selected row when stronger async results arrive', async () => {
    let resolveFiles: ((matches: PaletteProviderMatch[]) => void) | undefined;
    const fileResults = new Promise<PaletteProviderMatch[]>((resolve) => {
      resolveFiles = resolve;
    });
    const catalog = definePaletteProviderCatalog([
      rowProvider({
        kind: 'commands',
        keyword: '@commands',
        search: () => [match('first', 'First command'), match('second', 'Second command')],
      }),
      rowProvider({
        kind: 'files',
        keyword: '@files',
        minQueryLength: 2,
        search: () => fileResults,
      }),
    ]);

    await act(async () => {
      root.render(<CommandPaletteView providerCatalog={catalog} context={{}} onClose={vi.fn()} />);
    });
    const input = host.querySelector<HTMLInputElement>('input')!;
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    await act(async () => {
      setValue?.call(input, 'go');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await vi.waitFor(() => expect(host.textContent).toContain('Second command'));

    await act(async () => {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    });
    expect(host.querySelector('[cmdk-item][aria-selected="true"]')?.textContent).toBe(
      'Second command'
    );

    resolveFiles?.([
      {
        id: 'file',
        title: 'Best file',
        relevance: { band: 'exact', score: 2 },
      },
    ]);
    await vi.waitFor(() => expect(host.textContent).toContain('Best file'));
    expect(
      [...host.querySelectorAll<HTMLElement>('[cmdk-item]')].map((item) => item.textContent)
    ).toEqual(['Best file', 'First command', 'Second command']);
    expect(host.querySelector('[cmdk-item][aria-selected="true"]')?.textContent).toBe(
      'Second command'
    );
  });
});

function capitalize(value: string): string {
  return `${value[0]?.toUpperCase()}${value.slice(1)}`;
}
