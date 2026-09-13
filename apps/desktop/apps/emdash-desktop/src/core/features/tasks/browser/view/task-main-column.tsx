import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  pointerWithin,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  Resizable,
  useCollapsiblePanelBinding,
  useResizableDefaultLayout,
} from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useMemo, useState } from 'react';
import {
  splitPanePanelId,
  taskPanelLayoutsMemento,
} from '@core/features/tasks/contributions/mementos';
import {
  isTerminalDrawerDragData,
  type TerminalDrawerDragData,
} from '@core/features/terminals/api/browser/task-terminal/terminal-drag';
import { TerminalsPanel } from '@core/features/terminals/contributions/browser/task-terminal/terminal-panel';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';
import { PaneProvider } from '@core/features/workbench/contributions/browser/tabs/pane-provider';
import { createLayoutStorage, type MementoLayoutStorage } from '@core/primitives/mementos/browser';
import { PaneContent } from '@core/primitives/workbench-shell/browser/tabs/pane-content';
import type { Pane as PaneGroup } from '@core/primitives/workbench-shell/browser/tabs/pane-layout-store';
import { TabDragPreview } from '@core/primitives/workbench-shell/browser/tabs/tab-bar/tab-drag-preview';
import { PaneEmptyState } from '../pane-empty-state';
import { shouldShowTaskPaneTabBar } from './task-pane-chrome';

type ActiveDrag =
  | { kind: 'tab'; tabId: string }
  | { kind: 'terminal'; terminal: TerminalDrawerDragData };

// Drag-to-close threshold for the bottom drawer, in percent of the column.
// Below ~10% only the drawer tab bar and a row or two of terminal remain
// visible, so a drag settling there reads as intent to close rather than a
// resize. Deliberately under the drawer's old 15% resize floor, so every
// height the previous UI could persist stays a plain restore, never a close.
const TERMINAL_DRAWER_CLOSE_THRESHOLD = 10;

export const TaskMainColumn = observer(function TaskMainColumn() {
  const taskView = useTaskComposition();
  const { paneLayout } = taskView;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const [activeDrag, setActiveDrag] = useState<ActiveDrag | null>(null);

  // One storage facade per composition. TaskMainColumn renders below the task
  // view's space.isHydrated gate, so synchronous reads are safe by contract.
  const layoutStorage = useMemo(
    () => createLayoutStorage(taskView.space, taskPanelLayoutsMemento),
    [taskView.space]
  );
  const drawerBinding = useCollapsiblePanelBinding({
    storageKey: 'task-main-vertical',
    storage: layoutStorage,
    panelIds: ['task-main-content', 'task-terminal-drawer'],
    collapsiblePanelId: 'task-terminal-drawer',
    open: taskView.isTerminalDrawerOpen,
    onCloseRequest: () => taskView.chrome.commands.closeTerminalDrawer(),
    closeThreshold: TERMINAL_DRAWER_CLOSE_THRESHOLD,
  });

  const handleDragStart = (event: DragStartEvent) => {
    const terminalDragData = event.active.data.current;
    if (isTerminalDrawerDragData(terminalDragData)) {
      setActiveDrag({ kind: 'terminal', terminal: terminalDragData });
      return;
    }
    setActiveDrag({ kind: 'tab', tabId: event.active.id as string });
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveDrag(null);
    if (!event.over) return;

    const terminalDragData = event.active.data.current;
    if (isTerminalDrawerDragData(terminalDragData)) {
      const paneId = resolveDropPaneId(String(event.over.id), paneLayout);
      if (!paneId) return;
      paneLayout.setActiveGroup(paneId);
      paneLayout.open(
        'terminal',
        { terminalId: terminalDragData.terminalId },
        { target: { paneId } }
      );
      return;
    }

    paneLayout.handleDragEnd(event.active.id as string, event.over.id as string);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveDrag(null)}
    >
      <Resizable.Group orientation="vertical" id="task-main-vertical" {...drawerBinding.groupProps}>
        <Resizable.Panel id="task-main-content" minSize="30%">
          <SplitPaneLayout storage={layoutStorage} />
        </Resizable.Panel>
        {/* Closed = panel AND handle unmounted (sync contract: never program
            the panels). Terminal content survives the unmount because each
            PTY session's xterm DOM is reparented to the off-screen host, not
            disposed (see usePty). */}
        {taskView.isTerminalDrawerOpen && (
          <>
            <Resizable.Handle />
            <Resizable.Panel
              {...drawerBinding.collapsiblePanelProps}
              defaultSize={drawerBinding.collapsiblePanelProps.defaultSize ?? '25%'}
            >
              <TerminalsPanel />
            </Resizable.Panel>
          </>
        )}
      </Resizable.Group>
      <DragOverlay dropAnimation={null}>
        {activeDrag?.kind === 'tab' ? (
          <TabDragPreview tabId={activeDrag.tabId} />
        ) : activeDrag?.kind === 'terminal' ? (
          <TerminalDragPreview label={activeDrag.terminal.label} />
        ) : null}
      </DragOverlay>
    </DndContext>
  );
});

/**
 * One horizontal split pane: optional resize handle + resizable panel +
 * PaneProvider + PaneContent (which self-hosts PaneDimensionProvider on its
 * content region so the TabBar is excluded from the measured dimensions).
 */
const SplitPane = observer(function SplitPane({
  group,
  index,
  onActivate,
  defaultSize,
}: {
  group: PaneGroup;
  index: number;
  onActivate: () => void;
  defaultSize: string;
}) {
  const taskView = useTaskComposition();
  const canSplit = group.pane.resolvedTabs.length >= 2 && taskView.paneLayout.groups.length < 3;
  return (
    <>
      {index > 0 && <Resizable.Handle />}
      <Resizable.Panel
        id={splitPanePanelId(group.paneId)}
        defaultSize={defaultSize}
        minSize="200px"
        onPointerDown={onActivate}
      >
        <PaneProvider
          group={group}
          canSplit={canSplit}
          splitPane={() => taskView.paneLayout.splitRight()}
        >
          <PaneContent
            emptyState={<PaneEmptyState />}
            showTabBar={shouldShowTaskPaneTabBar(group.pane.resolvedTabs.map((tab) => tab.kind))}
          />
        </PaneProvider>
      </Resizable.Panel>
    </>
  );
});

/** Renders one vertical pane per tab group inside a Resizable.Group. */
const SplitPaneLayout = observer(function SplitPaneLayout({
  storage,
}: {
  storage: MementoLayoutStorage;
}) {
  const taskView = useTaskComposition();
  const { paneLayout } = taskView;

  // Split sizes persist through the shared layout storage like every other
  // resizable surface (sync contract: pixel sizes belong to the library, no
  // store write-back). The storage entry key derives from the pane-group id
  // combination, so a stale entry for a different set of groups is never
  // read and a re-split (fresh group id) starts from defaults; destroyed
  // groups' entries are deleted by the store owner (task-composition).
  const panelIds = paneLayout.groups.map((group) => splitPanePanelId(group.paneId));
  const { defaultLayout, onLayoutChanged } = useResizableDefaultLayout({
    id: 'task-main-split',
    panelIds,
    storage,
  });
  // `defaultLayout` covers panels present at Group mount; a panel entering
  // later (a fresh split) falls back to an even share via `defaultSize`.
  const evenSharePct = Math.floor(100 / paneLayout.groups.length);

  return (
    <Resizable.Group
      orientation="horizontal"
      id="task-main-split"
      defaultLayout={defaultLayout}
      onLayoutChanged={onLayoutChanged}
    >
      {paneLayout.groups.map((group, i) => (
        <SplitPane
          key={group.paneId}
          group={group}
          index={i}
          onActivate={() => paneLayout.setActiveGroup(group.paneId)}
          defaultSize={`${defaultLayout?.[splitPanePanelId(group.paneId)] ?? evenSharePct}%`}
        />
      ))}
    </Resizable.Group>
  );
});

function resolveDropPaneId(
  overId: string,
  paneLayout: ReturnType<typeof useTaskComposition>['paneLayout']
): string | undefined {
  if (overId.startsWith('pane-drop-')) return overId.slice('pane-drop-'.length);
  if (overId.startsWith('pane-content-')) return overId.slice('pane-content-'.length);
  return paneLayout.groups.find((group) => group.pane.entries.has(overId))?.paneId;
}

function TerminalDragPreview({ label }: { label: string }) {
  return (
    <div className="surface-paper flex cursor-grabbing items-center gap-1.5 rounded-md border border-border bg-(--em-surface) px-2 py-1 text-sm opacity-80 shadow-lg">
      <span className="max-w-[200px] truncate">{label}</span>
    </div>
  );
}
