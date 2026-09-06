import { Button } from '@emdash/ui/react/primitives';
import { MessageSquare, Plus } from 'lucide-react';
import { newChatDraftView } from '@core/features/workbench/contributions/views';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';

export function TaskListEmptyState({ projectId }: { projectId: string }) {
  const { navigate } = useNavigate();

  return (
    <div className="flex h-full flex-col items-center justify-center bg-background p-8 text-center">
      <div className="flex size-12 items-center justify-center rounded-xl border border-border bg-background-1 text-foreground-muted">
        <MessageSquare className="size-5" />
      </div>
      <h2 className="mt-4 text-base font-medium text-foreground">Start a chat</h2>
      <p className="mt-1 max-w-sm text-sm leading-relaxed text-foreground-muted">
        Chats in this folder can discuss the whole project or create and edit CAD, drawings,
        assemblies, and supporting files.
      </p>
      <div className="mt-5 flex items-center gap-2">
        <Button
          variant="primary"
          aria-label="Create chat"
          onClick={() => navigate(newChatDraftView(projectId))}
        >
          <Plus className="size-3.5" />
          Start first chat <BoundShortcut command="app.newTask" variant="keycaps" />
        </Button>
      </div>
    </div>
  );
}
