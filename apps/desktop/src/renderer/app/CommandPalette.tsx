import { useEffect } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FolderPlus,
  Folder,
  MessageSquare,
  MessageSquarePlus,
  PanelLeft,
  PanelRight,
  Settings,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@renderer/components/ui/command";
import { useOpenFolder } from "@renderer/hooks/use-open-folder";
import { useExplorer } from "@renderer/state/explorer";
import { useHistory, useHistoryReach } from "@renderer/state/history";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { SETTINGS_SECTIONS, SETTINGS_SECTION_LABELS, useUi } from "@renderer/state/ui";

/**
 * Cmd/Ctrl+K. Switches project, jumps to a thread, and opens any Settings
 * page.
 *
 * There is one way to narrow the list — the box — and every row carries the
 * words it can be found by in its `value`, project names included, so typing
 * a project's name is how its threads get filtered. A second, invisible
 * filter would be a list nobody could see the shape of. This is the app's
 * only search: the glyph that used to sit on each project's sidebar header
 * and seed the box with that project's name is gone, and the one in the
 * panel's header opens this empty.
 *
 * The shortcut is bound here as well as in the app menu: the menu accelerator
 * is the one that works when focus is inside a webview or a native dialog, and
 * this one is the one that works when the menu is hidden. Both end at the same
 * store action.
 */
export function CommandPalette() {
  const open = useUi((state) => state.commandPaletteOpen);
  const setOpen = useUi((state) => state.setCommandPaletteOpen);
  const toggle = useUi((state) => state.toggleCommandPalette);
  const query = useUi((state) => state.commandPaletteQuery);
  const setQuery = useUi((state) => state.setCommandPaletteQuery);
  const openSettings = useUi((state) => state.openSettings);
  const projects = useProjects((state) => state.projects);
  const activeProjectId = useProjects((state) => state.activeId);
  const setActiveProject = useProjects((state) => state.setActive);
  const openFolder = useOpenFolder();
  const sessions = useSessions((state) => state.sessions);
  const selectSession = useSessions((state) => state.select);
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);
  const reach = useHistoryReach();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  const run = (action: () => void) => () => {
    setOpen(false);
    action();
  };

  return (
    <CommandDialog
      description="Search projects, settings and commands"
      onOpenChange={setOpen}
      open={open}
      title="Command palette"
    >
      <CommandInput
        onValueChange={setQuery}
        placeholder="Search projects and commands…"
        value={query}
      />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

        {/* Threads first: the box is most often a thread's name, and a
            project's search glyph seeds it with the project's, which every
            one of these rows carries. */}
        <CommandGroup heading="Sessions">
          {sessions.map((session) => {
            const project = projects.find((candidate) => candidate.id === session.projectId);
            return (
              <CommandItem
                key={session.id}
                onSelect={run(() => selectSession(session.id))}
                value={`${session.title} ${project?.name ?? ""} ${session.branch ?? ""}`}
              >
                <MessageSquare className="size-4" />
                <span className="truncate">{session.title}</span>
                {project ? (
                  <span className="ml-auto truncate text-xs text-muted-foreground">
                    {project.name}
                  </span>
                ) : null}
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Projects">
          {projects.map((project) => (
            <CommandItem
              key={project.id}
              onSelect={run(() => setActiveProject(project.id))}
              value={`${project.name} ${project.path}`}
            >
              <Folder className="size-4" />
              <span className="truncate">{project.name}</span>
              <span className="ml-auto truncate text-xs text-muted-foreground">{project.path}</span>
            </CommandItem>
          ))}
          {/* The keyboard's way to the chooser the project chip's menu ends
              with. `add project` stays in the search terms: it is what
              somebody who remembers the old row will type. */}
          <CommandItem onSelect={run(() => void openFolder())} value="open folder add project">
            <FolderPlus className="size-4" />
            Open folder…
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="View">
          <CommandItem
            onSelect={run(() =>
              void setLayout({ sidebarCollapsed: !(layout?.sidebarCollapsed ?? false) }),
            )}
            value="toggle sidebar"
          >
            <PanelLeft className="size-4" />
            Toggle sidebar
          </CommandItem>
          {/* No project, no explorer to toggle (`Shell`). */}
          {activeProjectId ? (
            <CommandItem
              onSelect={run(() => useExplorer.getState().toggleCollapsed())}
              value="toggle explorer"
            >
              <PanelRight className="size-4" />
              Toggle explorer
            </CommandItem>
          ) : null}
          <CommandItem onSelect={run(() => undefined)} value="new session chat">
            <MessageSquarePlus className="size-4" />
            New session
          </CommandItem>
          {/* The top level's history (`state/history.ts`). Offered only when
              there is somewhere to go, since a palette row cannot be muted
              the way the two arrows in the title strip are. */}
          {reach.back ? (
            <CommandItem onSelect={run(() => useHistory.getState().back())} value="back navigate history">
              <ChevronLeft className="size-4" />
              Back
            </CommandItem>
          ) : null}
          {reach.forward ? (
            <CommandItem onSelect={run(() => useHistory.getState().forward())} value="forward navigate history">
              <ChevronRight className="size-4" />
              Forward
            </CommandItem>
          ) : null}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Settings">
          {SETTINGS_SECTIONS.map((section) => (
            <CommandItem
              key={section}
              onSelect={run(() => openSettings(section))}
              value={`settings ${SETTINGS_SECTION_LABELS[section]}`}
            >
              <Settings className="size-4" />
              {SETTINGS_SECTION_LABELS[section]}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
