import { Command } from 'cmdk';
import { X } from 'lucide-react';
import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { PALETTE_PROVIDER_CATALOG } from '@core/manifests/browser/palette-provider-catalog';
import { Shortcut } from '@core/primitives/keybindings/browser/shortcut';
import { defineModal } from '@core/primitives/modals/react';
import {
  PaletteController,
  type PaletteContext,
  type PaletteProviderCatalog,
  type PaletteProviderDef,
  type PaletteResult,
} from '@core/primitives/palette/api';
import { cn } from '@core/primitives/styling/browser/cn';

interface CommandPaletteProps {
  projectId?: string;
  taskId?: string;
  workspaceId?: string;
}

interface InputChrome {
  readonly value: string;
  readonly keyword?: string;
}

interface CommandPaletteViewProps {
  readonly context: PaletteContext;
  readonly providerCatalog: PaletteProviderCatalog<readonly PaletteProviderDef[]>;
  readonly onClose: () => void;
}

const GROUP_CLASS = cn(
  '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5',
  '[&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium',
  '[&_[cmdk-group-heading]]:text-foreground/50'
);

function getInputChrome(
  input: string,
  providerCatalog: PaletteProviderCatalog<readonly PaletteProviderDef[]>
): InputChrome {
  const trimmed = input.trimStart();
  const separator = trimmed.search(/\s/);
  const token = separator === -1 ? trimmed : trimmed.slice(0, separator);
  const provider = providerCatalog.byKeyword(token);
  if (!provider) return { value: input };
  return {
    value: separator === -1 ? '' : trimmed.slice(separator).trimStart(),
    keyword: provider.keyword,
  };
}

function PaletteResultRow({ result, onSelect }: { result: PaletteResult; onSelect: () => void }) {
  const Renderer = result.provider.render;
  return <Renderer match={result.match} value={result.identity} onSelect={onSelect} />;
}

function PaletteResults({
  results,
  onSelect,
}: {
  results: readonly PaletteResult[];
  onSelect: () => void;
}) {
  const rows: React.ReactNode[] = [];
  let index = 0;

  while (index < results.length) {
    const result = results[index];
    const section = result?.match.section;
    if (!result) break;
    if (!section) {
      rows.push(<PaletteResultRow key={result.identity} result={result} onSelect={onSelect} />);
      index += 1;
      continue;
    }

    let end = index + 1;
    while (end < results.length && results[end]?.match.section === section) end += 1;
    rows.push(
      <Command.Group key={`${section}:${index}`} heading={section} className={GROUP_CLASS}>
        {results.slice(index, end).map((sectionResult) => (
          <PaletteResultRow
            key={sectionResult.identity}
            result={sectionResult}
            onSelect={onSelect}
          />
        ))}
      </Command.Group>
    );
    index = end;
  }

  return rows;
}

export function CommandPaletteView({
  context: contextInput,
  providerCatalog,
  onClose,
}: CommandPaletteViewProps) {
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const controller = useMemo(() => new PaletteController(providerCatalog), [providerCatalog]);
  const context = useMemo(
    () => ({
      projectId: contextInput.projectId,
      taskId: contextInput.taskId,
      workspaceId: contextInput.workspaceId,
    }),
    [contextInput.projectId, contextInput.taskId, contextInput.workspaceId]
  );
  const subscribe = useMemo(() => controller.subscribe.bind(controller), [controller]);
  const getSnapshot = useMemo(() => controller.getSnapshot.bind(controller), [controller]);
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const inputChrome = getInputChrome(input, providerCatalog);

  useEffect(() => {
    void controller.setInput(input, context, input.trim() ? 100 : 0);
  }, [context, controller, input]);

  const handleInputChange = (value: string) => {
    setInput(inputChrome.keyword ? `${inputChrome.keyword} ${value}` : value);
  };

  const clearMode = () => {
    setInput(inputChrome.value);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  return (
    <Command
      className="flex flex-col overflow-hidden"
      value={snapshot.selectedIdentity ?? ''}
      onValueChange={(identity) => controller.select(identity)}
      shouldFilter={false}
      loop
    >
      <div className="flex items-center gap-1 border-b border-foreground/10 px-2">
        {inputChrome.keyword && (
          <button
            type="button"
            aria-label={`Clear ${inputChrome.keyword} mode`}
            className="flex shrink-0 items-center gap-1 rounded bg-foreground/10 px-2 py-1 text-xs text-foreground/70 hover:bg-foreground/15"
            onMouseDown={(event) => event.preventDefault()}
            onClick={clearMode}
          >
            {inputChrome.keyword}
            <X size={12} />
          </button>
        )}
        <Command.Input
          ref={inputRef}
          value={inputChrome.value}
          onValueChange={handleInputChange}
          onKeyDown={(event) => {
            if (
              event.key === 'Backspace' &&
              inputChrome.keyword &&
              inputChrome.value.length === 0
            ) {
              event.preventDefault();
              clearMode();
            }
          }}
          placeholder="Search tasks, projects, actions…"
          className="min-w-0 flex-1 bg-transparent px-2 py-3 text-sm outline-none placeholder:text-foreground/40"
          autoFocus
        />
      </div>
      <Command.List className="h-96 overflow-y-auto p-1">
        {snapshot.query && !snapshot.pending && (
          <Command.Empty className="py-8 text-center text-sm text-foreground/40">
            No results for &ldquo;{snapshot.query}&rdquo;
          </Command.Empty>
        )}
        <PaletteResults results={snapshot.results} onSelect={onClose} />
      </Command.List>

      <div className="flex items-center gap-4 border-t border-foreground/10 px-3 py-2">
        <span className="flex items-center gap-1 text-xs text-foreground/40">
          <Shortcut hotkey="ArrowUp" variant="keycaps" />
          <Shortcut hotkey="ArrowDown" variant="keycaps" />
          Navigate
        </span>
        <span className="flex items-center gap-1 text-xs text-foreground/40">
          <Shortcut hotkey="Enter" variant="keycaps" />
          Select
        </span>
        <span className="flex items-center gap-1 text-xs text-foreground/40">
          <Shortcut hotkey="Escape" variant="keycaps" />
          Close
        </span>
      </div>
    </Command>
  );
}

export function CommandPaletteModal({ projectId, taskId, workspaceId }: CommandPaletteProps) {
  const { dismiss } = useModalController('commandPaletteModal');
  const context = useMemo(
    () => ({ projectId, taskId, workspaceId }),
    [projectId, taskId, workspaceId]
  );
  return (
    <CommandPaletteView
      context={context}
      providerCatalog={PALETTE_PROVIDER_CATALOG}
      onClose={dismiss}
    />
  );
}

export const commandPaletteModal = defineModal<void>()({
  id: 'commandPaletteModal',
  component: CommandPaletteModal,
  size: 'md',
});
