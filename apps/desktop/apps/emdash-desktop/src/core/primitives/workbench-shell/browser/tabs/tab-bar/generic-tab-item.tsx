import { Separator } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { cn } from '@core/primitives/styling/browser/cn';
import type { TabHost } from '@core/primitives/workbench-shell/browser/tabs/core/tab-host';
import type {
  ResolvedTab,
  TabViewContext,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { usePaneContext } from '../pane-context';
import { DraggableTab } from './draggable-tab';
import { TabCloseButton } from './tab-close-button';
import type { TabCommand } from './tab-commands';
import { TabContextMenu } from './tab-context-menu';
import { TabTitle } from './tab-title';

/** Props for GenericTabItem — aligns with TabBarItemProps<any> for convenience. */
export interface GenericTabItemProps {
  tab: ResolvedTab;
  host: TabHost;
  ctx: TabViewContext;
  /** Plain visible text; used as the default tooltip base and rename commit basis. */
  label: string;
  /** Tooltip base when different from label (e.g. full file path); preview hint appended. */
  tooltip?: string;
  /** Leading icon slot (file icon, agent icon, spinner). */
  preSlot?: ReactNode;
  /**
   * Overrides the default `<TabTitle>{label}</TabTitle>` for non-rename custom labels
   * (e.g. diff muted suffix). While editing, the inline input is shown regardless.
   */
  labelSlot?: ReactNode;
  /** Content shown under the absolutely-positioned close X (e.g. dirty dot, status icon). */
  statusSlot?: ReactNode;
  /** Renders the title in destructive color. */
  hasError?: boolean;
  /** Extra context-menu items placed after the engine commands. */
  kindCommands?: TabCommand[];
  /** Raw editable text prefilled into the rename input (defaults to label). */
  renameValue?: string;
  /** Max character length enforced on the rename input. */
  renameMaxLength?: number;
}

/**
 * Single generic tab chip renderer. Owns:
 * - Drag wrapper, click/keyboard interaction, active styling, pane separator
 * - Context menu wrapping
 * - Preview tooltip/italic formatting
 * - Inline rename (label → input) driven by host.renameRequest
 * - Close button with optional status indicator underneath
 *
 * Each tab kind supplies only its slot config (preSlot, labelSlot, statusSlot,
 * kindCommands) plus label/tooltip/hasError.
 */
export const GenericTabItem = observer(function GenericTabItem({
  tab,
  host,
  ctx,
  label,
  tooltip,
  preSlot,
  labelSlot,
  statusSlot,
  hasError,
  kindCommands,
  renameValue,
  renameMaxLength,
}: GenericTabItemProps) {
  const { isFocusedPane, pane } = usePaneContext();
  const [isEditing, setIsEditing] = useState(false);
  const committedRef = useRef(false);

  const startRename = useCallback(() => {
    committedRef.current = false;
    window.setTimeout(() => setIsEditing(true), 0);
  }, []);

  const renameRequested = host.renameRequest?.tabId === tab.tabId;
  useEffect(() => {
    if (!renameRequested) return;
    startRename();
    host.clearRenameRequest();
  }, [renameRequested, startRename, host]);

  const commit = useCallback(
    (value: string) => {
      if (committedRef.current) return;
      committedRef.current = true;
      let next = value.trim();
      if (renameMaxLength != null) next = next.slice(0, renameMaxLength);
      if (next && next !== (renameValue ?? label)) host.commitRename(tab.tabId, next);
      setIsEditing(false);
    },
    [host, label, renameMaxLength, renameValue, tab.tabId]
  );

  const handleSelect = () => {
    host.setActiveTab(tab.tabId);
    // Container TabBar onClick will return focus to active content for mouse clicks.
    // Keyboard-initiated selection needs an explicit call since onClick won't fire.
  };

  const base = tooltip ?? label;
  const fullTitle = tab.isPreview ? `${base} (preview — double-click to keep)` : base;

  return (
    <TabContextMenu tab={tab} host={host} ctx={ctx} kindCommands={kindCommands}>
      <DraggableTab id={tab.tabId}>
        <div
          role="button"
          tabIndex={0}
          onMouseEnter={() => host.signalActivateIntent(tab.tabId)}
          onClick={handleSelect}
          onDoubleClick={() => host.pin(tab.tabId)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleSelect();
              // Keyboard selection doesn't bubble as a click, so return focus explicitly.
              pane.focusActiveContent();
            }
          }}
          onMouseDown={(e) => {
            if (e.button === 1) e.preventDefault();
          }}
          onAuxClick={(e) => {
            if (e.button === 1) {
              e.preventDefault();
              host.requestCloseTab(tab.tabId);
            }
          }}
          title={fullTitle}
          data-tabid={tab.tabId}
          className={cn(
            'group relative my-1 flex h-[calc(100%-0.5rem)] flex-col overflow-hidden rounded-md text-sm transition-[background-color,color] duration-100 hover:bg-(--em-surface-hover) focus-visible:bg-(--em-surface-hover) focus-visible:outline-none',
            tab.isActive && 'text-foreground-muted',
            isFocusedPane && 'text-foreground'
          )}
        >
          <div className="flex h-full items-center pr-2 pl-3">
            {preSlot}
            {isEditing ? (
              <input
                ref={(el) => {
                  el?.focus();
                  el?.select();
                }}
                defaultValue={renameValue ?? label}
                maxLength={renameMaxLength}
                className="h-6 max-w-30 min-w-0 rounded bg-background-1 px-1.5 text-sm text-foreground ring-1 ring-foreground/20 outline-none focus:ring-foreground/40"
                onClick={(e) => e.stopPropagation()}
                onDoubleClick={(e) => e.stopPropagation()}
                onBlur={(e) => commit(e.target.value)}
                onKeyDown={(e) => {
                  e.stopPropagation();
                  if (e.key === 'Enter') commit(e.currentTarget.value);
                  else if (e.key === 'Escape') {
                    committedRef.current = true;
                    setIsEditing(false);
                  }
                }}
              />
            ) : (
              (labelSlot ?? (
                <TabTitle
                  isActive={tab.isActive}
                  isPreview={tab.isPreview}
                  hasError={hasError}
                  className="px-1.5"
                >
                  {label}
                </TabTitle>
              ))
            )}
            <TabCloseButton
              onClose={() => host.requestCloseTab(tab.tabId)}
              ariaLabel={`Close ${label}`}
              statusIndicator={statusSlot}
            />
          </div>
        </div>
        <Separator orientation="vertical" />
      </DraggableTab>
    </TabContextMenu>
  );
});

/**
 * Generic drag ghost for any tab kind.
 */
export function GenericTabDragPreview({ preSlot, label }: { preSlot?: ReactNode; label: string }) {
  return (
    <div className="surface-paper flex cursor-grabbing items-center gap-1.5 rounded-md border border-border bg-(--em-surface) px-2 py-1 text-sm opacity-80 shadow-lg">
      {preSlot}
      <span className="max-w-[200px] truncate">{label}</span>
    </div>
  );
}
