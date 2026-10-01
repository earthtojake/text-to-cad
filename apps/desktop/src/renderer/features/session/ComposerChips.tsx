import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useId, useMemo, useState } from "react";
import {
  Check,
  Folder,
  Gauge,
  GitBranch,
  GitFork,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { cn } from "cn";
import { toast } from "sonner";

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
import { useOpenFolderOrToast } from "@renderer/hooks/use-open-folder";
import { agentIcon } from "@renderer/lib/agent-icons";
import { GIT_MODE_LABELS, gitModeAvailability, localGitMode } from "@renderer/lib/git-mode";
import { recentProjects } from "@renderer/lib/projects";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { currentName, isFullAccessMode, type SelectOption } from "@shared/acp/options";
import type { SessionMode } from "@shared/acp/types";
import type { ProjectGitInfo } from "@shared/ipc/git";
import type { GitMode, Project } from "@shared/types";

/**
 * The composer's context strip (plan §2, §6). Every chip is the same shape:
 * an icon and a short label.
 *
 * No chevron. Six of them in two rows is six glyphs saying the same thing
 * about six controls that are visibly the same control, and the row is
 * narrow enough that the space they cost is a chip's label truncated. A
 * chevron earns its place where nothing else says a thing opens; here the
 * hover, the icon and the row all do.
 *
 * A new session shows Project / Git mode in a strip above the composer and
 * `+` / Mode in the row under it; a live session shows `+` and the mode on
 * the left of that row, the model, the effort and the context ring on the
 * right. The two screens draw the **same** mode, model and effort chips: on
 * the new-session screen they come from the agent's cached snapshot and say
 * what the session will be created as, and in a live session they are that
 * session's own. What a session cannot change — its project — is the
 * sidebar's.
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
  disabledReason,
  hintSide = "bottom",
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
  /**
   * Why the chip cannot be used now. It stays focusable and in the accessibility tree
   * (`aria-disabled`, never `disabled` or `inert`) with this as its description, and a click says
   * it rather than opening the menu. No native `title`: the reason is the description.
   */
  disabledReason?: string;
  /**
   * Which way the hint opens: away from the box. The row's chips sit under it and open below; the
   * strip's sit over it and open above, off the sentence. The row's right end (model, effort) opens
   * to the left: in a live session the row is 16px off the window's edge, a hint below it flips to
   * the top, and above those chips is send.
   */
  hintSide?: "top" | "bottom" | "left";
}) {
  const reasonId = useId();
  // ONE button whether or not the chip can be used, so a keyboard user focused on it while the agent
  // reconnects keeps their place when it comes back. Unavailable, it refuses activation before the
  // menu's own pointer and key handlers see it (they skip a default-prevented event) and says why.
  // Enter and Space say it here: preventing their default is what stops the button's own click,
  // and the click is where a pointer hears the reason.
  const refuse = (event: React.SyntheticEvent, say = false) => {
    if (!disabledReason) return;
    event.preventDefault();
    if (say) toast.info(disabledReason);
  };
  // The menu is controlled so that one open when the chip becomes unavailable closes with it: its
  // items would otherwise still run against an agent that is reconnecting.
  const [open, setOpen] = useState(false);
  const menuOpen = open && !disabledReason;
  // The chip's hint is the kit's `TooltipHint`, never a native `title`; it stands aside while the
  // menu is open (`aria-expanded`), and while the chip is unavailable its reason is the description.
  const body = (
    // `disabled`, not a missing `content`: without content the hint renders a different tree, and
    // the button would be remounted — focus lost — when the chip comes back.
    <TooltipHint content={title} disabled={Boolean(disabledReason)} side={hintSide}>
      <button
        aria-describedby={disabledReason ? reasonId : undefined}
        aria-disabled={disabledReason ? "true" : undefined}
        className={cn(
          "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-1.5 text-[12px] leading-none text-muted-foreground transition-colors",
          disabledReason
            ? "cursor-not-allowed opacity-50"
            : menu
              ? "hover:bg-accent hover:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground"
              : "cursor-default",
          className,
        )}
        data-chip={testId}
        onClick={(event) => {
          if (!disabledReason) return;
          event.preventDefault();
          toast.info(disabledReason);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") refuse(event, true);
          else if (event.key === "ArrowDown" || event.key === "ArrowUp") refuse(event);
        }}
        onPointerDown={refuse}
        style={{ maxWidth }}
        type="button"
      >
        <span className="[&>svg]:size-3.5">{icon}</span>
        {label ? <span className="truncate text-foreground/90">{label}</span> : null}
        {detail ? <span className="truncate">{detail}</span> : null}
      </button>
    </TooltipHint>
  );
  const reason = disabledReason ? <span className="sr-only" id={reasonId}>{disabledReason}</span> : null;
  if (!menu) {
    return (
      <>
        {body}
        {reason}
      </>
    );
  }
  return (
    <DropdownMenu onOpenChange={setOpen} open={menuOpen}>
      <DropdownMenuTrigger asChild>{body}</DropdownMenuTrigger>
      {reason}
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
        {...openOnChecked}
      >
        {menu}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * A menu of choices opens on the one chosen, not on the first row: Enter on the mode chip then
 * says "Plan, checked" rather than "Ask", and the arrows start from there. DropdownMenu's types
 * leave out `onOpenAutoFocus`, but it hands the prop to the Menu content underneath, which runs
 * it before its own entry focus (tests/unit/renderer/session-chips.test.tsx holds it to that).
 */
const openOnChecked = {
  onOpenAutoFocus: (event: Event) => {
    const content = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
    const checked = content?.querySelector<HTMLElement>("[role=menuitemradio][aria-checked=true]");
    if (!checked) return;
    event.preventDefault();
    checked.focus();
  },
} as Record<string, unknown>;

/* -------------------------------------------------------------------------- */
/* New-session chips                                                           */
/* -------------------------------------------------------------------------- */

/**
 * The draft's directory: recently active session directories first, followed
 * by the folder chooser. Choosing a folder opens an in-memory draft; it does
 * not create a saved project or a sidebar group.
 */
export function ProjectChip({ project, onChange }: { project: Project | null; onChange: (id: string) => void }) {
  const projects = useProjects((state) => state.projects);
  const sessions = useSessions((state) => state.sessions);
  const openFolder = useOpenFolderOrToast();
  // The folder this draft is in is listed whether or not a session has run there yet, first when
  // it has none: a menu that leaves out its own check mark reads as a different folder.
  const recent = useMemo(() => {
    const activeDirectories = new Set(sessions.filter(session => !session.archived).map(session => session.projectId));
    const listed = recentProjects(projects.filter(candidate => activeDirectories.has(candidate.id)), sessions);
    return project && !listed.some(candidate => candidate.id === project.id) ? [project, ...listed] : listed;
  }, [project, projects, sessions]);
  return (
    <Chip
      icon={<Folder />}
      label={project?.name ?? "Choose folder"}
      menu={
        <>
          {recent.length > 0 ? (
            <DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase">Recent</DropdownMenuLabel>
          ) : null}
          {recent.map((candidate) => (
            // The name is what a person picks by; the path is a hover away
            // rather than a second line under every row.
            <TooltipHint content={candidate.path} key={candidate.id} side="right">
              <DropdownMenuItem onSelect={() => onChange(candidate.id)}>
                <span className="flex size-4 shrink-0 items-center justify-center">
                  {candidate.id === project?.id ? <Check className="size-3.5" /> : null}
                </span>
                <span className="truncate">{candidate.name}</span>
              </DropdownMenuItem>
            </TooltipHint>
          ))}
          {recent.length > 0 ? <DropdownMenuSeparator /> : null}
          <DropdownMenuItem
            onSelect={() =>
              void openFolder().then((added) => {
                if (added) {
                  onChange(added.id);
                }
              })
            }
          >
            Open folder…
          </DropdownMenuItem>
        </>
      }
      hintSide="top"
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
                  ? `The project folder; ${info?.problem ?? "it is not a git repository"}`
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
      hintSide="top"
      testId="git-mode"
      title={isWorktree ? "A fresh branch in a worktree of its own" : "The project's own folder"}
    />
  );
}

/**
 * The mode — **the** permission control, and the only one (README,
 * "Permissions"). What the agent asks about is what the agent's own mode
 * says, so the app has no approval setting of its own over the top of it:
 * one chip, on the new-session screen and in a live thread, with the names
 * the agent gave and nothing added to them.
 *
 * Whichever shape the agent sends its modes in reaches this component the
 * same way (`modeChoice` in `shared/acp/options`); the caller owns the
 * setter, which is `session/set_mode` or a `mode` config option.
 *
 * No sublabels — the agent's `description` is a paragraph under every row —
 * with one exception: the mode that asks about nothing gets a muted note
 * saying so, because it is the one choice that removes every checkpoint.
 */
export function ModeChip({
  modes,
  currentModeId,
  onChange,
  disabledReason,
}: {
  modes: SessionMode[];
  currentModeId: string | null;
  onChange: (modeId: string) => void;
  disabledReason?: string;
}) {
  const current = modes.find((mode) => mode.id === currentModeId) ?? null;
  return (
    <Chip
      disabledReason={disabledReason}
      icon={<ShieldCheck />}
      label={current?.name ?? "Mode"}
      maxWidth={160}
      menu={
        <DropdownMenuRadioGroup onValueChange={onChange} value={currentModeId ?? ""}>
          {modes.map((mode) => (
            <DropdownMenuRadioItem key={mode.id} value={mode.id}>
              {isFullAccessMode(mode) ? (
                <span className="flex flex-col" data-mode-full-access>
                  <span className="truncate">{mode.name}</span>
                  <span className="text-[11px] text-muted-foreground">Never asks</span>
                </span>
              ) : (
                <span className="truncate">{mode.name}</span>
              )}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      }
      testId="mode"
      title={current?.description ?? "What this agent asks you about"}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Live-session chips                                                          */
/* -------------------------------------------------------------------------- */

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
  disabledReason,
}: {
  providers: ModelProvider[];
  /** Whose model is showing. */
  agentId: string | null;
  onChange: (agentId: string, value: string) => void;
  fast?: FastSwitch | null;
  onFastChange?: (configId: string, value: string | boolean) => void;
  disabledReason?: string;
}) {
  const current = providers.find((provider) => provider.agentId === agentId) ?? providers[0] ?? null;
  if (!current) {
    return null;
  }
  const many = providers.length > 1;
  return (
    <Chip
      disabledReason={disabledReason}
      icon={<ProviderGlyph icon={current.icon} />}
      label={currentName(current.model)}
      hintSide="left"
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
                <DropdownMenuLabel className="flex items-center gap-1.5 text-[11px] text-muted-foreground uppercase">
                  {many ? (
                    <>
                      <ProviderGlyph icon={provider.icon} size="size-3" />
                      {provider.agentName}
                    </>
                  ) : (
                    provider.model.name
                  )}
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
  disabledReason,
}: {
  effort: SelectOption;
  onChange: (configId: string, value: string) => void;
  disabledReason?: string;
}) {
  return (
    <Chip
      disabledReason={disabledReason}
      icon={<Gauge />}
      label={currentName(effort)}
      hintSide="left"
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
function ProviderGlyph({ icon, size = "size-3.5" }: { icon?: string | null; size?: "size-3" | "size-3.5" }) {
  const markup = agentIcon(icon);
  if (!markup) {
    return <Sparkles className={size} />;
  }
  return (
    // Committed assets, checked by the script that downloads them — not user
    // input (see `features/settings/AgentMark.tsx`).
    <span aria-hidden className={cn("block", size)} dangerouslySetInnerHTML={{ __html: markup }} />
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
