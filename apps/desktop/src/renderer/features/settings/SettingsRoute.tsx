import { useMemo, useState } from "react";
import { ArrowLeft, Search } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import { ScrollArea } from "@renderer/components/ui/scroll-area";
import { SettingsPage } from "@renderer/features/settings/pages";
import {
  SETTINGS_SECTIONS,
  SETTINGS_SECTION_LABELS,
  useUi,
  type SettingsSection,
} from "@renderer/state/ui";

/** Words that should find a page even though its label does not contain them. */
const SEARCH_ALIASES: Record<SettingsSection, string> = {
  general: "launch login menu bar notifications telemetry usage data project folder",
  agents: "claude codex gemini copilot acp install auth plugin mcp",
  appearance: "theme dark light system accent font contrast",
  git: "branch worktree prefix fetch pull request commit push",
  "cad-runtime": "python cadgen wheel viewer repair occt",
  shortcuts: "keyboard keys accelerator binding",
  about: "version update release channel licenses",
};

/**
 * Settings replaces the whole window (plan §3): back to the app, a search box,
 * grouped nav on the left, one page on the right.
 *
 * A full-window route rather than a modal because these pages have their own
 * navigation and their own search — a dialog would be fighting the shell for
 * the keyboard the entire time it is open.
 */
export function SettingsRoute() {
  const section = useUi((state) => state.settingsSection);
  const setSection = useUi((state) => state.setSettingsSection);
  const close = useUi((state) => state.closeSettings);
  const [query, setQuery] = useState("");

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return SETTINGS_SECTIONS;
    }
    return SETTINGS_SECTIONS.filter((candidate) =>
      `${SETTINGS_SECTION_LABELS[candidate]} ${SEARCH_ALIASES[candidate]}`
        .toLowerCase()
        .includes(needle),
    );
  }, [query]);

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground">
      <header
        className="app-drag flex shrink-0 items-center gap-3 px-3"
        style={{ height: "var(--titlebar-height)" }}
      >
        <div className="w-[60px]" />
        <Button className="app-no-drag h-7 gap-1.5 px-2 text-xs" onClick={close} size="sm" variant="ghost">
          <ArrowLeft className="size-3.5" />
          Back to app
        </Button>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav className="flex w-[232px] shrink-0 flex-col gap-2 border-r px-3 py-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-8 text-sm"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search settings"
              value={query}
            />
          </div>
          <div className="flex flex-col gap-0.5">
            {matches.map((candidate) => (
              <NavItem
                active={candidate === section}
                key={candidate}
                label={SETTINGS_SECTION_LABELS[candidate]}
                onSelect={() => setSection(candidate)}
              />
            ))}
            {matches.length === 0 ? (
              <p className="px-2 py-3 text-xs text-muted-foreground">No matching settings.</p>
            ) : null}
          </div>
        </nav>

        <ScrollArea className="min-h-0 flex-1">
          <div className="mx-auto w-full max-w-[720px] px-8 py-8">
            <h1 className="mb-6 text-xl font-semibold tracking-tight">
              {SETTINGS_SECTION_LABELS[section]}
            </h1>
            <SettingsPage section={section} />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

function NavItem({
  label,
  active,
  onSelect,
}: {
  label: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={cn(
        "rounded-md px-2 py-1.5 text-left text-[13px] transition-colors",
        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60",
      )}
      onClick={onSelect}
      type="button"
    >
      {label}
    </button>
  );
}
