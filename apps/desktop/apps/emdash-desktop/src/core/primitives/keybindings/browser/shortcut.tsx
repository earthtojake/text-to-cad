import { Kbd, KbdGroup } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useState } from 'react';
import type { CommandDef } from '@core/primitives/commands/api';
import { chord, detectPlatformContext, type Chord } from '@core/primitives/keybindings/api';
import { cn } from '@core/primitives/styling/browser/cn';
import { keybindingService } from './keybinding-service';
import { keyboardLayoutService } from './keyboard-layout-service';

type ShortcutVariant = 'text' | 'badge' | 'keycaps';

const KEYCAP_KBD_BASE_CLASS =
  'h-5 min-w-5 shrink-0 rounded px-1 text-tiny font-medium leading-none text-current';

const KEYCAP_KBD_CLASS = cn(
  KEYCAP_KBD_BASE_CLASS,
  'border-border/60 bg-background-secondary shadow-[inset_0_-1px_0_rgba(255,255,255,0.05)]',
  // Primary action buttons (Create, Save, etc.). Primary buttons opt in via data-variant="primary".
  'in-data-[variant=primary]:border-primary-button-foreground/22 in-data-[variant=primary]:bg-primary-button-foreground/16 in-data-[variant=primary]:shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]',
  'in-data-[slot=combobox-trigger]:border-border/50 in-data-[slot=combobox-trigger]:bg-background-secondary in-data-[slot=combobox-trigger]:shadow-[inset_0_-1px_0_rgba(255,255,255,0.05)]',
  'in-data-[slot=tooltip-content]:border-background/20 in-data-[slot=tooltip-content]:bg-background/15 in-data-[slot=tooltip-content]:text-background in-data-[slot=tooltip-content]:shadow-none',
  'in-data-[slot=dropdown-menu-item]:border-border/50 in-data-[slot=dropdown-menu-item]:bg-background-secondary in-data-[slot=dropdown-menu-item]:shadow-[inset_0_-1px_0_rgba(255,255,255,0.05)]'
);

interface ShortcutProps {
  hotkey: Chord | string | null | undefined;
  className?: string;
  variant?: ShortcutVariant;
  bare?: boolean;
}

function ShortcutKey({ keyName }: { keyName: string }) {
  return (
    <span aria-hidden="true" className="inline-block">
      {keyName}
    </span>
  );
}

/** Display a shortcut when the hotkey string is already resolved. */
function Shortcut({ hotkey, className, variant = 'text', bare = false }: ShortcutProps) {
  const [, setLayoutVersion] = useState(0);
  useEffect(
    () => keyboardLayoutService.onDidChangeLayout(() => setLayoutVersion((version) => version + 1)),
    []
  );
  const parsed = useMemo(() => {
    if (!hotkey) return null;
    try {
      return chord(hotkey);
    } catch {
      return null;
    }
  }, [hotkey]);

  if (!parsed) return null;

  const keys = keyboardLayoutService.displayLabel(parsed, detectPlatformContext());

  if (bare) {
    return (
      <KbdGroup data-slot="shortcut" role="img" aria-label={keys.join(' + ')} className={className}>
        {keys.map((key, index) => (
          <Kbd key={`${key}-${index}`} aria-hidden="true">
            <ShortcutKey keyName={key} />
          </Kbd>
        ))}
      </KbdGroup>
    );
  }

  return (
    <span
      data-slot="shortcut"
      role="img"
      aria-label={keys.join(' + ')}
      className={cn(
        variant === 'text' &&
          'inline-flex shrink-0 items-center justify-center gap-0 rounded px-1.5 py-1 text-xs leading-none text-foreground-muted in-data-[slot=tooltip-content]:text-background',
        variant === 'badge' &&
          'inline-flex shrink-0 items-center justify-center gap-0 rounded bg-background-secondary px-1.5 py-1 text-xs leading-none text-foreground/60 in-data-[slot=tooltip-content]:bg-background/20 in-data-[slot=tooltip-content]:py-0.5 in-data-[slot=tooltip-content]:text-background',
        variant === 'keycaps' &&
          'inline-flex shrink-0 items-center gap-0.5 text-foreground-muted in-data-[slot=button]:text-current in-data-[slot=combobox-trigger]:text-current in-data-[slot=tooltip-content]:text-background',
        className
      )}
    >
      {keys.map((key, index) =>
        variant === 'keycaps' ? (
          <Kbd key={`${key}-${index}`} aria-hidden="true" className={KEYCAP_KBD_CLASS}>
            <ShortcutKey keyName={key} />
          </Kbd>
        ) : (
          <ShortcutKey key={`${key}-${index}`} keyName={key} />
        )
      )}
    </span>
  );
}

interface BoundShortcutProps {
  command: CommandDef | string;
  className?: string;
  variant?: ShortcutVariant;
  bare?: boolean;
}

/** Display a shortcut directly from an app shortcut settings key. */
const BoundShortcut = observer(function BoundShortcut({
  command,
  className,
  variant,
  bare,
}: BoundShortcutProps) {
  const hotkey = keybindingService.chordFor(typeof command === 'string' ? command : command.id);

  return <Shortcut hotkey={hotkey} className={className} variant={variant} bare={bare} />;
});

export { BoundShortcut, Shortcut, type ShortcutVariant };
