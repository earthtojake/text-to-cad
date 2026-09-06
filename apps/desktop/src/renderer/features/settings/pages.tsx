/**
 * The seven Settings pages (plan §10), each in its own module under `./pages/`.
 *
 * This file is only the switch. A page is a list of rows built from
 * `./SettingCard`, so the layout is not something a page gets to decide, and
 * search (`./search.tsx`) has one row component to hook into rather than seven
 * pages to index.
 */
import { AboutPage } from "@renderer/features/settings/pages/AboutPage";
import { AgentsPage } from "@renderer/features/settings/pages/AgentsPage";
import { AppearancePage } from "@renderer/features/settings/pages/AppearancePage";
import { CadRuntimePage } from "@renderer/features/settings/pages/CadRuntimePage";
import { GeneralPage } from "@renderer/features/settings/pages/GeneralPage";
import { GitPage } from "@renderer/features/settings/pages/GitPage";
import { ShortcutsPage } from "@renderer/features/settings/pages/ShortcutsPage";
import type { SettingsSection } from "@renderer/state/ui";

export function SettingsPage({ section }: { section: SettingsSection }) {
  switch (section) {
    case "general":
      return <GeneralPage />;
    case "agents":
      return <AgentsPage />;
    case "appearance":
      return <AppearancePage />;
    case "git":
      return <GitPage />;
    case "cad-runtime":
      return <CadRuntimePage />;
    case "shortcuts":
      return <ShortcutsPage />;
    case "about":
      return <AboutPage />;
  }
}
