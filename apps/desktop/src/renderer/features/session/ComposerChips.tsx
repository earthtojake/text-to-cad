import {
  Bot,
  Check,
  ChevronDown,
  Folder,
  GitBranch,
  GitFork,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { cn } from "cn";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { useAgents, useInstalledAgents } from "@renderer/state/agents";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";
import type { ApprovalMode, ConfigOption, SessionMode } from "@shared/acp/types";
import type { AgentStatus } from "@shared/agents";
import type { GitMode, Project } from "@shared/types";

/**
 * The composer's context strip (plan §2, §6). Every chip is the same
 * shape: an icon, a short label, a chevron when it opens a menu. A new
 * session shows Project / Git mode / Agent in a strip above the composer and
 * Approval in it; a live session shows Approval and the agent's modes on the
 * left, the model and its other options on the right. What a session cannot
 * change — its agent, its project — is the title bar's and the sidebar's.
 */
export function Chip({
  icon,
  label,
  detail,
  menu,
  title,
  className,
  testId,
  maxWidth = 200,
}: {
  icon: React.ReactNode;
  maxWidth?: number;
  label: string;
  /** Muted text after the label. */
  detail?: string | null;
  /** When present the chip is a menu trigger. */
  menu?: React.ReactNode;
  title?: string;
  className?: string;
  testId?: string;
}) {
  const body = (
    <button
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-1.5 text-[12px] leading-none text-muted-foreground transition-colors",
        menu ? "hover:bg-accent hover:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground" : "cursor-default",
        className,
      )}
      data-chip={testId}
      style={{ maxWidth }}
      title={title}
      type="button"
    >
      <span className="[&>svg]:size-3.5">{icon}</span>
      {label ? <span className="truncate text-foreground/90">{label}</span> : null}
      {detail ? <span className="truncate">{detail}</span> : null}
      {menu ? <ChevronDown className="size-3 opacity-70" /> : null}
    </button>
  );
  if (!menu) {
    return body;
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{body}</DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64" side="top">
        {menu}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* -------------------------------------------------------------------------- */
/* New-session chips                                                           */
/* -------------------------------------------------------------------------- */

export function AgentChip({
  agentId,
  onChange,
}: {
  agentId: string | null;
  onChange: (agentId: string) => void;
}) {
  const agents = useAgents((state) => state.agents);
  const installed = useInstalledAgents();
  const openSettings = useUi((state) => state.openSettings);
  const current = agents.find((agent) => agent.id === agentId) ?? null;
  const missing = agents.filter((agent) => !installed.includes(agent));

  return (
    <Chip
      detail={current ? authDetail(current) : null}
      icon={<Bot />}
      label={current?.name ?? "Choose an agent"}
      menu={
        <>
          <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">Installed</DropdownMenuLabel>
          {installed.length === 0 ? (
            <DropdownMenuItem disabled>No agents found on this machine</DropdownMenuItem>
          ) : null}
          <DropdownMenuRadioGroup onValueChange={onChange} value={agentId ?? ""}>
            {installed.map((agent) => (
              <DropdownMenuRadioItem key={agent.id} value={agent.id}>
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="truncate">{agent.name}</span>
                  <span className="ml-auto text-[11px] text-muted-foreground">{authDetail(agent) ?? agent.version ?? ""}</span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          {missing.length > 0 ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => openSettings("agents")}>
                <span className="flex flex-col">
                  <span>Install another agent…</span>
                  <span className="text-[11px] text-muted-foreground">
                    {missing
                      .slice(0, 4)
                      .map((agent) => agent.name)
                      .join(", ")}
                    {missing.length > 4 ? ` and ${missing.length - 4} more` : ""} in Settings › Agents
                  </span>
                </span>
              </DropdownMenuItem>
            </>
          ) : null}
        </>
      }
      maxWidth={150}
      testId="agent"
    />
  );
}

function authDetail(agent: AgentStatus): string | null {
  switch (agent.auth) {
    case "unauthenticated":
      return "not signed in";
    case "authenticated":
    case "not-required":
    case "unknown":
      return agent.installed ? null : "via npx";
  }
}

export function ProjectChip({ project, onChange }: { project: Project | null; onChange: (id: string) => void }) {
  const projects = useProjects((state) => state.projects);
  const addProject = useProjects((state) => state.add);
  return (
    <Chip
      icon={<Folder />}
      label={project?.name ?? "No project"}
      menu={
        <>
          <DropdownMenuRadioGroup onValueChange={onChange} value={project?.id ?? ""}>
            {projects.map((candidate) => (
              <DropdownMenuRadioItem key={candidate.id} value={candidate.id}>
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{candidate.name}</span>
                  <span className="truncate text-[11px] text-muted-foreground">{candidate.path}</span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => void addProject()}>Add project…</DropdownMenuItem>
        </>
      }
      maxWidth={150}
      testId="project"
      title={project?.path}
    />
  );
}

const GIT_MODES: { value: GitMode; label: string; description: string; icon: React.ReactNode }[] = [
  { value: "none", label: "Local", description: "Work in the project directory; git is left alone", icon: <Folder /> },
  { value: "checkout", label: "Current branch", description: "Work in the project directory on its branch", icon: <GitBranch /> },
  { value: "worktree", label: "New worktree", description: "A fresh branch in its own worktree", icon: <GitFork /> },
];

export function GitModeChip({ gitMode, onChange }: { gitMode: GitMode; onChange: (mode: GitMode) => void }) {
  const current = GIT_MODES.find((mode) => mode.value === gitMode) ?? GIT_MODES[0]!;
  return (
    <Chip
      icon={current.icon}
      label={current.label}
      menu={
        <DropdownMenuRadioGroup onValueChange={(value) => onChange(value as GitMode)} value={gitMode}>
          {GIT_MODES.map((mode) => (
            <DropdownMenuRadioItem key={mode.value} value={mode.value}>
              <span className="flex flex-col">
                <span>{mode.label}</span>
                <span className="text-[11px] text-muted-foreground">{mode.description}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      }
      testId="git-mode"
    />
  );
}

type SelectOption = Extract<ConfigOption, { type: "select" }>;
type BooleanOption = Extract<ConfigOption, { type: "boolean" }>;

export const APPROVAL_MODES: { value: ApprovalMode; label: string; description: string }[] = [
  { value: "ask", label: "Ask", description: "Every permission request waits for you" },
  { value: "approve-for-me", label: "Approve for me", description: "Requests are allowed once, automatically" },
];

/**
 * Codex's `Approve for me` chip. Two things live behind it: the agent's
 * own approval preset when it exposes one (Codex's `mode` config option:
 * ask / approve for me / full access — what the agent asks about), and
 * what Hardcore does with the requests that do arrive (ask, or allow once
 * automatically). The label is the agent's preset when there is one.
 */
export function ApprovalChip({
  mode,
  onChange,
  preset,
  onPresetChange,
}: {
  mode: ApprovalMode;
  onChange: (mode: ApprovalMode) => void;
  preset?: SelectOption | null;
  onPresetChange?: (configId: string, value: string) => void;
}) {
  const current = APPROVAL_MODES.find((candidate) => candidate.value === mode) ?? APPROVAL_MODES[0]!;
  const presetName = preset
    ? (preset.options.find((option) => option.value === preset.currentValue)?.name ?? preset.currentValue)
    : null;
  return (
    <Chip
      icon={<ShieldCheck />}
      label={presetName ?? current.label}
      menu={
        <>
          {preset && onPresetChange ? (
            <>
              <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{preset.name}</DropdownMenuLabel>
              <OptionGroup onChange={(value) => onPresetChange(preset.id, value)} option={preset} />
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">When it asks</DropdownMenuLabel>
            </>
          ) : null}
          <DropdownMenuRadioGroup onValueChange={(value) => onChange(value as ApprovalMode)} value={mode}>
            {APPROVAL_MODES.map((candidate) => (
              <DropdownMenuRadioItem key={candidate.value} value={candidate.value}>
                <span className="flex flex-col">
                  <span>{candidate.label}</span>
                  <span className="text-[11px] text-muted-foreground">{candidate.description}</span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </>
      }
      testId="approval"
      title={preset?.description ?? "What Hardcore does with the agent's permission requests"}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Live-session chips                                                          */
/* -------------------------------------------------------------------------- */

export function ModeChip({
  modes,
  currentModeId,
  onChange,
}: {
  modes: SessionMode[];
  currentModeId: string | null;
  onChange: (modeId: string) => void;
}) {
  const current = modes.find((mode) => mode.id === currentModeId) ?? null;
  return (
    <Chip
      icon={<Sparkles />}
      label={current?.name ?? "Mode"}
      menu={
        <DropdownMenuRadioGroup onValueChange={onChange} value={currentModeId ?? ""}>
          {modes.map((mode) => (
            <DropdownMenuRadioItem key={mode.id} value={mode.id}>
              <span className="flex flex-col">
                <span>{mode.name}</span>
                {mode.description ? (
                  <span className="text-[11px] text-muted-foreground">{mode.description}</span>
                ) : null}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      }
      testId="mode"
      title="Session mode"
    />
  );
}

/**
 * Codex's model chip: `GPT-6 Astra · High`. The `model` option and the
 * `thought_level` option share one menu, in two groups.
 */
export function ModelChip({
  model,
  effort,
  onChange,
}: {
  model: SelectOption;
  effort: SelectOption | null;
  onChange: (configId: string, value: string) => void;
}) {
  const modelName = model.options.find((option) => option.value === model.currentValue)?.name ?? model.currentValue;
  const effortName = effort
    ? (effort.options.find((option) => option.value === effort.currentValue)?.name ?? effort.currentValue)
    : null;
  return (
    <Chip
      icon={<Sparkles />}
      label={effortName ? `${modelName} · ${effortName}` : modelName}
      menu={
        <>
          <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{model.name}</DropdownMenuLabel>
          <OptionGroup onChange={(value) => onChange(model.id, value)} option={model} />
          {effort ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{effort.name}</DropdownMenuLabel>
              <OptionGroup onChange={(value) => onChange(effort.id, value)} option={effort} />
            </>
          ) : null}
        </>
      }
      testId="model"
      title={model.description ?? undefined}
    />
  );
}

/** Any other select option the agent exposes (Codex's collaboration mode, say). */
export function ConfigOptionChip({
  option,
  onChange,
}: {
  option: SelectOption;
  onChange: (configId: string, value: string) => void;
}) {
  const currentName = option.options.find((candidate) => candidate.value === option.currentValue)?.name ?? option.currentValue;
  return (
    <Chip
      icon={<Sparkles />}
      label={currentName}
      menu={
        <>
          <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{option.name}</DropdownMenuLabel>
          <OptionGroup onChange={(value) => onChange(option.id, value)} option={option} />
        </>
      }
      testId={`config-${option.id}`}
      title={option.description ?? option.name}
    />
  );
}

/**
 * The rest of the agent's config options under one chip, a group each —
 * Codex's collaboration mode and web search, say. The composer stays at
 * Codex's width: context, approval, model, and this.
 */
export function OptionsChip({
  selects,
  booleans,
  onSelect,
  onToggle,
}: {
  selects: SelectOption[];
  booleans: BooleanOption[];
  onSelect: (configId: string, value: string) => void;
  onToggle: (configId: string, value: boolean) => void;
}) {
  if (selects.length === 0 && booleans.length === 0) {
    return null;
  }
  const changed = selects.filter((option) => option.currentValue !== option.options[0]?.value).length + booleans.filter((option) => option.currentValue).length;
  return (
    <Chip
      icon={<SlidersHorizontal />}
      label={changed > 0 ? `${changed}` : ""}
      menu={
        <>
          {selects.map((option, index) => (
            <div key={option.id}>
              {index > 0 ? <DropdownMenuSeparator /> : null}
              <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{option.name}</DropdownMenuLabel>
              <OptionGroup onChange={(value) => onSelect(option.id, value)} option={option} />
            </div>
          ))}
          {booleans.length > 0 && selects.length > 0 ? <DropdownMenuSeparator /> : null}
          {booleans.map((option) => (
            <DropdownMenuItem key={option.id} onSelect={(event) => { event.preventDefault(); onToggle(option.id, !option.currentValue); }}>
              <span className="flex size-4 items-center justify-center">{option.currentValue ? <Check className="size-3.5" /> : null}</span>
              <span className="flex min-w-0 flex-col">
                <span>{option.name}</span>
                {option.description ? <span className="text-[11px] text-muted-foreground">{option.description}</span> : null}
              </span>
            </DropdownMenuItem>
          ))}
        </>
      }
      testId="options"
      title="More options from the agent"
    />
  );
}

export function BooleanOptionChip({
  option,
  onChange,
}: {
  option: BooleanOption;
  onChange: (configId: string, value: boolean) => void;
}) {
  return (
    <button
      aria-pressed={option.currentValue}
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2 text-[12px] leading-none transition-colors hover:bg-accent",
        option.currentValue ? "text-foreground" : "text-muted-foreground",
      )}
      data-chip={`config-${option.id}`}
      onClick={() => onChange(option.id, !option.currentValue)}
      title={option.description ?? undefined}
      type="button"
    >
      {option.currentValue ? <Check className="size-3.5" /> : null}
      {option.name}
    </button>
  );
}

function OptionGroup({ option, onChange }: { option: SelectOption; onChange: (value: string) => void }) {
  const groups = new Map<string | null, SelectOption["options"]>();
  for (const candidate of option.options) {
    const list = groups.get(candidate.group) ?? [];
    list.push(candidate);
    groups.set(candidate.group, list);
  }
  return (
    <DropdownMenuRadioGroup onValueChange={onChange} value={option.currentValue}>
      {[...groups.entries()].map(([group, options]) => (
        <div key={group ?? ""}>
          {group ? (
            <DropdownMenuLabel className="pt-2 text-[11px] font-normal text-muted-foreground">{group}</DropdownMenuLabel>
          ) : null}
          {options.map((candidate) => (
            <DropdownMenuRadioItem key={candidate.value} value={candidate.value}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{candidate.name}</span>
                {candidate.description ? (
                  <span className="line-clamp-2 text-[11px] text-muted-foreground">{candidate.description}</span>
                ) : null}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </div>
      ))}
    </DropdownMenuRadioGroup>
  );
}
