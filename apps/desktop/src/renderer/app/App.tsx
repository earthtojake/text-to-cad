import { MotionConfig } from "motion/react";
import { useEffect, useRef } from "react";

import { CommandPalette } from "@renderer/app/CommandPalette";
import { focusSessionHome } from "@renderer/app/pane-focus";
import { Shell } from "@renderer/app/Shell";
import { Welcome } from "@renderer/features/onboarding/Welcome";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { useApplyAppearance } from "@renderer/hooks/use-appearance";
import { useSettingsShortcuts } from "@renderer/hooks/use-settings-shortcuts";
import { useApplyTheme } from "@renderer/hooks/use-theme";
import { Toaster } from "@renderer/components/ui/sonner";
import { TooltipProvider } from "@renderer/components/ui/tooltip";
import { hydrate, subscribeToMain } from "@renderer/state/bridge";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useShowWelcome } from "@renderer/state/onboarding";
import { useUi } from "@renderer/state/ui";

/** What the window is called, in the Window menu and to a screen reader: the route, or the session. */
function useDocumentTitle(route: string, showWelcome: boolean): void {
  // The title string, not the session: the row is a fresh object on every
  // `sessions.changed`, and App re-rendering on each status or diff tick
  // re-renders everything under it.
  const sessionTitle = useSessions((state) => state.sessions.find((session) => session.id === state.activeId)?.title.trim() || null);
  const page = route === "settings" ? "Settings" : showWelcome ? "Welcome" : sessionTitle;
  useEffect(() => {
    document.title = page ? `text-to-cad — ${page}` : "text-to-cad";
  }, [page]);
}

/**
 * Leaving Settings unmounts the button that was focused, and the shell mounts fresh: focus
 * goes to the session's composer rather than to the page.
 */
function useFocusAfterSettings(route: string): void {
  const previous = useRef(route);
  useEffect(() => {
    if (previous.current === "settings" && route !== "settings") focusSessionHome();
    previous.current = route;
  }, [route]);
}

/**
 * The window. Three full-window routes — the three-pane shell, Settings and
 * the first-run welcome — plus the palette and the toaster, which belong to
 * none of them.
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
  useDocumentTitle(route, showWelcome);
  useFocusAfterSettings(route);
  const reduceMotion = useSettings((state) => state.settings?.reduceMotion ?? false);

  useEffect(() => {
    const detach = subscribeToMain();
    void hydrate();
    return detach;
  }, []);

  return (
    // The `.reduce-motion` class only reaches CSS animations; the JS ones (the
    // shimmer's sweep) read this. The setting wins, the OS is the fallback.
    <MotionConfig reducedMotion={reduceMotion ? "always" : "user"}>
      <TooltipProvider delayDuration={300}>
        {route === "settings" ? <SettingsRoute /> : showWelcome ? <Welcome /> : <Shell />}
        <CommandPalette />
        {/* Top right, under the title strip: the composer is centred at the
            bottom, and a toast in the bottom corner sat on its send button and
            chips — the refusal of a prompt over the very box that kept it. */}
        <Toaster offset={{ top: "calc(var(--titlebar-height) + 8px)", right: 16 }} position="top-right" />
      </TooltipProvider>
    </MotionConfig>
  );
}
