import { SlidersHorizontal } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { MenuKind } from "@renderer/features/sidebar/menu";
import { ProjectMenuItems } from "@renderer/features/sidebar/project-menu";
import { useSettings, useSidebarSettings } from "@renderer/state/settings";
import type {
  Project,
  SidebarEnvironmentFilter,
  SidebarGroupBy,
  SidebarSortBy,
  SidebarStatusFilter,
} from "@shared/types";

/**
 * How the list is read: which threads it holds, how they are grouped, in
 * what order, and what each row says. Reached from the sliders glyph on a
 * section header.
 *
 * The settings are **global**, not per project (`settings.sidebar`), even
 * though the menu is opened from one project's header: "show me the archived
 * ones" is a question about how the whole list is read, and a person who set
 * it on one header and found the next unchanged would have to set it once per
 * project. The header the menu was opened from decides only one thing — which
 * project `Project…` acts on.
 */
export function SidebarFilterMenu({
  project,
  onRenameProject,
}: {
  /** The header this was opened from, when it is a project's. */
  project: Project | null;
  onRenameProject: () => void;
}) {
  const filters = useSidebarSettings();
  const setSidebar = useSettings((state) => state.setSidebar);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label="Filters"
          className="size-5 shrink-0 text-muted-foreground data-[state=open]:opacity-100"
          size="icon-xs"
          variant="ghost"
        >
          <SlidersHorizontal className="size-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <Choice
          items={STATUS}
          label="Status"
          onChange={(status) => void setSidebar({ status })}
          value={filters.status}
        />
        <Choice
          items={ENVIRONMENT}
          label="Environment"
          onChange={(environment) => void setSidebar({ environment })}
          value={filters.environment}
        />
        <DropdownMenuSeparator />
        <Choice
          items={GROUP_BY}
          label="Group by"
          onChange={(groupBy) => void setSidebar({ groupBy })}
          value={filters.groupBy}
        />
        <Choice
          items={SORT_BY}
          label="Sort by"
          onChange={(sortBy) => void setSidebar({ sortBy })}
          value={filters.sortBy}
        />
        <DropdownMenuSeparator />
        <DropdownMenuCheckboxItem
          checked={filters.showEmptyGroups}
          onCheckedChange={(showEmptyGroups) => void setSidebar({ showEmptyGroups })}
        >
          Show empty groups
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={filters.showBranch}
          onCheckedChange={(showBranch) => void setSidebar({ showBranch })}
        >
          Show branch
        </DropdownMenuCheckboxItem>
        {project ? (
          <>
            <DropdownMenuSeparator />
            {/* The project's own actions, so nothing that used to be behind
                the header's `…` is only reachable with a mouse. */}
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>Project…</DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="w-48">
                <MenuKind.Provider value="dropdown">
                  <ProjectMenuItems onRename={onRenameProject} project={project} />
                </MenuKind.Provider>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * One `Label  Value ›` row over a submenu of radio items — the shape the whole
 * top half of this menu has, so it is written once. The value on the row is
 * the point: the menu answers "what is it set to" without being opened twice.
 */
function Choice<T extends string>({
  label,
  value,
  items,
  onChange,
}: {
  label: string;
  value: T;
  items: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const current = items.find((item) => item.value === value);
  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger>
        <span className="flex-1">{label}</span>
        <span className="text-muted-foreground">{current?.label ?? value}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-40">
        <DropdownMenuRadioGroup onValueChange={(next) => onChange(next as T)} value={value}>
          {items.map((item) => (
            <DropdownMenuRadioItem key={item.value} value={item.value}>
              {item.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

const STATUS: readonly { value: SidebarStatusFilter; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];

/** Our environments are the git modes, as the composer's chip names them. */
const ENVIRONMENT: readonly { value: SidebarEnvironmentFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "local", label: "Local" },
  { value: "worktree", label: "Worktree" },
];

const GROUP_BY: readonly { value: SidebarGroupBy; label: string }[] = [
  { value: "project", label: "Project" },
  { value: "none", label: "None" },
];

const SORT_BY: readonly { value: SidebarSortBy; label: string }[] = [
  { value: "activity", label: "Last activity" },
  { value: "created", label: "Created" },
  { value: "name", label: "Name" },
];
