import { Button } from '@emdash/ui/react/primitives';
import { motion, type Variants } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import HardcoreIcon from '@/assets/images/hardcore/hardcore.png';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { confirmCommand } from '@core/features/workbench/contributions/commands';
import { detectPlatformContext, resolveEffectiveChord } from '@core/primitives/keybindings/api';
import { useChordKeydown } from '@core/primitives/keybindings/browser';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';

const SHORTCUT_PRESS_DURATION_MS = 120;

interface WelcomeScreenProps {
  onGetStarted: () => void;
}

export function WelcomeScreen({ onGetStarted }: WelcomeScreenProps) {
  const { value: keyboard } = useAppSettingsKey('keyboard');
  const confirmHotkey = confirmCommand.keybinding
    ? resolveEffectiveChord(confirmCommand.keybinding, keyboard ?? {}, detectPlatformContext())
    : null;
  const [isShortcutPressed, setIsShortcutPressed] = useState(false);
  const shortcutPressTimeoutRef = useRef<number | null>(null);

  const handleGetStarted = useCallback(() => {
    if (shortcutPressTimeoutRef.current !== null) {
      window.clearTimeout(shortcutPressTimeoutRef.current);
      shortcutPressTimeoutRef.current = null;
    }

    setIsShortcutPressed(false);
    onGetStarted();
  }, [onGetStarted]);

  const handleConfirmKeyDown = useCallback(
    (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      if (shortcutPressTimeoutRef.current !== null) return;

      setIsShortcutPressed(true);
      shortcutPressTimeoutRef.current = window.setTimeout(() => {
        handleGetStarted();
      }, SHORTCUT_PRESS_DURATION_MS);
    },
    [handleGetStarted]
  );
  useChordKeydown(confirmHotkey ?? 'Mod+Enter', handleConfirmKeyDown, {
    capture: true,
    enabled: confirmHotkey !== null,
  });

  useEffect(() => {
    return () => {
      if (shortcutPressTimeoutRef.current !== null)
        window.clearTimeout(shortcutPressTimeoutRef.current);
    };
  }, []);

  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.3,
        delayChildren: 0.7,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.9,
        ease: [0.25, 0.1, 0.25, 1] as [number, number, number, number], // Properly typed cubic-bezier
      },
    },
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <motion.div
        className="relative z-10 flex w-[min(30rem,calc(100vw-3rem))] flex-col border border-border bg-background-secondary p-8 shadow-md"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <motion.div
          className="mb-8 flex items-center gap-3 border-b border-border pb-4"
          variants={itemVariants}
        >
          <span className="grid size-9 place-items-center border border-border bg-background">
            <img src={HardcoreIcon} alt="" className="size-6" />
          </span>
          <span className="text-tiny tracking-[1.5px] text-foreground-muted uppercase">
            Hardcore desktop
          </span>
        </motion.div>

        <motion.h1 className="text-xl font-medium text-foreground" variants={itemVariants}>
          Welcome to Hardcore.
        </motion.h1>

        <motion.p className="mt-2 text-sm text-foreground-muted" variants={itemVariants}>
          Start a task, work with your engineering files, and review the result beside the chat.
        </motion.p>

        <motion.div className="mt-8 self-start" variants={itemVariants}>
          <div
            className={`transition-transform duration-100 ease-in-out ${
              isShortcutPressed ? 'scale-[0.97]' : ''
            }`}
          >
            <Button variant="primary" onClick={handleGetStarted} size="sm">
              <span className="flex items-center gap-2">
                Open workspace
                <BoundShortcut command="app.confirm" variant="keycaps" />
              </span>
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
