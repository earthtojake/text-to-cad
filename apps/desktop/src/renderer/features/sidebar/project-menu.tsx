import { FolderOpen, MessageSquarePlus, Pencil, Trash2 } from "lucide-react";

import { MenuItem, MenuSeparator } from "@renderer/features/sidebar/menu";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project } from "@shared/types";

/**
 * A project's actions, written once: right-clicking the project's section
 * header, which is where a list puts them.
 *
 * The header itself carries only what belongs on a header — the collapse and
 * `+` — so these are not a `…` button of their own. They were also the
 * bottom of the filter menu (`Project…`) while that menu hung off a project's
 * header; the menu is the panel's now, and a global menu is no place for one
 * folder's actions. Drawn through `menu.tsx` so the list is not written twice
 * for Radix's two menu components.
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
