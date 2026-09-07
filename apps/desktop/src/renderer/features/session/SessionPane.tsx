import { useEffect } from "react";
import { FolderOpen } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { useOpenFolder } from "@renderer/hooks/use-open-folder";
import { useActiveProject } from "@renderer/state/projects";
import { useActiveSession, useSessions } from "@renderer/state/sessions";

import { NewSession } from "./NewSession";
import { SessionHeader } from "./SessionHeader";
import { SessionView } from "./SessionView";

/**
 * One thread, one agent (plan §3). Three states: no project yet, the
 * new-session state for the active project, and a session.
 *
 * Cmd/Ctrl+N is bound here as well as in the app menu — the menu's
 * accelerator is the one that works while focus is in a webview, this one
 * works when the menu is hidden — and both end at the same store action.
 */
export function SessionPane() {
  const project = useActiveProject();
  const session = useActiveSession();
  const setActiveSession = useSessions((state) => state.setActive);
  const openFolder = useOpenFolder();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "n" && (event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        setActiveSession(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setActiveSession]);

  if (session) {
    return <SessionView key={session.id} session={session} />;
  }

  return (
    <div className="flex h-full flex-col">
      <SessionHeader session={null} title={project ? project.name : "No project"} />
      {project ? (
        <NewSession key={project.id} project={project} />
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 pb-10" data-no-project>
          <div className="w-full max-w-[720px]">
            <h1 className="text-center text-[22px] leading-tight font-medium tracking-tight text-balance">
              Add a project to get started
            </h1>
            <p className="mt-2 text-center text-[13px] text-balance text-muted-foreground">
              A session always belongs to a folder.
            </p>
            {/* The chooser itself, not a sentence pointing at one: with no
                project there is no project chip to open `Open folder…` from,
                and this screen is the whole app until there is. */}
            <div className="mt-4 flex justify-center">
              <Button onClick={() => void openFolder()} size="sm" variant="secondary">
                <FolderOpen className="size-3.5" />
                Open folder…
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
