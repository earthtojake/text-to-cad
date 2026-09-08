import { CirclePlus, Search, Settings } from "lucide-react";
import { cn } from "cn";

import { HistoryNav, SidebarToggle } from "@renderer/app/PaneToggles";
import { Button } from "@renderer/components/ui/button";
import { ScrollArea } from "@renderer/components/ui/scroll-area";
import { SessionSection } from "@renderer/features/sidebar/SessionSection";
import { SidebarFilterMenu } from "@renderer/features/sidebar/SidebarFilterMenu";
import { Wordmark } from "@renderer/features/sidebar/Wordmark";
import { useOpenFolder } from "@renderer/hooks/use-open-folder";
import { useProjects } from "@renderer/state/projects";
import { useSessions, useSidebarSections } from "@renderer/state/sessions";
import { useUi } from "@renderer/state/ui";

/**
 * Projects and their threads, as Claude Code's sidebar: a short nav list, then
 * a grey section header per project with a flat list of sessions under it.
 *
 * There is no tree. A project is a **section**, not a row with children —
 * a header in muted text with a chevron for its collapse, `+` for a thread in
 * that project, and the sliders for the filter menu — and a session is one
 * flat row with its state as a leading glyph. `Pinned` is the first section
 * when anything is pinned, and a pinned thread lives *only* there. What each
 * section holds is `lib/sidebar.ts`, a pure function of the index and the
 * filter menu; this file is the frame around it.
 *
 * The top strip is the window's drag region on macOS — the traffic lights sit
 * in it, which is why it is exactly `--titlebar-height` tall and why nothing
 * is drawn in it. The app's name goes *under* it, with the sidebar's own
 * collapse on its left and, on its right, the two controls that act on the
 * whole list: search and the filter menu. Both used to be per project — a
 * search glyph and the sliders on every section header — and neither ever
 * meant one project: the palette searches every thread, and the filters are
 * `settings.sidebar`, global. One list, one place to narrow it.
 */
export function Sidebar() {
  const projects = useProjects((state) => state.projects);
  const ready = useProjects((state) => state.ready);
  const openFolder = useOpenFolder();
  const setActiveSession = useSessions((state) => state.setActive);
  const openSettings = useUi((state) => state.openSettings);
  const toggleCommandPalette = useUi((state) => state.toggleCommandPalette);
  const sections = useSidebarSections();

  return (
    <div className="flex h-full flex-col border-r border-sidebar-border bg-sidebar">
      {/* The traffic lights' strip on macOS — the row the session's and the
          explorer's bars share. The panel's collapse sits right after the
          lights and back/forward right after it, at the same x the session's
          title bar gives them once the panel is gone: a control in this row
          never moves (Codex's placement). */}
      <div
        className="app-drag flex shrink-0 items-center"
        data-sidebar-titlebar
        style={{ height: "var(--titlebar-height)", paddingLeft: "calc(var(--titlebar-inset) + 0.75rem)" }}
      >
        <SidebarToggle />
        <HistoryNav />
      </div>

      <header className="app-drag flex shrink-0 items-center gap-1 pt-0.5 pr-2 pb-1 pl-3">
        <Wordmark />
      </header>

      {/* The nav list, which is one row: `New`, the accent-ringed plus — the
          one row that starts something, and the same action as the app menu's
          `Cmd+N`. Adding a folder is not a row here any more; it is
          `Open folder…` at the bottom of the project chip's menu, where
          picking a folder already happens, and the card below for the one
          state that has no chip to open — no projects at all. */}
      <nav className="flex shrink-0 items-center gap-0.5 px-2 pb-1">
        <div className="min-w-0 flex-1">
          <SidebarLink
            icon={<CirclePlus className="size-4 text-primary" />}
            label="New"
            onClick={() => setActiveSession(null)}
          />
        </div>
        {/* Search and the filters, small, at the row's right: they act on the
            list below, so they sit at its head rather than beside the name. */}
        <Button
          aria-label="Search"
          className="size-7 text-muted-foreground"
          onClick={toggleCommandPalette}
          size="icon-sm"
          variant="ghost"
        >
          <Search className="size-3.5" />
        </Button>
        <SidebarFilterMenu />
      </nav>

      {/* Radix lays the viewport's content out as a table that grows to its
          content; forcing it to block keeps long titles truncating instead of
          scrolling the list sideways when a rename input takes focus. */}
      <ScrollArea className="min-h-0 flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block">
        <div className="min-w-0 px-2 pb-2">
          {sections.map((section) => (
            <SessionSection key={section.id} section={section} />
          ))}
          {ready && projects.length === 0 ? <NoProjects onOpen={() => void openFolder()} /> : null}
        </div>
      </ScrollArea>

      <footer className="flex shrink-0 items-center gap-2 border-t border-sidebar-border px-3 py-2">
        <Button
          aria-label="Settings"
          className="size-7 text-muted-foreground"
          onClick={() => openSettings()}
          size="icon-sm"
          variant="ghost"
        >
          <Settings className="size-4" />
        </Button>
        <span className="truncate text-xs text-muted-foreground">Local · v{__APP_VERSION__}</span>
      </footer>
    </div>
  );
}

function SidebarLink({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        "flex h-7 w-full items-center gap-2 rounded-md px-2 text-[13px]",
        "text-sidebar-foreground/90 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      )}
      onClick={onClick}
      type="button"
    >
      <span className="text-muted-foreground">{icon}</span>
      {label}
    </button>
  );
}

/**
 * The one state that needs a chooser of its own: with no project there is no
 * project chip to open `Open folder…` from, so the card is it.
 */
function NoProjects({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="mt-2 rounded-lg border border-dashed border-sidebar-border px-3 py-4 text-center">
      <p className="text-xs text-muted-foreground">No projects yet.</p>
      <Button className="mt-2 h-7 text-xs" onClick={onOpen} size="sm" variant="secondary">
        Open folder…
      </Button>
    </div>
  );
}
