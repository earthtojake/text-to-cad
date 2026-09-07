import { useState } from "react";
import { Archive, Folder, MoreHorizontal, Pencil, Trash2, Unplug } from "lucide-react";

import { ExplorerToggle, SidebarToggle } from "@renderer/app/PaneToggles";
import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { useAcp } from "@renderer/state/acp";
import { useSessions } from "@renderer/state/sessions";
import { useExplorer } from "@renderer/state/explorer";
import { useSettings } from "@renderer/state/settings";
import type { Session } from "@shared/types";

/**
 * The session's title bar (plan §2): folder icon, the title (from the
 * first prompt; click to edit), a `…` menu; the explorer's toggle on the
 * right. The strip is the window's drag region, so the controls opt out of it.
 *
 * The two pane toggles keep their places on screen whatever the panes do
 * (Codex's rule): the sidebar's is right after the traffic lights — in the
 * sidebar's own title strip while it is open, here once it is gone — and
 * the explorer's is at the window's right edge — here while the explorer is
 * shut, in the explorer's tab strip once it is open.
 */
export function SessionHeader({
  session,
  title,
}: {
  /** Null in the new-session state, where the title is the project. */
  session: Session | null;
  title: string;
}) {
  const rename = useSessions((state) => state.rename);
  const archive = useSessions((state) => state.archive);
  const remove = useSessions((state) => state.remove);
  const closeSession = useAcp((state) => state.close);
  const sidebarCollapsed = useSettings((state) => state.settings?.layout.sidebarCollapsed ?? false);
  const explorerCollapsed = useExplorer((state) => state.collapsed);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  const startEditing = () => {
    if (session) {
      setDraft(title);
      setEditing(true);
    }
  };

  const commit = () => {
    setEditing(false);
    if (session && draft.trim() && draft.trim() !== session.title) {
      void rename(session.id, draft);
    }
  };

  return (
    <header
      className="app-drag flex shrink-0 items-center gap-2 border-b px-3"
      data-session-header
      style={{ height: "var(--titlebar-height)" }}
    >
      {/* The window's left edge once the sidebar is gone. */}
      {sidebarCollapsed ? <SidebarToggle /> : null}
      <div className="app-no-drag flex min-w-0 items-center gap-2">
        <Folder className="size-3.5 shrink-0 text-muted-foreground" />
        {editing && session ? (
          <input
            aria-label="Session title"
            autoFocus
            className="min-w-[200px] bg-transparent text-[13px] font-medium outline-none"
            onBlur={commit}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                commit();
              } else if (event.key === "Escape") {
                setEditing(false);
              }
            }}
            value={draft}
          />
        ) : (
          <button
            className="truncate text-[13px] font-medium"
            data-session-title
            disabled={!session}
            onClick={startEditing}
            title={session ? "Rename" : undefined}
            type="button"
          >
            {title}
          </button>
        )}
        {session ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button aria-label="Session actions" className="size-6 text-muted-foreground" size="icon-xs" variant="ghost">
                <MoreHorizontal className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-44">
              <DropdownMenuItem onSelect={startEditing}>
                <Pencil />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void navigator.clipboard.writeText(session.cwd)}>
                Copy path
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => void window.hardcore.shell.showItemInFolder({ path: session.cwd })}
              >
                Reveal in Finder
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void closeSession(session.id)}>
                <Unplug />
                Disconnect agent
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void archive(session.id, true)}>
                <Archive />
                Archive
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void remove(session.id)} variant="destructive">
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
      <div className="flex-1" />
      {/* The window's right edge while the explorer is shut; open, the
          explorer's own strip holds the toggle at that same edge. */}
      {explorerCollapsed ? (
        <div className="app-no-drag flex items-center gap-0.5">
          <ExplorerToggle />
        </div>
      ) : null}
    </header>
  );
}
