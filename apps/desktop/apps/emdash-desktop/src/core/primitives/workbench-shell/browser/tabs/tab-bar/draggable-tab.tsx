import { useDraggable, useDroppable } from '@dnd-kit/core';

export function DraggableTab({ id, children }: { id: string; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef: setDragRef } = useDraggable({ id });
  const { setNodeRef: setDropRef, isOver } = useDroppable({ id });

  return (
    <div
      ref={(el) => {
        setDragRef(el);
        setDropRef(el);
      }}
      style={{
        display: 'flex',
        height: '100%',
        alignItems: 'center',
        position: 'relative',
      }}
      {...attributes}
      {...listeners}
    >
      {isOver && <DropIndicator />}
      {children}
    </div>
  );
}

function DropIndicator() {
  return <div className="pointer-events-none absolute inset-y-1 left-0 z-10 w-0.5 bg-foreground" />;
}

export function PaneDropZone({ paneId }: { paneId: string }) {
  const { setNodeRef, isOver } = useDroppable({ id: `pane-drop-${paneId}` });
  return (
    <div ref={setNodeRef} className="relative h-full flex-1">
      {isOver && <DropIndicator />}
    </div>
  );
}
