import { Combobox } from '@emdash/ui/react/primitives';
import { ChevronDown, ChevronUp, CircleDot, MessageSquare, TextInitial } from 'lucide-react';
import { useMemo, useRef, useState, type ReactNode } from 'react';
import { useChordKeydown } from '@core/primitives/keybindings/browser';
import { Shortcut } from '@core/primitives/keybindings/browser/shortcut';
import { cn } from '@core/primitives/styling/browser/cn';
import { buildContextActionText, type ContextAction } from '../context-bar/context-actions';

const ADD_CONTEXT_HOTKEY = 'Mod+Shift+A';
type AddContextPopoverSide = 'top' | 'bottom';

export function ActionItemBaseRow({
  icon,
  label,
  text,
}: {
  icon: React.ReactNode;
  label: string;
  text: string;
}) {
  return (
    <div className="flex h-5 w-full min-w-0 items-center gap-4">
      <div className="flex items-center gap-1.5">
        {icon}
        <div className="shrink-0 truncate text-sm font-normal text-foreground-muted">{label}</div>
      </div>
      <div className="truncate text-xs text-foreground-passive">{text}</div>
    </div>
  );
}

export function ActionItemRow({ action }: { action: ContextAction }) {
  switch (action.kind) {
    case 'linked-issue':
      return (
        <ActionItemBaseRow
          icon={<CircleDot className="h-3.5 w-3.5 shrink-0" />}
          label={action.issue.title}
          text={action.issue.identifier}
        />
      );
    case 'draft-comments':
      return (
        <ActionItemBaseRow
          icon={<MessageSquare className="size-3.5 shrink-0 text-foreground-muted" />}
          label="Line comments"
          text={`${action.commentCount} comment${action.commentCount !== 1 ? 's' : ''} in ${action.fileCount} file${action.fileCount !== 1 ? 's' : ''}`}
        />
      );
    case 'prompt':
      return (
        <ActionItemBaseRow
          icon={<TextInitial className="size-3.5 shrink-0" />}
          label={action.prompt.title}
          text={action.prompt.prompt}
        />
      );
    default:
      return null;
  }
}

export interface AddContextPopoverProps {
  actions: ContextAction[];
  disabled: boolean;
  emptyMessage?: string;
  hideTrigger?: boolean;
  hotkeyEnabled?: boolean;
  isActivePane?: boolean;
  onApplyAction: (
    text: string,
    action: ContextAction,
    opts?: { andSend?: boolean }
  ) => Promise<void>;
  /** Replace the default "Add context" button with a custom trigger. */
  renderTrigger?: (ctx: { open: boolean; disabled: boolean }) => ReactNode;
  side?: AddContextPopoverSide;
}

export function AddContextPopover({
  actions,
  disabled,
  emptyMessage = 'No context found',
  hideTrigger = false,
  hotkeyEnabled,
  isActivePane = true,
  onApplyAction,
  renderTrigger,
  side = 'top',
}: AddContextPopoverProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<ContextAction | null>(null);
  const [query, setQuery] = useState('');
  const ignoreOpenUntilRef = useRef(0);

  const filteredActions = useMemo(() => {
    if (!query) return actions;
    const q = query.toLowerCase();
    return actions.filter((action) => {
      switch (action.kind) {
        case 'linked-issue':
          return (
            action.issue.title.toLowerCase().includes(q) ||
            action.issue.identifier.toLowerCase().includes(q)
          );
        case 'draft-comments':
          return 'line comments'.includes(q);
        case 'prompt':
          return (
            action.prompt.title.toLowerCase().includes(q) ||
            action.prompt.prompt.toLowerCase().includes(q)
          );
      }
    });
  }, [query, actions]);

  useChordKeydown(
    ADD_CONTEXT_HOTKEY,
    (event) => {
      event.preventDefault();
      setOpen((value) => !value);
    },
    { enabled: (hotkeyEnabled ?? !disabled) && isActivePane }
  );

  const handleConfirm = (action: ContextAction | null, opts?: { andSend?: boolean }) => {
    if (!action) return;
    const text = buildContextActionText(action);
    void onApplyAction(text, action, opts);
    setOpen(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen && Date.now() < ignoreOpenUntilRef.current) {
      return;
    }
    setOpen(nextOpen);
    if (!nextOpen) setQuery('');
  };

  const blockComboboxOpenForContextMenu = () => {
    ignoreOpenUntilRef.current = Date.now() + 500;
  };

  const blockSyntheticClickAfterContextMenu = (event: React.SyntheticEvent) => {
    if (Date.now() >= ignoreOpenUntilRef.current) return;
    event.preventDefault();
    event.stopPropagation();
  };

  return (
    <Combobox.Root
      items={[{ value: 'items', items: filteredActions }]}
      value={null}
      onInputValueChange={(value) => setQuery(value ?? '')}
      inputValue={query}
      onValueChange={(action) => handleConfirm(action)}
      onItemHighlighted={(value) => setSelected(value ?? null)}
      open={open}
      onOpenChange={handleOpenChange}
      // 'always' highlights the first item on open; Base UI types narrow to boolean
      // but the runtime accepts the string literal
      autoHighlight={'always' as unknown as boolean}
    >
      <Combobox.Trigger
        disabled={disabled}
        onContextMenuCapture={() => blockComboboxOpenForContextMenu()}
        onPointerDownCapture={(event) => {
          if (event.button !== 0) blockComboboxOpenForContextMenu();
        }}
        onMouseDownCapture={(event) => {
          if (event.button !== 0) blockComboboxOpenForContextMenu();
        }}
        onClickCapture={(event) => {
          if (event.button !== 0) blockComboboxOpenForContextMenu();
          blockSyntheticClickAfterContextMenu(event);
        }}
        aria-hidden={hideTrigger || undefined}
        tabIndex={hideTrigger ? -1 : undefined}
        className={cn(
          hideTrigger
            ? 'pointer-events-none absolute bottom-0 left-1/2 size-px -translate-x-1/2 overflow-hidden border-0 p-0 opacity-0'
            : renderTrigger
              ? undefined
              : 'flex h-6 min-w-[160px] items-center justify-between gap-1.5 rounded-lg border-border bg-background-secondary-2 px-2 text-xs font-normal text-foreground-muted transition-colors hover:bg-background-secondary-3 hover:text-foreground disabled:pointer-events-none'
        )}
      >
        {hideTrigger ? null : renderTrigger ? (
          renderTrigger({ open, disabled })
        ) : (
          <>
            <span className="flex items-center gap-1.5">
              {open ? (
                <ChevronUp className="size-3 shrink-0" />
              ) : (
                <ChevronDown className="size-3 shrink-0" />
              )}
              <span>Add context</span>
            </span>
            <Shortcut hotkey={ADD_CONTEXT_HOTKEY} variant="keycaps" />
          </>
        )}
      </Combobox.Trigger>

      <Combobox.Content
        side={side}
        align="center"
        className="flex flex-col"
        style={{ width: 'min(27rem, calc(100vw - 2rem), var(--available-width))' }}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            handleConfirm(selected ?? filteredActions[0] ?? null, { andSend: true });
          }
        }}
      >
        <Combobox.Input showTrigger={false} placeholder="Search..." />
        <Combobox.List className="flex-1">
          {(group: { value: string; items: ContextAction[] }) => (
            <Combobox.Group items={group.items}>
              <Combobox.Collection>
                {(action: ContextAction) => (
                  <Combobox.Item
                    key={action.id}
                    value={action}
                    className="items-start data-highlighted:bg-background-2!"
                  >
                    <ActionItemRow action={action} />
                  </Combobox.Item>
                )}
              </Combobox.Collection>
            </Combobox.Group>
          )}
        </Combobox.List>
        <Combobox.Empty className="flex flex-1 items-center justify-center">
          {emptyMessage}
        </Combobox.Empty>
        <div className="flex items-center justify-end border-t px-2 py-1.5">
          <span className="flex items-center gap-1">
            <p className="text-xs text-foreground-passive">Add to input</p>
            <Shortcut hotkey="Enter" variant="keycaps" />
          </span>
        </div>
      </Combobox.Content>
    </Combobox.Root>
  );
}
