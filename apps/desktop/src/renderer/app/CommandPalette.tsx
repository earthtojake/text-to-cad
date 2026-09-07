import { useEffect } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FolderPlus,
  Folder,
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
import { useExplorer } from "@renderer/state/explorer";
import { useHistory, useHistoryReach } from "@renderer/state/history";
import { useProjects } from "@renderer/state/projects";
import { useSettings } from "@renderer/state/settings";
import { SETTINGS_SECTIONS, SETTINGS_SECTION_LABELS, useUi } from "@renderer/state/ui";

/**
 * Cmd/Ctrl+K. Switches project and opens any Settings page.
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
  const openSettings = useUi((state) => state.openSettings);
  const projects = useProjects((state) => state.projects);
  const activeProjectId = useProjects((state) => state.activeId);
  const setActiveProject = useProjects((state) => state.setActive);
  const addProject = useProjects((state) => state.add);
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
      <CommandInput placeholder="Search projects and commands…" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

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
          <CommandItem onSelect={run(() => void addProject())} value="add project folder">
            <FolderPlus className="size-4" />
            Add project…
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
