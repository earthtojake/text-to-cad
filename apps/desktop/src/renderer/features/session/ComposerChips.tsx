import {
  Bot,
  Check,
  ChevronDown,
  Folder,
  Gauge,
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
import { agentIcon } from "@renderer/lib/agent-icons";
import { GIT_MODE_LABELS, gitModeAvailability, localGitMode } from "@renderer/lib/git-mode";
import { useAgents, useInstalledAgents } from "@renderer/state/agents";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";
import type { ApprovalMode, ConfigOption, SessionMode } from "@shared/acp/types";
import type { AgentStatus } from "@shared/agents";
import type { ProjectGitInfo } from "@shared/ipc/git";
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

/**
 * Where the session's working directory comes from. Two choices (plan §9):
 * **Local**, the project's own folder — its checkout, or just the folder when
 * it is not a repository — and **New worktree**, a branch of its own, which a
 * project that is not a repository or has no commits cannot offer and which
 * says why instead of failing later.
 */
export function GitModeChip({
  gitMode,
  info,
  onChange,
}: {
  gitMode: GitMode;
  info: ProjectGitInfo | null;
  onChange: (mode: GitMode) => void;
}) {
  const local = localGitMode(info);
  const worktree = gitModeAvailability("worktree", info);
  const isWorktree = gitMode === "worktree";
  return (
    <Chip
      icon={isWorktree ? <GitFork /> : local === "none" ? <Folder /> : <GitBranch />}
      label={GIT_MODE_LABELS[gitMode]}
      menu={
        <DropdownMenuRadioGroup
          onValueChange={(value) => onChange(value === "worktree" ? "worktree" : local)}
          value={isWorktree ? "worktree" : "local"}
        >
          <DropdownMenuRadioItem value="local">
            <span className="flex flex-col">
              <span>Local</span>
              <span className="text-[11px] text-muted-foreground">
                {local === "none"
                  ? "The project folder; it is not a git repository"
                  : `The project's checkout${info?.branch ? `, on ${info.branch}` : ""}`}
              </span>
            </span>
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem disabled={!worktree.available} value="worktree">
            <span className="flex flex-col">
              <span>New worktree</span>
              <span className="text-[11px] text-muted-foreground">
                {worktree.reason ?? "A fresh branch in a worktree of its own"}
              </span>
            </span>
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      }
      testId="git-mode"
      title={isWorktree ? "A fresh branch in a worktree of its own" : "The project's own folder"}
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
 * The model, with the mark of whoever runs it: `◇ GPT-6 Astra`. The icon is
 * the agent's own (`lib/agent-icons.ts`) — the model belongs to a provider,
 * and a row of identical sparkles says nothing about which one.
 */
export function ModelChip({
  model,
  icon,
  onChange,
}: {
  model: SelectOption;
  /** The agent's registry `icon`; a sparkle stands in when it has none. */
  icon?: string | null;
  onChange: (configId: string, value: string) => void;
}) {
  const modelName = model.options.find((option) => option.value === model.currentValue)?.name ?? model.currentValue;
  return (
    <Chip
      icon={<ProviderGlyph icon={icon} />}
      label={modelName}
      maxWidth={170}
      menu={
        <>
          <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{model.name}</DropdownMenuLabel>
          <OptionGroup onChange={(value) => onChange(model.id, value)} option={model} />
        </>
      }
      testId="model"
      title={model.description ?? model.name}
    />
  );
}

/**
 * How hard the model is asked to think, when the agent exposes it — Codex's
 * `reasoning_effort`, Claude's `effort`. Its own dropdown beside the model's
 * rather than a second group inside it: they are two decisions, and the one
 * that changes between prompts is this one.
 */
export function EffortChip({
  effort,
  onChange,
}: {
  effort: SelectOption;
  onChange: (configId: string, value: string) => void;
}) {
  const current = effort.options.find((option) => option.value === effort.currentValue)?.name ?? effort.currentValue;
  return (
    <Chip
      icon={<Gauge />}
      label={current}
      maxWidth={130}
      menu={
        <>
          <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">{effort.name}</DropdownMenuLabel>
          <OptionGroup onChange={(value) => onChange(effort.id, value)} option={effort} />
        </>
      }
      testId="effort"
      title={effort.description ?? effort.name}
    />
  );
}

/** The agent's mark at chip size, in `currentColor`, or a sparkle. */
function ProviderGlyph({ icon }: { icon?: string | null }) {
  const markup = agentIcon(icon);
  if (!markup) {
    return <Sparkles />;
  }
  return (
    // Committed assets, checked by the script that downloads them — not user
    // input (see `features/settings/AgentMark.tsx`).
    <span aria-hidden className="block size-3.5" dangerouslySetInnerHTML={{ __html: markup }} />
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
