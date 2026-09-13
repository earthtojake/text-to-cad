import { Copy, Minus, Square, X } from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { detectPlatformContext } from '@core/primitives/keybindings/api';
import { cn } from '@core/primitives/styling/browser/cn';

const isLinux = detectPlatformContext().os === 'linux';

/**
 * Linux-only top overlay providing a draggable strip and window controls for
 * full-screen views that do not render the {@link Titlebar} (onboarding and the
 * welcome splash). Sits above the welcome screen's `z-50` overlay. No-op on
 * macOS/Windows, which keep their native frame or traffic lights.
 */
export function FramelessTitlebarOverlay() {
  if (!isLinux) return null;
  return (
    <div className="fixed inset-x-0 top-0 z-60 flex h-10 items-center justify-end [-webkit-app-region:drag]">
      <WindowControls />
    </div>
  );
}

/**
 * Custom window controls (minimize / maximize / close) for the frameless Linux
 * window. macOS keeps its native traffic lights and Windows keeps the native
 * frame, so this is only rendered on Linux (see Titlebar).
 */
export function WindowControls() {
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void getHostClient().then(async (client) => {
      setIsMaximized(await client.isWindowMaximized());
      const nextUnsubscribe = await client.events.subscribe(undefined, {
        onEvent: (event) => {
          if (event.type === 'window-maximize-changed') setIsMaximized(event.maximized);
        },
        onGap: () => {},
      });
      if (disposed) nextUnsubscribe();
      else unsubscribe = nextUnsubscribe;
    });
    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, []);

  return (
    <div className="flex h-full items-center [-webkit-app-region:no-drag]">
      <ControlButton
        label="Minimize"
        onClick={() => void getHostClient().then((client) => client.minimizeWindow())}
      >
        <Minus className="h-4 w-4" />
      </ControlButton>
      <ControlButton
        label={isMaximized ? 'Restore' : 'Maximize'}
        onClick={() => void getHostClient().then((client) => client.toggleMaximizeWindow())}
      >
        {isMaximized ? <Copy className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
      </ControlButton>
      <ControlButton
        label="Close"
        danger
        onClick={() => void getHostClient().then((client) => client.closeWindow())}
      >
        <X className="h-4 w-4" />
      </ControlButton>
    </div>
  );
}

function ControlButton({
  children,
  label,
  onClick,
  danger,
}: {
  children: ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        'flex h-10 w-12 items-center justify-center text-foreground-muted transition-colors hover:bg-background-2',
        danger && 'hover:bg-background-destructive hover:text-foreground-destructive'
      )}
    >
      {children}
    </button>
  );
}
