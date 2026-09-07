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
import { useSettings, useSidebarSettings } from "@renderer/state/settings";
import type {
  SidebarEnvironmentFilter,
  SidebarGroupBy,
  SidebarSortBy,
  SidebarStatusFilter,
} from "@shared/types";

/**
 * How the list is read: which threads it holds, how they are grouped, in
 * what order, and what each row says. Reached from the sliders glyph in the
 * panel's header, beside search.
 *
 * The settings are **global** (`settings.sidebar`): "show me the archived
 * ones" is a question about how the whole list is read, not about one folder.
 * The menu used to hang off a project's section header, with that project's
 * own actions as a `Project…` submenu at the bottom — a global menu that
 * secretly belonged to whichever header you opened it from. Now it is where
 * it acts, and the project actions are on the header's right-click, which is
 * the one place they were ever a project's.
 */
export function SidebarFilterMenu() {
  const filters = useSidebarSettings();
  const setSidebar = useSettings((state) => state.setSidebar);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label="Filters"
          className="app-no-drag size-7 shrink-0 text-muted-foreground"
          size="icon-sm"
          variant="ghost"
        >
          <SlidersHorizontal className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      {/* Anchored to the trigger's right edge: it is the last control in the
          panel's header, and a menu that opened rightward from there would
          be pushed back by the collision boundary every time. */}
      <DropdownMenuContent align="end" className="w-56">
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
