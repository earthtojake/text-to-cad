import {
  Blocks,
  Bug,
  Folder,
  MoreHorizontal,
  PanelLeft,
  PanelRight,
  Ruler,
  ScanSearch,
} from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@renderer/components/ui/tooltip";
import { Composer } from "@renderer/features/session/Composer";
import { useActiveProject } from "@renderer/state/projects";
import { useSettings } from "@renderer/state/settings";

/**
 * One thread, one agent (plan §3).
 *
 * P0 is the empty state: the question, the composer and four suggestions, as
 * one centred column. P1 puts a real ACP session behind it; P2 replaces the
 * centred column with a transcript that scrolls and a composer pinned to the
 * bottom — the arrangement every chat has once there is something to scroll.
 */
export function SessionPane() {
  const project = useActiveProject();
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);

  return (
    <div className="flex h-full flex-col">
      <header
        className="app-drag flex shrink-0 items-center gap-2 px-3"
        style={{ height: "var(--titlebar-height)" }}
      >
        <div className="app-no-drag flex min-w-0 items-center gap-2">
          <Folder className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate text-[13px] font-medium">
            {project ? project.name : "No project"}
          </span>
          <Button
            aria-label="Session actions"
            className="size-6 text-muted-foreground"
            size="icon-xs"
            variant="ghost"
          >
            <MoreHorizontal className="size-3.5" />
          </Button>
        </div>
        <div className="flex-1" />
        <div className="app-no-drag flex items-center gap-0.5">
          <PaneToggle
            active={!(layout?.sidebarCollapsed ?? false)}
            icon={<PanelLeft className="size-3.5" />}
            label="Toggle sidebar"
            onClick={() =>
              void setLayout({ sidebarCollapsed: !(layout?.sidebarCollapsed ?? false) })
            }
          />
          <PaneToggle
            active={!(layout?.explorerCollapsed ?? false)}
            icon={<PanelRight className="size-3.5" />}
            label="Toggle explorer"
            onClick={() =>
              void setLayout({ explorerCollapsed: !(layout?.explorerCollapsed ?? false) })
            }
          />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-6 pb-10">
        <div className="w-full max-w-[620px]">
          <h1 className="text-center text-[22px] leading-tight font-medium tracking-tight text-balance">
            {project ? `What should we build in ${project.name}?` : "Add a project to get started"}
          </h1>
          <p className="mt-2 text-center text-sm text-balance text-muted-foreground">
            {project
              ? "Hardcore runs the agent in this folder, with cadgen and the CAD skills already loaded."
              : "A session always belongs to a folder. Add one from the sidebar."}
          </p>

          <div className="mt-5">
            <Composer projectName={project?.name ?? null} />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <SuggestionCard key={suggestion.title} {...suggestion} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  {
    icon: <ScanSearch className="size-4" />,
    title: "Explore this project",
    description: "Read the models and say how they fit together",
  },
  {
    icon: <Blocks className="size-4" />,
    title: "Model a new part",
    description: "From a description, a sketch or a drawing",
  },
  {
    icon: <Ruler className="size-4" />,
    title: "Measure and validate",
    description: "Check fits, clearances and printability",
  },
  {
    icon: <Bug className="size-4" />,
    title: "Fix a build",
    description: "Track down why a model stopped generating",
  },
] as const;

function SuggestionCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <button
      className="flex items-start gap-3 rounded-xl border bg-card px-3.5 py-3 text-left transition-colors hover:bg-accent"
      type="button"
    >
      <span className="mt-0.5 text-muted-foreground">{icon}</span>
      <span className="min-w-0">
        <span className="block text-[13px] font-medium">{title}</span>
        <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
          {description}
        </span>
      </span>
    </button>
  );
}

function PaneToggle({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          aria-label={label}
          aria-pressed={active}
          className={active ? "size-7" : "size-7 text-muted-foreground"}
          onClick={onClick}
          size="icon-sm"
          variant="ghost"
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
