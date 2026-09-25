import { useEffect } from "react";

import { CommandPalette } from "@renderer/app/CommandPalette";
import { Shell } from "@renderer/app/Shell";
import { Welcome } from "@renderer/features/onboarding/Welcome";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { useApplyAppearance } from "@renderer/hooks/use-appearance";
import { useSettingsShortcuts } from "@renderer/hooks/use-settings-shortcuts";
import { useApplyTheme } from "@renderer/hooks/use-theme";
import { Toaster } from "@renderer/components/ui/sonner";
import { TooltipProvider } from "@renderer/components/ui/tooltip";
import { hydrate, subscribeToMain } from "@renderer/state/bridge";
import { useShowWelcome } from "@renderer/state/onboarding";
import { useUi } from "@renderer/state/ui";

/**
 * The window. Two full-window routes — the three-pane shell and Settings —
 * plus the palette and the toaster, which belong to neither.
 */
export function App() {
  const route = useUi((state) => state.route);
  // First run: the welcome covers the shell until it is finished or skipped.
  const showWelcome = useShowWelcome();
  useApplyTheme();
  // The accent, the UI scale, the code font, reduced motion and the
  // translucent sidebar are tokens on <html> (Settings › Appearance).
  useApplyAppearance();
  useSettingsShortcuts();

  useEffect(() => {
    const detach = subscribeToMain();
    void hydrate();
    return detach;
  }, []);

  return (
    <TooltipProvider delayDuration={300}>
      {route === "settings" ? <SettingsRoute /> : showWelcome ? <Welcome /> : <Shell />}
      <CommandPalette />
      <Toaster position="bottom-right" />
    </TooltipProvider>
  );
}
