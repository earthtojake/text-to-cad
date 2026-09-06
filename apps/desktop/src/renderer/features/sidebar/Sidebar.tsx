import { FolderPlus, MessageSquarePlus, Search, Settings } from "lucide-react";
import { cn } from "cn";

import { SidebarToggle } from "@renderer/app/PaneToggles";
import { Button } from "@renderer/components/ui/button";
import { ScrollArea } from "@renderer/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@renderer/components/ui/tooltip";
import { ProjectRow } from "@renderer/features/sidebar/ProjectRow";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useUi } from "@renderer/state/ui";

/**
 * Projects, and the sessions under them. Codex's shape (plan §2): a title row,
 * fixed links, the project list, and a footer.
 *
 * The top strip is the window's drag region on macOS — the traffic lights sit
 * in it, which is why it is exactly `--titlebar-height` tall and why nothing
 * is drawn in it. The app's name goes *under* it, at Codex's size, with the
 * sidebar's own collapse on its left and search on its right.
 */
export function Sidebar() {
  const projects = useProjects((state) => state.projects);
  const ready = useProjects((state) => state.ready);
  const addProject = useProjects((state) => state.add);
  const setActiveSession = useSessions((state) => state.setActive);
  const openSettings = useUi((state) => state.openSettings);
  const toggleCommandPalette = useUi((state) => state.toggleCommandPalette);

  return (
    <div className="flex h-full flex-col border-r border-sidebar-border bg-sidebar">
      {/* The traffic lights' strip on macOS: drag region, and nothing else. */}
      <div className="app-drag shrink-0" style={{ height: "var(--titlebar-height)" }} />

      <header className="app-drag flex shrink-0 items-center gap-1 pt-0.5 pr-2 pb-1 pl-1.5">
        <SidebarToggle />
        <span className="app-no-drag truncate text-[15px] font-semibold tracking-tight">Hardcore</span>
        <div className="flex-1" />
        <Button
          aria-label="Search"
          className="app-no-drag size-7 text-muted-foreground"
          onClick={toggleCommandPalette}
          size="icon-sm"
          variant="ghost"
        >
          <Search className="size-3.5" />
        </Button>
      </header>

      <nav className="shrink-0 px-2 pb-2">
        <SidebarLink
          icon={<MessageSquarePlus className="size-4" />}
          label="New chat"
          onClick={() => setActiveSession(null)}
        />
      </nav>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center justify-between px-4 pt-1 pb-1.5">
          <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Projects
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label="Add project"
                className="size-6 text-muted-foreground"
                onClick={() => void addProject()}
                size="icon-xs"
                variant="ghost"
              >
                <FolderPlus className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Add a project folder</TooltipContent>
          </Tooltip>
        </div>

        {/* Radix lays the viewport's content out as a table that grows to its
            content; forcing it to block keeps long titles truncating instead of
            scrolling the list sideways when a rename input takes focus. */}
        <ScrollArea className="min-h-0 flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block">
          <div className="min-w-0 px-2 pb-2">
            {projects.map((project) => (
              <ProjectRow key={project.id} project={project} />
            ))}
            {ready && projects.length === 0 ? <NoProjects onAdd={() => void addProject()} /> : null}
          </div>
        </ScrollArea>
      </div>

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

function NoProjects({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="mt-2 rounded-lg border border-dashed border-sidebar-border px-3 py-4 text-center">
      <p className="text-xs text-muted-foreground">No projects yet.</p>
      <Button className="mt-2 h-7 text-xs" onClick={onAdd} size="sm" variant="secondary">
        Add a folder
      </Button>
    </div>
  );
}
