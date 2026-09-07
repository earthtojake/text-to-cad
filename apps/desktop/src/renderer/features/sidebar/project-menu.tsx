import { FolderOpen, MessageSquarePlus, Pencil, Trash2 } from "lucide-react";

import { MenuItem, MenuSeparator } from "@renderer/features/sidebar/menu";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project } from "@shared/types";

/**
 * A project's actions, written once and drawn in the two places a person
 * looks for them: right-clicking the project's section header, and the last
 * item of the filter menu (`Project…`).
 *
 * The header itself carries only what belongs on a header — the collapse, and
 * the three glyphs the design gives it — so these are not a `…` button of
 * their own any more. Both routes are real: a right-click is where a list
 * puts them, and the menu keeps them reachable from the keyboard.
 */
export function ProjectMenuItems({
  project,
  onRename,
}: {
  project: Project;
  onRename: () => void;
}) {
  const setActiveProject = useProjects((state) => state.setActive);
  const removeProject = useProjects((state) => state.remove);
  const setActiveSession = useSessions((state) => state.setActive);

  return (
    <>
      <MenuItem
        icon={<MessageSquarePlus />}
        label="New chat here"
        onSelect={() => {
          setActiveProject(project.id);
          setActiveSession(null);
        }}
      />
      <MenuItem icon={<Pencil />} label="Rename" onSelect={onRename} />
      <MenuItem
        label="Copy path"
        onSelect={() => void navigator.clipboard.writeText(project.path)}
      />
      <MenuItem
        icon={<FolderOpen />}
        label="Reveal in Finder"
        onSelect={() => void window.hardcore.shell.showItemInFolder({ path: project.path })}
      />
      <MenuSeparator />
      <MenuItem
        destructive
        icon={<Trash2 />}
        label="Remove from Hardcore"
        onSelect={() => void removeProject(project.id)}
      />
    </>
  );
}
