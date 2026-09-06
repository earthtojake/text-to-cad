import { Command } from 'cmdk';
import { COMMAND_PALETTE_CATALOG } from '@core/manifests/shared/command-palette-catalog';
import type { Chord } from '@core/primitives/keybindings/api';
import { keybindingService } from '@core/primitives/keybindings/browser';
import { Shortcut } from '@core/primitives/keybindings/browser/shortcut';
import {
  matchPaletteText,
  type CommandPaletteCatalog,
  type CommandPaletteItemDef,
  type PaletteProviderDef,
  type PaletteProviderMatch,
  type PaletteProviderRenderProps,
} from '@core/primitives/palette/api';
import { cn } from '@core/primitives/styling/browser/cn';
import type { BoundCommand } from '@core/primitives/view-scopes/api';
import { scopes, type ViewScopes } from '@core/primitives/view-scopes/browser';
import { getCommandIcon } from '../../browser/command-palette/command-icons';
import { PALETTE_ITEM_CLASS } from '../../browser/command-palette/palette-item-styles';

const APP_IDLE_COMMAND_IDS = ['app.newProject', 'app.settings'] as const;
const PROJECT_IDLE_COMMAND_IDS = ['app.newTask', 'app.settings'] as const;
const TASK_IDLE_COMMAND_IDS = [
  'task.newConversation',
  'task.sidebarChanges',
  'task.sidebarFiles',
  'task.sidebarConversations',
  'task.toggleTerminalDrawer',
] as const;

export interface CommandPaletteMatch extends PaletteProviderMatch {
  readonly item: CommandPaletteItemDef;
  readonly bound: BoundCommand;
  readonly chord: Chord | null;
  readonly disabledReason?: string;
  execute(): boolean;
}

export interface CommandsPaletteProviderOptions {
  readonly catalog: CommandPaletteCatalog<readonly CommandPaletteItemDef[]>;
  readonly viewScopes: Pick<ViewScopes, 'getActiveCommand'>;
  readonly chordFor: (commandId: string) => Chord | null;
}

function CommandPaletteProviderRow({
  match,
  value,
  onSelect,
}: PaletteProviderRenderProps<CommandPaletteMatch>) {
  const icon = match.bound.presentation?.icon ?? match.item.command.icon;
  const Icon = getCommandIcon(icon);
  const disabled = match.disabledReason !== undefined;
  const subtitle = match.disabledReason ?? match.subtitle;

  return (
    <Command.Item
      value={value}
      onSelect={() => {
        if (match.bound.availability.kind !== 'enabled') return;
        onSelect();
        match.execute();
      }}
      disabled={disabled}
      title={match.disabledReason}
      className={cn(PALETTE_ITEM_CLASS, 'group', disabled && 'cursor-not-allowed opacity-50')}
    >
      {Icon && <Icon size={14} className="shrink-0 text-foreground/40" />}
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate">{match.title}</span>
        {subtitle && <span className="truncate text-xs text-foreground/40">{subtitle}</span>}
      </span>
      {match.chord && <Shortcut hotkey={match.chord} variant="keycaps" />}
    </Command.Item>
  );
}

export function createCommandsPaletteProvider({
  catalog,
  viewScopes,
  chordFor,
}: CommandsPaletteProviderOptions): PaletteProviderDef {
  const resolve = (item: CommandPaletteItemDef): CommandPaletteMatch | undefined => {
    const bound = viewScopes.getActiveCommand(item.command, { belowActiveCapture: true });
    if (!bound || bound.availability.kind === 'hidden') return undefined;

    const presentation = bound.presentation;
    const availability = bound.availability;
    return {
      id: item.command.id,
      item,
      bound,
      title: presentation?.title ?? item.command.title,
      subtitle: presentation?.description ?? item.command.description,
      chord: chordFor(item.command.id),
      disabledReason: availability.kind === 'disabled' ? availability.reason : undefined,
      relevance: { band: 'fuzzy', score: 0 },
      execute: () => {
        if (bound.availability.kind !== 'enabled') return false;
        bound.execute(undefined, 'palette');
        return true;
      },
    };
  };

  return {
    kind: 'commands',
    keyword: '@commands',
    minQueryLength: 1,
    idle: (context) => {
      const commandIds = context.taskId
        ? TASK_IDLE_COMMAND_IDS
        : context.projectId
          ? PROJECT_IDLE_COMMAND_IDS
          : APP_IDLE_COMMAND_IDS;
      return commandIds.flatMap((commandId) => {
        const item = catalog.byCommandId(commandId);
        if (!item) return [];
        const match = resolve(item);
        return match ? [match] : [];
      });
    },
    search: ({ query }) =>
      catalog.items.flatMap((item) => {
        const match = resolve(item);
        if (!match) return [];
        const relevance = matchPaletteText(query, {
          primary: [item.command.title, match.title, ...(item.aliases ?? [])],
          secondary: [item.command.description, match.subtitle].filter(
            (value): value is string => value !== undefined
          ),
        });
        return relevance ? [{ ...match, relevance }] : [];
      }),
    render: ({ match, value, onSelect }) => (
      <CommandPaletteProviderRow
        match={match as CommandPaletteMatch}
        value={value}
        onSelect={onSelect}
      />
    ),
  };
}

export const commandsPaletteProviderDef = createCommandsPaletteProvider({
  catalog: COMMAND_PALETTE_CATALOG,
  viewScopes: scopes,
  chordFor: (commandId) => keybindingService.chordFor(commandId),
});

export const workbenchCommandsPaletteProviderDefs = [commandsPaletteProviderDef] as const;
