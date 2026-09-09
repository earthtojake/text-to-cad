import { observer } from 'mobx-react-lite';
import { cn } from '@core/primitives/styling/browser/cn';
import { usePaneContext } from '../../tabs/pane-context';

export const TabTitle = observer(function TabTitle({
  isActive,
  isPreview,
  hasError,
  maxWidth = 'max-w-[200px]',
  className,
  children,
}: {
  isActive: boolean;
  isPreview?: boolean;
  hasError?: boolean;
  maxWidth?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const { isFocusedPane } = usePaneContext();

  return (
    <span
      className={cn(
        'truncate p-1 text-sm opacity-85 group-hover:opacity-100 transition-opacity',
        maxWidth,
        isPreview && 'italic',
        isActive && isFocusedPane && 'opacity-100',
        hasError && 'text-foreground-destructive',
        className
      )}
    >
      {children}
    </span>
  );
});
