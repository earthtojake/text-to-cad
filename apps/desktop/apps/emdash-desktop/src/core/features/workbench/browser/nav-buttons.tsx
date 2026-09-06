import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import type { HistoryEntry } from '@core/primitives/navigation/api';
import {
  getNavigation,
  getNavigationHistory,
} from '@core/primitives/navigation/browser/navigation-selectors';

export function applyHistoryEntry(entry: HistoryEntry): boolean {
  return getNavigation().applyEntry(entry);
}

export const NavButtons = observer(function NavButtons() {
  const { canGoBack, canGoForward } = getNavigationHistory();
  return (
    <div className="flex items-center gap-0.5 [-webkit-app-region:no-drag]">
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              aria-label="Go back"
              disabled={!canGoBack}
              onClick={() => getNavigationHistory().back(applyHistoryEntry)}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
          }
        />
        <Tooltip.Content>
          Go Back
          <BoundShortcut command="app.navigateBack" variant="keycaps" />
        </Tooltip.Content>
      </Tooltip.Root>
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              aria-label="Go forward"
              disabled={!canGoForward}
              onClick={() => getNavigationHistory().forward(applyHistoryEntry)}
            >
              <ArrowRight className="h-4 w-4" />
            </Button>
          }
        />
        <Tooltip.Content>
          Go Forward
          <BoundShortcut command="app.navigateForward" variant="keycaps" />
        </Tooltip.Content>
      </Tooltip.Root>
    </div>
  );
});
