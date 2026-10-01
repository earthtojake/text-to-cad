import { defaultFilter } from "cmdk";
import { useEffect } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderPlus,
  Folder,
  GitCompare,
  Globe,
  MessageSquare,
  MessageSquarePlus,
  PanelLeft,
  PanelRight,
  PencilRuler,
  Settings,
  SquareTerminal,
  type LucideIcon,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@renderer/components/ui/command";
import { useOpenFolderOrToast } from "@renderer/hooks/use-open-folder";
import { useReturnFocus } from "@renderer/hooks/use-return-focus";
import { isPrimaryModifier } from "@renderer/lib/platform";
import { useExplorer } from "@renderer/state/explorer";
import { useHistory, useHistoryReach } from "@renderer/state/history";
import { leaveWelcome } from "@renderer/state/onboarding";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { SETTINGS_SECTIONS, SETTINGS_SECTION_LABELS, useUi } from "@renderer/state/ui";
import type { ExplorerTabKind } from "@shared/types";

/** One string for the box's placeholder and the dialog's description. */
export const COMMAND_PALETTE_PROMPT = "Search sessions, projects and commands…";
/** The box's name: a placeholder is not one, and it goes when the person types. */
export const COMMAND_PALETTE_LABEL = "Search sessions, projects and commands";

/**
 * Every tab kind the explorer's `+` menu makes, as a Create row. `value` is
 * what cmdk scores: "new" and "open" find all of them, and each carries the
 * words its kind is known by.
 */
const NEW_TAB_ROWS: readonly { kind: ExplorerTabKind; label: string; value: string; icon: LucideIcon }[] = [
  { kind: "file", label: "New file tab", value: "new file tab open", icon: FileText },
  { kind: "review", label: "New review tab", value: "new review tab diff changes git", icon: GitCompare },
  { kind: "terminal", label: "New terminal", value: "new terminal tab shell", icon: SquareTerminal },
  { kind: "browser", label: "New browser tab", value: "new browser tab web url", icon: Globe },
  { kind: "drawing", label: "New drawing", value: "new drawing tab sketch canvas", icon: PencilRuler },
];

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
/**
 * cmdk scores `value` and `keywords` together. A row that names its keywords is searched on
 * those alone (its `value` is a key for selection, not text); every other row is scored as usual.
 */
const scoredOnKeywords = (value: string, search: string, keywords?: string[]): number =>
  defaultFilter(keywords?.length ? keywords.join(" ") : value, search);

export function CommandPalette() {
  const open = useUi((state) => state.commandPaletteOpen);
  const setOpen = useUi((state) => state.setCommandPaletteOpen);
  const toggle = useUi((state) => state.toggleCommandPalette);
  const query = useUi((state) => state.commandPaletteQuery);
  const setQuery = useUi((state) => state.setCommandPaletteQuery);
  const openSettings = useUi((state) => state.openSettings);
  const closeSettings = useUi((state) => state.closeSettings);
  const projects = useProjects((state) => state.projects);
  const setActiveProject = useProjects((state) => state.setActive);
  const openFolder = useOpenFolderOrToast();
  const sessions = useSessions((state) => state.sessions);
  const selectSession = useSessions((state) => state.select);
  const setActiveSession = useSessions((state) => state.setActive);
  const activeSessionId = useSessions((state) => state.activeId);
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);
  const reach = useHistoryReach();
  // No trigger (a chord, the menu, the sidebar's search): Escape gives focus back by hand.
  const returnFocus = useReturnFocus();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && isPrimaryModifier(event)) {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  const openSessions = sessions.filter((session) => !session.archived);

  const run = (action: () => void) => () => {
    setOpen(false);
    action();
  };
  /**
   * A row that changes what the shell shows. Behind Settings, or behind the
   * welcome, that change lands in a window nobody is looking at — so the row
   * leaves them first, the way the menu's New Session leaves Settings
   * (`runUiCommand`). A view toggle leaves Settings but not the welcome:
   * collapsing a sidebar is not a reason to skip first-run.
   */
  const leaveForShell = () => {
    closeSettings();
    leaveWelcome();
  };
  const show = (action: () => void, leave: () => void = leaveForShell) => run(() => {
    leave();
    action();
  });

  return (
    <CommandDialog
      // Anchored near the top, not centred: a centred dialog moves every time
      // the list under the box grows or shrinks, so the box jumps as you type.
      className="top-[20%] translate-y-0"
      description={COMMAND_PALETTE_PROMPT}
      filter={scoredOnKeywords}
      label={COMMAND_PALETTE_LABEL}
      {...returnFocus}
      onOpenChange={setOpen}
      open={open}
      title="Command palette"
    >
      <CommandInput
        onValueChange={setQuery}
        placeholder={COMMAND_PALETTE_PROMPT}
        value={query}
      />
      {/* No separators: a separator is not a listbox's child (axe aria-required-children). The
          groups are the boundaries, a rule drawn over each visible group after the first. */}
      <CommandList className="[&_[cmdk-group]:not([hidden])~[cmdk-group]:not([hidden])]:border-t" label="Commands">
        <CommandEmpty>No matches.</CommandEmpty>

        {/* Threads first: the box is most often a thread's name, and a
            project's search glyph seeds it with the project's, which every
            one of these rows carries. */}
        {openSessions.length > 0 ? (
          <CommandGroup heading="Sessions">
            {openSessions.map((session) => {
              const project = projects.find((candidate) => candidate.id === session.projectId);
              return (
                <CommandItem
                  key={session.id}
                  onSelect={show(() => selectSession(session.id))}
                  // cmdk keys selection by value, so it is the id: two "New session" rows in one
                  // folder would otherwise be one row twice over. What is searched is the
                  // keywords (`scoredOnKeywords`), so a hex id is not text to match "dead" or "ace".
                  keywords={[session.title, project?.name ?? "", session.branch ?? ""]}
                  value={session.id}
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
        ) : null}

        <CommandGroup heading="Projects">
          {projects.filter(project => sessions.some(session => session.projectId === project.id && !session.archived)).map((project) => (
            <CommandItem
              key={project.id}
              onSelect={show(() => { setActiveProject(project.id); setActiveSession(null); })}
              // The name is searched, not the path: every project under ~/code matches "code".
              keywords={[project.name]}
              value={project.id}
            >
              <Folder className="size-4" />
              <span className="truncate">{project.name}</span>
              <span className="ml-auto truncate text-xs text-muted-foreground">{project.path}</span>
            </CommandItem>
          ))}
          {/* The keyboard's way to the chooser the project chip's menu ends
              with. `add project` stays in the search terms: it is what
              somebody who remembers the old row will type. */}
          <CommandItem
            // Only a folder actually chosen leaves Settings: a cancelled
            // chooser changed nothing, and Settings is where the person was.
            onSelect={run(() => void openFolder().then((project) => { if (project) leaveForShell(); }))}
            value="open folder add project"
          >
            <FolderPlus className="size-4" />
            Open folder…
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading="Create">
          <CommandItem onSelect={show(() => setActiveSession(null))} value="new session chat">
            <MessageSquarePlus className="size-4" />
            New session
          </CommandItem>
          {/* The explorer belongs to a session (`Shell`): no session, no tabs. */}
          {activeSessionId
            ? NEW_TAB_ROWS.map(({ kind, label, value, icon: Icon }) => (
                <CommandItem key={kind} onSelect={show(() => { useExplorer.getState().open(kind); })} value={value}>
                  <Icon className="size-4" />
                  {label}
                </CommandItem>
              ))
            : null}
        </CommandGroup>

        <CommandGroup heading="View">
          <CommandItem
            onSelect={show(
              () => void setLayout({ sidebarCollapsed: !(layout?.sidebarCollapsed ?? false) }),
              closeSettings,
            )}
            value="toggle sidebar"
          >
            <PanelLeft className="size-4" />
            Toggle sidebar
          </CommandItem>
          {/* No session, no explorer to toggle (`Shell`). */}
          {activeSessionId ? (
            <CommandItem
              onSelect={show(() => useExplorer.getState().toggleCollapsed(), closeSettings)}
              value="toggle explorer"
            >
              <PanelRight className="size-4" />
              Toggle explorer
            </CommandItem>
          ) : null}
          {/* The top level's history (`state/history.ts`). Offered only when
              there is somewhere to go, since a palette row cannot be muted
              the way the two arrows in the title strip are. */}
          {reach.back ? (
            <CommandItem onSelect={show(() => useHistory.getState().back(), closeSettings)} value="back navigate history">
              <ChevronLeft className="size-4" />
              Back
            </CommandItem>
          ) : null}
          {reach.forward ? (
            <CommandItem onSelect={show(() => useHistory.getState().forward(), closeSettings)} value="forward navigate history">
              <ChevronRight className="size-4" />
              Forward
            </CommandItem>
          ) : null}
        </CommandGroup>

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
