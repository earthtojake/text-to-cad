import { Plus } from 'lucide-react';
import { cn } from '@core/primitives/styling/browser/cn';

interface AddCommentButtonProps {
  pinned: boolean;
  onClick: () => void;
}

export function AddCommentButton({ pinned, onClick }: AddCommentButtonProps) {
  return (
    <button
      className={cn(
        'flex h-[22px] w-[22px] cursor-pointer items-center justify-center rounded-md border transition-colors',
        pinned
          ? 'border-border bg-background-2 text-foreground'
          : 'border-transparent bg-transparent text-foreground-muted hover:border-border hover:bg-background-2 hover:text-foreground'
      )}
      onMouseDown={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      }}
    >
      <Plus className="h-3 w-3" />
    </button>
  );
}
