import {
  Check,
  ChevronDown,
  Folder,
  Gauge,
  GitBranch,
  GitFork,
  ShieldCheck,
  Sparkles,
  Zap,
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
import { useProjects } from "@renderer/state/projects";
import { currentName, type SelectOption } from "@shared/acp/options";
import type { ApprovalMode, SessionMode } from "@shared/acp/types";
import type { ProjectGitInfo } from "@shared/ipc/git";
import type { GitMode, Project } from "@shared/types";

/**
 * The composer's context strip (plan §2, §6). Every chip is the same
 * shape: an icon, a short label, a chevron when it opens a menu.
 *
 * A new session shows Project / Git mode / Model / Effort in a strip above
 * the composer and Approval in it; a live session shows Approval and the
 * agent's modes on the left, the model and the effort on the right. The two
 * screens draw the **same** model and effort chips: on the new-session screen
 * the model menu lists every installed provider's models and picking one
 * picks the agent, and in a live session it is scoped to that session's
 * agent. What a session cannot change — its project — is the sidebar's.
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
      {/*
        Capped at what Radix measured is actually there and scrolled inside,
        rather than at a fraction of the window: a model menu with a group
        per installed provider is taller than the gap above the composer,
        and an uncapped one flips below the chip and off the bottom edge.
      */}
      <DropdownMenuContent
        align="start"
        className="max-h-[var(--radix-dropdown-menu-content-available-height)] w-64 overflow-y-auto"
        collisionPadding={12}
        side="top"
      >
        {menu}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* -------------------------------------------------------------------------- */
/* New-session chips                                                           */
/* -------------------------------------------------------------------------- */

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

/** One installed provider's models, as the model menu groups them. */
export type ModelProvider = {
  agentId: string;
  agentName: string;
  /** The agent's registry `icon`; a sparkle stands in when it has none. */
  icon?: string | null;
  model: SelectOption;
};

/** The `fast` switch, whichever way the agent sends it (`shared/acp/options`). */
export type FastSwitch = { id: string; name: string; on: boolean; value: string | boolean };

/**
 * The model, with the mark of whoever runs it: `◇ GPT-6 Astra`. The icon is
 * the agent's own (`lib/agent-icons.ts`) — the model belongs to a provider,
 * and a row of identical sparkles says nothing about which one.
 *
 * One chip, two situations. In a live session `providers` is that session's
 * agent alone and picking a model sets a config option on it. On the
 * new-session screen it is every **installed** agent that has answered, a
 * group each, and picking a model picks the agent the session will run —
 * which is why the agent has no chip of its own any more. An agent that is
 * not installed, or whose probe has not answered, contributes no group: a
 * model that cannot be run is not offered.
 *
 * The agent's `fast` switch, when it has one, is the last row of this menu
 * rather than a chip: it is a property of the model, not a second decision.
 */
export function ModelChip({
  providers,
  agentId,
  onChange,
  fast,
  onFastChange,
}: {
  providers: ModelProvider[];
  /** Whose model is showing. */
  agentId: string | null;
  onChange: (agentId: string, value: string) => void;
  fast?: FastSwitch | null;
  onFastChange?: (configId: string, value: string | boolean) => void;
}) {
  const current = providers.find((provider) => provider.agentId === agentId) ?? providers[0] ?? null;
  if (!current) {
    return null;
  }
  const many = providers.length > 1;
  return (
    <Chip
      icon={<ProviderGlyph icon={current.icon} />}
      label={currentName(current.model)}
      maxWidth={190}
      menu={
        <>
          <DropdownMenuRadioGroup
            onValueChange={(value) => {
              const [provider, model] = splitModelValue(value);
              if (provider && model) {
                onChange(provider, model);
              }
            }}
            value={modelValue(current.agentId, current.model.currentValue)}
          >
            {providers.map((provider, index) => (
              <div key={provider.agentId}>
                {index > 0 ? <DropdownMenuSeparator /> : null}
                <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">
                  {many ? provider.agentName : provider.model.name}
                </DropdownMenuLabel>
                <OptionItems
                  option={provider.model}
                  valueFor={(value) => modelValue(provider.agentId, value)}
                />
              </div>
            ))}
          </DropdownMenuRadioGroup>
          {fast && onFastChange ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault();
                  onFastChange(fast.id, fast.value);
                }}
              >
                <span className="flex size-4 items-center justify-center">
                  {fast.on ? <Check className="size-3.5" /> : <Zap className="size-3.5 opacity-50" />}
                </span>
                <span className="truncate">{fast.name}</span>
              </DropdownMenuItem>
            </>
          ) : null}
        </>
      }
      testId="model"
      title={current.model.description ?? current.model.name}
    />
  );
}

const MODEL_SEPARATOR = "\u0000";

/** Provider and model in one radio value, so one group can span every provider. */
function modelValue(agentId: string, value: string): string {
  return `${agentId}${MODEL_SEPARATOR}${value}`;
}

function splitModelValue(value: string): [string | null, string | null] {
  const at = value.indexOf(MODEL_SEPARATOR);
  return at < 0 ? [null, null] : [value.slice(0, at), value.slice(at + 1)];
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
  return (
    <Chip
      icon={<Gauge />}
      label={currentName(effort)}
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

function OptionGroup({ option, onChange }: { option: SelectOption; onChange: (value: string) => void }) {
  return (
    <DropdownMenuRadioGroup onValueChange={onChange} value={option.currentValue}>
      <OptionItems option={option} />
    </DropdownMenuRadioGroup>
  );
}

/**
 * One select's items, inside whichever radio group the caller opened. The
 * agent's own grouping (a model family) is kept as a sub-label; its
 * per-option `description` is not drawn — a menu of models is a list of
 * names, and a paragraph under each one is a wall to read past rather than a
 * choice to make.
 */
function OptionItems({
  option,
  valueFor = (value: string) => value,
}: {
  option: SelectOption;
  /** The radio value an option's own value goes by (the model menu spans providers). */
  valueFor?: (value: string) => string;
}) {
  const groups = new Map<string | null, SelectOption["options"]>();
  for (const candidate of option.options) {
    const list = groups.get(candidate.group) ?? [];
    list.push(candidate);
    groups.set(candidate.group, list);
  }
  return (
    <>
      {[...groups.entries()].map(([group, options]) => (
        <div key={group ?? ""}>
          {group ? (
            <DropdownMenuLabel className="pt-2 text-[11px] font-normal text-muted-foreground">{group}</DropdownMenuLabel>
          ) : null}
          {options.map((candidate) => (
            <DropdownMenuRadioItem key={candidate.value} value={valueFor(candidate.value)}>
              <span className="truncate">{candidate.name}</span>
            </DropdownMenuRadioItem>
          ))}
        </div>
      ))}
    </>
  );
}
