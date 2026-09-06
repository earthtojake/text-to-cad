import {
  closestCenter,
  DndContext,
  DragOverlay,
  MeasuringStrategy,
  PointerSensor,
  pointerWithin,
  useDndContext,
  useSensor,
  useSensors,
  type ClientRect,
  type CollisionDetection,
  type DragEndEvent,
  type DragMoveEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { getTaskStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { type SidebarRow } from '@core/features/workbench/browser/sidebar/sidebar-store';
import { getSidebarStore } from '@core/features/workbench/contributions/browser/app-stores';
import {
  useViewParams,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';
import { SidebarProjectItem } from './project-item';
import { SidebarTaskItem } from './task-item';

const ROW_HEIGHT = 32;

export const SidebarVirtualList = observer(function SidebarVirtualList() {
  const rows = getSidebarStore().sidebarRows;
  const { currentView } = useWorkspaceSlots();
  const taskParams = useViewParams(taskViewDef) ?? {
    projectId: undefined,
    taskId: undefined,
  };
  const projectParams = useViewParams(projectViewDef) ?? { projectId: undefined };

  const scrollRef = useRef<HTMLDivElement>(null);
  const initialPointerYRef = useRef<number | null>(null);
  const dragPointerYRef = useRef<number | null>(null);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [dragPointerY, setDragPointerY] = useState<number | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const activeTaskProjectExpanded =
    currentView === 'task' && taskParams.projectId
      ? getSidebarStore().expandedProjectIds.has(taskParams.projectId)
      : null;
  const allDndIds = useMemo(() => rows.map(rowToDndId), [rows]);

  // Expand the parent project when navigating to a task (not when `rows` changes —
  // otherwise collapsing while staying on that task would immediately re-expand).
  useEffect(() => {
    if (currentView !== 'task') return;
    const targetProjectId = taskParams.projectId;
    const targetTaskId = taskParams.taskId;
    if (!targetProjectId || !targetTaskId) return;
    const activeTask = getTaskStore(targetProjectId, targetTaskId);
    if (activeTask?.data.isPinned) return;
    getSidebarStore().ensureProjectExpanded(targetProjectId);
  }, [currentView, taskParams.projectId, taskParams.taskId]);

  // Scroll the active project/task into view only when the navigation target itself
  // changes, plus the active task's project expansion state. Re-running on every
  // `rows` change would yank the user back to the active row whenever the
  // sidebar mutates (e.g. deleting an unrelated task), but direct navigation to a
  // task in a collapsed project needs one rerun after `ensureProjectExpanded`.
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  useEffect(() => {
    let targetProjectId: string | null = null;
    let targetTaskId: string | null = null;

    if (currentView === 'task') {
      targetProjectId = taskParams.projectId ?? null;
      targetTaskId = taskParams.taskId ?? null;
    } else if (currentView === 'project') {
      targetProjectId = projectParams.projectId ?? null;
    }

    if (!targetProjectId) return;

    if (targetTaskId) {
      const activeTask = getTaskStore(targetProjectId, targetTaskId);
      if (activeTask?.data.isPinned) {
        return;
      }
    }

    const activeIndex = rowsRef.current.findIndex((row) => {
      if (targetTaskId) {
        return (
          row.kind === 'task' && row.taskId === targetTaskId && row.projectId === targetProjectId
        );
      }
      return row.kind === 'project' && row.projectId === targetProjectId;
    });

    if (activeIndex >= 0) {
      const frame = window.requestAnimationFrame(() => {
        scrollRef.current
          ?.querySelector<HTMLElement>(`[data-sidebar-row-index="${activeIndex}"]`)
          ?.scrollIntoView({ block: 'nearest' });
      });
      return () => window.cancelAnimationFrame(frame);
    }
  }, [
    currentView,
    taskParams.projectId,
    taskParams.taskId,
    projectParams.projectId,
    activeTaskProjectExpanded,
  ]);

  function setCurrentDragPointerY(pointerY: number | null) {
    dragPointerYRef.current = pointerY;
    setDragPointerY(pointerY);
  }

  function handleDragStart(event: DragStartEvent) {
    const pointerY = getEventClientY(event.activatorEvent);
    initialPointerYRef.current = pointerY;
    setActiveDragId(String(event.active.id));
    setCurrentDragPointerY(pointerY);
  }

  function handleDragMove(event: DragMoveEvent) {
    const initialPointerY = initialPointerYRef.current;
    if (initialPointerY === null) return;
    setCurrentDragPointerY(initialPointerY + event.delta.y);
  }

  function clearDragPointerY() {
    initialPointerYRef.current = null;
    setActiveDragId(null);
    setCurrentDragPointerY(null);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    const pointerY = dragPointerYRef.current;
    clearDragPointerY();
    if (!over || active.id === over.id) return;
    const aParsed = parseDndId(String(active.id));
    const oParsed = parseDndId(String(over.id));
    if (!aParsed || !oParsed) return;

    const isAbove = isCursorAbove(pointerY, active.rect.current.translated, over.rect);

    if (aParsed.kind === 'project') {
      const overRowIdx = rows.findIndex((r) => rowToDndId(r) === String(over.id));
      if (overRowIdx === -1) return;
      const insertionRowIdx = isAbove ? overRowIdx : overRowIdx + 1;
      const ids = getSidebarStore()
        .orderedProjects.map((p) => (p.state === 'unregistered' ? p.id : (p.data?.id ?? '')))
        .filter(Boolean);
      const oldIdx = ids.indexOf(aParsed.projectId);
      if (oldIdx === -1) return;
      const projectsAbove = rows
        .slice(0, insertionRowIdx)
        .filter((r) => r.kind === 'project').length;
      let newIdx = projectsAbove;
      if (newIdx > oldIdx) newIdx -= 1;
      if (newIdx === oldIdx) return;
      getSidebarStore().setProjectOrder(arrayMove(ids, oldIdx, newIdx));
    } else if (oParsed.kind === 'task' && oParsed.projectId === aParsed.projectId) {
      const projectId = aParsed.projectId;
      const taskIds = rows
        .filter(
          (r): r is Extract<SidebarRow, { kind: 'task' }> =>
            r.kind === 'task' && r.projectId === projectId
        )
        .map((r) => r.taskId);
      const oldIdx = taskIds.indexOf(aParsed.taskId);
      const overTaskIdx = taskIds.indexOf(oParsed.taskId);
      if (oldIdx === -1 || overTaskIdx === -1) return;
      let newIdx = isAbove ? overTaskIdx : overTaskIdx + 1;
      if (newIdx > oldIdx) newIdx -= 1;
      if (newIdx === oldIdx) return;
      getSidebarStore().setTaskOrder(projectId, arrayMove(taskIds, oldIdx, newIdx));
    }
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={sidebarCollision}
      measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
      autoScroll={{ threshold: { x: 0, y: 0.18 }, acceleration: 8, interval: 5 }}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      onDragCancel={clearDragPointerY}
    >
      <SortableContext items={allDndIds} strategy={verticalListSortingStrategy}>
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-3 pt-1 pb-3">
          <div className="relative">
            {rows.map((row, index) => {
              const dndId = rowToDndId(row);
              const rowStyle: React.CSSProperties = {
                width: '100%',
                minHeight: `${ROW_HEIGHT}px`,
              };
              if (row.kind === 'project') {
                return (
                  <SortableRow key={row.projectId} dndId={dndId} style={rowStyle} index={index}>
                    <SidebarProjectItem projectId={row.projectId} />
                  </SortableRow>
                );
              }
              return (
                <SortableRow
                  key={`${row.projectId}:${row.taskId}`}
                  dndId={dndId}
                  style={rowStyle}
                  index={index}
                >
                  <SidebarTaskItem projectId={row.projectId} taskId={row.taskId} />
                </SortableRow>
              );
            })}
          </div>
        </div>
      </SortableContext>
      <DragOverlay dropAnimation={null}>
        {activeDragId ? <DragOverlayContent dndId={activeDragId} /> : null}
      </DragOverlay>
      <InsertionIndicator pointerY={dragPointerY} />
    </DndContext>
  );
});

const toProjectDndId = (id: string) => `proj::${id}`;
const toTaskDndId = (projectId: string, taskId: string) => `task::${projectId}::${taskId}`;

type SidebarDndId =
  | { kind: 'project'; projectId: string }
  | { kind: 'task'; projectId: string; taskId: string };

function rowToDndId(row: SidebarRow): string {
  if (row.kind === 'project') return toProjectDndId(row.projectId);
  return toTaskDndId(row.projectId, row.taskId);
}

function parseDndId(id: string): SidebarDndId | null {
  if (id.startsWith('proj::')) return { kind: 'project', projectId: id.slice(6) };
  if (id.startsWith('task::')) {
    const [, projectId, taskId] = id.split('::');
    if (projectId && taskId) return { kind: 'task', projectId, taskId };
  }
  return null;
}

// Project drags consider every visible row so dropping over a task maps to its
// owning project in onDragEnd without changing the visible list mid-drag.
// Task drags stay restricted to their own project's tasks.
const sidebarCollision: CollisionDetection = (args) => {
  const activeId = String(args.active.id);
  const parsed = parseDndId(activeId);
  if (!parsed) return [];
  const containers = args.droppableContainers.filter((c) => {
    const id = String(c.id);
    if (id === activeId) return false;
    if (parsed.kind === 'task') {
      const cParsed = parseDndId(id);
      return cParsed?.kind === 'task' && cParsed.projectId === parsed.projectId;
    }
    return true;
  });
  const filteredArgs = { ...args, droppableContainers: containers };
  const pointerCollisions = pointerWithin(filteredArgs);
  return pointerCollisions.length > 0 ? pointerCollisions : closestCenter(filteredArgs);
};

function getEventClientY(event: Event): number | null {
  if ('clientY' in event && typeof event.clientY === 'number') return event.clientY;
  if (typeof TouchEvent !== 'undefined' && event instanceof TouchEvent) {
    const touch = event.touches[0] ?? event.changedTouches[0];
    return touch?.clientY ?? null;
  }
  return null;
}

function isCursorAbove(
  pointerY: number | null,
  translated: ClientRect | null,
  overRect: ClientRect
): boolean {
  if (pointerY !== null) return pointerY < overRect.top + overRect.height / 2;
  if (!translated) return true;
  const cursorY = translated.top + translated.height / 2;
  const overCenterY = overRect.top + overRect.height / 2;
  return cursorY < overCenterY;
}

function DragOverlayContent({ dndId }: { dndId: string }) {
  const parsed = parseDndId(dndId);
  if (!parsed) return null;
  return (
    <div className="px-3">
      <div className="rounded-lg bg-background-tertiary-2 shadow-md">
        {parsed.kind === 'project' ? (
          <SidebarProjectItem projectId={parsed.projectId} />
        ) : (
          <SidebarTaskItem projectId={parsed.projectId} taskId={parsed.taskId} />
        )}
      </div>
    </div>
  );
}

function InsertionIndicator({ pointerY }: { pointerY: number | null }) {
  const { active, over } = useDndContext();
  if (!active || !over || active.id === over.id) return null;
  const activeParsed = parseDndId(String(active.id));
  const overParsed = parseDndId(String(over.id));
  if (!activeParsed || !overParsed) return null;
  if (
    activeParsed.kind === 'project' &&
    overParsed.kind === 'task' &&
    overParsed.projectId === activeParsed.projectId
  ) {
    return null;
  }
  const overRect = over.rect;
  if (!overRect) return null;
  const isAbove = isCursorAbove(pointerY, active.rect.current.translated, overRect);
  const top = isAbove ? overRect.top : overRect.top + overRect.height;
  return createPortal(
    <div
      className="bg-foreground"
      style={{
        position: 'fixed',
        left: overRect.left + 8,
        top: top - 1.5,
        width: Math.max(0, overRect.width - 16),
        height: 3,
        borderRadius: 2,
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    />,
    document.body
  );
}

interface SortableRowProps {
  dndId: string;
  style: React.CSSProperties;
  children: React.ReactNode;
  index: number;
}

function SortableRow({ dndId, style, children, index }: SortableRowProps) {
  const { setNodeRef, transform, transition, isDragging, listeners } = useSortable({
    id: dndId,
  });

  const combinedStyle: React.CSSProperties = {
    ...style,
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 1 : 'auto',
  };

  return (
    <div
      ref={setNodeRef}
      data-index={index}
      data-sidebar-row-index={index}
      style={combinedStyle}
      {...listeners}
    >
      {children}
    </div>
  );
}
