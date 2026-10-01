/**
 * Agent settings, in a right-hand drawer (Emdash's shape, plan §2).
 *
 * Everything about one agent that the app can answer without starting it: where
 * its binary is, whether the user is signed in, what it is given in a text-to-cad
 * session, and what the app will type when it launches it. The two
 * long-running actions — install and sign in — are pty jobs in main whose
 * output streams into the log under the button that started them, because an
 * installer that prints nothing for ninety seconds is indistinguishable from
 * one that has hung.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, ExternalLink, Terminal } from "lucide-react";
import { Spinner } from "@renderer/components/ui/spinner";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@renderer/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@renderer/components/ui/sheet";
import { Textarea } from "@renderer/components/ui/textarea";
import { useReturnFocus } from "@renderer/hooks/use-return-focus";
import { AgentMark } from "@renderer/features/settings/AgentMark";
import { InlineCode } from "@renderer/features/settings/inline-code";
import { StatusLabel, type Tone } from "@renderer/features/settings/StatusDot";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { useDraft } from "@renderer/features/settings/SettingCard";
import { useSkills } from "@renderer/features/settings/use-skills";
import { useAgents } from "@renderer/state/agents";
import type { AgentJobOutput, AgentStatus, AuthState, Platform } from "@shared/agents";

const AUTH_TONE: Record<AuthState, Tone> = {
  authenticated: "ok",
  unauthenticated: "warn",
  unknown: "idle",
  "not-required": "ok",
};

// "unknown" says only what detection knows — whether the CLI is here — the
// same words as the agent rows (`features/session/agent-setup.tsx`).
const AUTH_LABEL: Record<Exclude<AuthState, "unknown">, string> = {
  authenticated: "Signed in",
  unauthenticated: "Not signed in",
  "not-required": "No sign-in needed",
};

export function authLabel(agent: Pick<AgentStatus, "auth" | "installed" | "probing">): string {
  // The last launch's row: its login is being asked again, so it says nothing yet.
  if (agent.probing && agent.auth === "unauthenticated") {
    return "Checking…";
  }
  if (agent.auth === "unknown") {
    return agent.installed ? "Installed" : "Not installed";
  }
  return AUTH_LABEL[agent.auth];
}

/** What `capabilities` means in a sentence, for the "Supports:" line. */
function supports(agent: AgentStatus): string {
  const list = [
    "Prompts",
    agent.capabilities.loadSession ? "Sessions" : null,
    agent.capabilities.terminals ? "Terminals" : null,
    agent.capabilities.modes ? "Modes" : null,
    agent.capabilities.configOptions ? "Models" : null,
    agent.capabilities.subagents ? "Subagents" : null,
  ].filter(Boolean);
  return list.join(", ");
}

export function AgentDrawer({
  agent,
  open,
  platform,
  onOpenChange,
}: {
  /**
   * The agent to show. Kept by the page after the drawer closes — a drawer
   * whose contents vanished the moment it was dismissed would spend its exit
   * animation as an empty white panel.
   */
  agent: AgentStatus | null;
  open: boolean;
  platform: Platform;
  onOpenChange: (open: boolean) => void;
}) {
  // Opened from a row, not a Sheet trigger: Escape hands focus back to that row by hand.
  const returnFocus = useReturnFocus();
  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent
        className="w-full gap-0 overflow-y-auto p-0 sm:max-w-[520px]"
        side="right"
        {...returnFocus}
      >
        {/* Keyed by agent: every field inside is per-agent state, and the
            cheapest correct reset is a new component. */}
        {agent ? <DrawerBody agent={agent} key={agent.id} platform={platform} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function DrawerBody({ agent, platform }: { agent: AgentStatus; platform: Platform }) {
  return (
    <>
      <SheetHeader className="gap-3 border-b p-5">
        <div className="flex items-start gap-3">
          <AgentMark icon={agent.icon} id={agent.id} name={agent.name} size="drawer" />
          <div className="min-w-0 flex-1">
            <SheetTitle className="text-base">{agent.name}</SheetTitle>
            <SheetDescription className="mt-0.5 text-xs"><InlineCode text={agent.description} /></SheetDescription>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            <span className="text-foreground">Supports:</span> {supports(agent)}
          </p>
          <Button
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={() =>
              void window.textToCad.shell.openExternal({ url: agent.websiteUrl })
            }
            size="sm"
            variant="ghost"
          >
            View website
            <ExternalLink className="size-3" />
          </Button>
        </div>
      </SheetHeader>

      <div className="flex flex-col divide-y">
        <InstallationSection agent={agent} platform={platform} />
        <AuthenticationSection agent={agent} />
        <SkillsSection agent={agent} />
        <McpSection agent={agent} />
        <AdvancedSection agent={agent} />
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-medium">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function InstallationSection({ agent, platform }: { agent: AgentStatus; platform: Platform }) {
  const methods = agent.install[platform];
  const [index, setIndex] = useState(0);
  const install = useAgents((state) => state.install);
  const { jobId, output, running, failure, start } = useJob(agent.id, "install", agent.installed);

  if (agent.installed) {
    return (
      <Section title="Installation">
        <div className="flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2.5 text-xs">
          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />
          <p className="min-w-0 break-all text-muted-foreground" data-selectable>
            Found at <span className="text-foreground">{agent.binaryPath}</span>
            {agent.version ? ` · v${agent.version}` : ""}
            {agent.adapter ? ` · adapter ${agent.adapter.version}` : ""}
          </p>
        </div>
        {jobId ? <JobLog failure={failure} output={output} /> : null}
      </Section>
    );
  }

  // The last launch's "not installed" is provisional: nothing to install until it is confirmed.
  if (agent.probing) {
    return (
      <Section title="Installation">
        <p className="text-xs text-muted-foreground">Checking…</p>
      </Section>
    );
  }

  if (methods.length === 0) {
    return (
      <Section title="Installation">
        <p className="text-xs text-muted-foreground">
          No install command for {PLATFORM_NAMES[platform]}. Follow the agent's own instructions,
          then press Refresh on the Agents page.
        </p>
        <Button
          className="mt-3 h-8 gap-1.5"
          onClick={() => void window.textToCad.shell.openExternal({ url: agent.docsUrl })}
          size="sm"
          variant="secondary"
        >
          Installation docs
          <ExternalLink className="size-3" />
        </Button>
      </Section>
    );
  }

  return (
    <Section title="Installation">
      <div className="flex items-center gap-2">
        <Select onValueChange={(value) => setIndex(Number(value))} value={String(index)}>
          <SelectTrigger aria-label="Install method" className="flex-1" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {methods.map((method, position) => (
              <SelectItem key={method.label} value={String(position)}>
                {method.label}
                {position === 0 ? " (recommended)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          className="h-8 gap-1.5"
          disabled={running}
          onClick={() => void start(() => install(agent.id, index))}
          size="sm"
        >
          {running ? <Spinner aria-hidden className="size-3.5" /> : null}
          Install
        </Button>
      </div>
      <p className="mt-2 font-mono text-[11px] break-all text-muted-foreground" data-selectable>
        {methods[index]?.command}
      </p>
      {jobId ? <JobLog failure={failure} output={output} /> : null}
    </Section>
  );
}

const PLATFORM_NAMES: Record<Platform, string> = {
  macos: "macOS",
  windows: "Windows",
  linux: "Linux",
};

/* -------------------------------------------------------------------------- */

function AuthenticationSection({ agent }: { agent: AgentStatus }) {
  const login = useAgents((state) => state.login);
  const { jobId, output, running, failure, start } = useJob(agent.id, "login", agent.auth === "authenticated");

  const cliLogin = agent.authMethods.find((method) => method.type === "cli-login");
  const apiKey = agent.authMethods.find((method) => method.type === "api-key");

  const signedIn = agent.auth === "authenticated";

  return (
    <Section
      action={<StatusLabel tone={agent.probing && agent.auth === "unauthenticated" ? "idle" : AUTH_TONE[agent.auth]}>{authLabel(agent)}</StatusLabel>}
      title="Authentication"
    >
      {/* Signed in, the status on the right already says so: what is left is
          one quiet way to redo it. Signed out, the method's own words sit
          beside the primary button. */}
      {cliLogin ? (
        <div className={signedIn ? "flex justify-end" : "flex items-center justify-between gap-3"}>
          {signedIn ? null : <p className="min-w-0 text-xs text-muted-foreground">{cliLogin.label}</p>}
          <Button
            className="h-8 gap-1.5"
            // Signing in runs the agent's own CLI, which has to be installed.
            disabled={running || !agent.installed}
            onClick={() => void start(() => login(agent.id))}
            size="sm"
            variant={signedIn ? "secondary" : "default"}
          >
            {running ? <Spinner aria-hidden className="size-3.5" /> : null}
            {signedIn ? "Sign in again" : "Sign in"}
          </Button>
        </div>
      ) : null}

      {!agent.installed && cliLogin ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Install {agent.name} first — signing in runs its own CLI.
        </p>
      ) : null}

      {/* The API key is the other way in, not a step after signing in: it is
          folded away, and open only when it is the one way there is. */}
      {apiKey ? (
        <details className="group mt-3 text-xs" open={!cliLogin && !signedIn}>
          <summary className="cursor-default text-muted-foreground select-none hover:text-foreground">
            Use an API key instead
          </summary>
          <div className="mt-2 rounded-lg border bg-muted/40 px-3 py-2.5">
            <p className="text-muted-foreground">
              {apiKey.label}: set one of these in the shell text-to-cad launches from, then press
              Refresh.
            </p>
            <p className="mt-1.5 font-mono text-[11px]" data-selectable>
              {apiKey.envVars.join("  ·  ")}
            </p>
          </div>
        </details>
      ) : null}

      {jobId ? <JobLog failure={failure} output={output} /> : null}
    </Section>
  );
}

/* -------------------------------------------------------------------------- */

function SkillsSection({ agent }: { agent: AgentStatus }) {
  const skills = useSkills();
  const count = skills?.skills.length ?? 0;
  const native = agent.skillRoots === "native";

  return (
    <Section
      action={<StatusLabel tone={count > 0 ? "ok" : "idle"}>{count > 0 ? `${count} skills` : "—"}</StatusLabel>}
      title="Skills"
    >
      <p className="text-xs text-muted-foreground">
        <InlineCode
          text={
            count > 0
              ? `Every session in text-to-cad is handed the app's CAD skills and focused workspace integration skills as an extra directory,
             ${
               native
                 ? `which ${agent.name} loads by itself.`
                 : `and, because ${agent.name} does not load one, a line in the first prompt saying where they are. The app's MCP server can read them too.`
             } Nothing is installed into ${agent.name}'s own configuration.`
              : "text-to-cad hands its skills to every session. This build has none composed yet — run `npm run build`."
          }
        />
      </p>
      {skills?.root ? (
        // The whole path when the line has cut it short.
        <TooltipHint content={skills.root} overflowOnly side="top">
          <p className="mt-2 truncate text-[11px] text-muted-foreground">
            <span data-selectable>{skills.root}</span>
          </p>
        </TooltipHint>
      ) : null}
    </Section>
  );
}

/* -------------------------------------------------------------------------- */

function McpSection({ agent }: { agent: AgentStatus }) {
  return (
    <Section title="MCP servers">
      <p className="text-xs text-muted-foreground">
        Every text-to-cad session gets the app&apos;s own server — how an agent opens a file in the
        explorer, attaches a snapshot, or reads a skill — beside whatever {agent.name} is
        configured with itself. That configuration is {agent.name}&apos;s; this app does not touch it.
      </p>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * The launch line, and the user's amendments to it.
 *
 * The command and its arguments are read-only: they come from the registry, are
 * what the adapter was tested with, and an agent that will not start because
 * someone edited its argv is a support question with no answer. Extra arguments
 * and environment variables are additive, which is the part that can be
 * corrected by removing what was added.
 */
function AdvancedSection({ agent }: { agent: AgentStatus }) {
  const settings = useSettingsValue();
  const patch = useSettingsPatch();
  const override = settings.agentOverrides[agent.id];

  // Each field is a draft (`useDraft`): written on blur, and on unmount for an
  // edit the drawer closed on (Esc) before any blur. The two fields save as one
  // record, so a commit reads the other field's draft from `typed`.
  const typed = useRef({ extraArgs: "", env: "" });
  const save = (nextArgs: string, nextEnv: string) => {
    const parsedArgs = nextArgs.split(/\s+/).filter(Boolean);
    const parsedEnv = parseEnv(nextEnv);
    const empty = parsedArgs.length === 0 && Object.keys(parsedEnv).length === 0;
    const overrides = { ...settings.agentOverrides };
    if (empty) {
      delete overrides[agent.id];
    } else {
      overrides[agent.id] = { extraArgs: parsedArgs, env: parsedEnv };
    }
    patch({ agentOverrides: overrides });
  };
  const extraArgs = useDraft((override?.extraArgs ?? []).join(" "), (next) => save(next, typed.current.env));
  // The saved record is the parse of the text, so the text is still the field's
  // when it parses to what the store holds: comments and malformed lines stay.
  const env = useDraft(
    formatEnv(override?.env ?? {}),
    (next) => save(typed.current.extraArgs, next),
    sameEnv,
  );
  useEffect(() => {
    typed.current = { extraArgs: extraArgs.value, env: env.value };
  });
  const dropped = droppedEnvLines(env.value);

  const launchEnv = Object.entries(agent.launch.env);

  return (
    <Section title="Advanced">
      <dl className="space-y-2 rounded-lg border bg-muted/40 px-3 py-2.5 text-[11px]">
        <Field label="Command" value={agent.launch.command} />
        <Field label="Arguments" value={agent.launch.args.join(" ") || "—"} />
        <Field
          label="Environment"
          value={
            launchEnv.length === 0
              ? "inherited from your login shell"
              : launchEnv.map(([key, value]) => `${key}=${value}`).join("  ")
          }
        />
      </dl>

      <label className="mt-4 block text-xs" htmlFor={`${agent.id}-extra-args`}>
        Extra arguments
      </label>
      <Input
        className="mt-1.5 h-8 font-mono text-xs"
        id={`${agent.id}-extra-args`}
        onBlur={extraArgs.onBlur}
        onChange={(event) => extraArgs.onChange(event.target.value)}
        onFocus={extraArgs.onFocus}
        // Neutral: one drawer serves every agent, and a model name in the
        // hint was one agent's flag shown on all the others.
        placeholder="--flag value"
        value={extraArgs.value}
      />

      <label className="mt-3 block text-xs" htmlFor={`${agent.id}-env`}>
        Environment
      </label>
      <Textarea
        className="mt-1.5 min-h-16 font-mono text-xs"
        id={`${agent.id}-env`}
        onBlur={env.onBlur}
        onChange={(event) => env.onChange(event.target.value)}
        onFocus={env.onFocus}
        placeholder={"KEY=value\nANOTHER=value"}
        value={env.value}
      />
      {dropped.length > 0 ? (
        <p className="mt-1.5 text-[11px] text-amber-600 dark:text-amber-500" role="status">
          {dropped.length === 1 ? `Line ${dropped[0]} has` : `Lines ${dropped.slice(0, -1).join(", ")} and ${dropped.at(-1)} have`}{" "}
          no KEY=value and will not be saved.
        </p>
      ) : null}
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        One per line. Merged over the launch environment when text-to-cad starts {agent.name}.
      </p>
    </Section>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-20 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 font-mono break-all" data-selectable>
        {value}
      </dd>
    </div>
  );
}

/** One line of the environment field: blank and `#` lines say nothing; the rest are `KEY=value` or not. */
function envEntry(line: string): { key: string; value: string } | "ignored" | "malformed" {
  const trimmed = line.trim();
  if (trimmed === "" || trimmed.startsWith("#")) {
    return "ignored";
  }
  const split = trimmed.indexOf("=");
  if (split <= 0) {
    return "malformed";
  }
  return { key: trimmed.slice(0, split).trim(), value: trimmed.slice(split + 1).trim() };
}

/** `KEY=value` lines → a record. Blank lines and comments are ignored. */
export function parseEnv(text: string): Record<string, string> {
  const entries: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const entry = envEntry(line);
    if (typeof entry === "object") {
      entries[entry.key] = entry.value;
    }
  }
  return entries;
}

/** The 1-based numbers of the lines `parseEnv` drops without saying so: not blank, not a comment, no `KEY=`. */
export function droppedEnvLines(text: string): number[] {
  return text
    .split("\n")
    .flatMap((line, index) => (envEntry(line) === "malformed" ? [index + 1] : []));
}

/** Whether `draft` is a spelling of the env text `value` (a `formatEnv` result). */
function sameEnv(draft: string, value: string): boolean {
  return formatEnv(parseEnv(draft)) === value;
}

export function formatEnv(env: Record<string, string>): string {
  return Object.entries(env)
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
}

/* -------------------------------------------------------------------------- */

/**
 * One pty job at a time, with its output.
 *
 * The job id comes back from the IPC call and the output arrives on
 * `agents.output` afterwards, so the component has to remember the id to know
 * which stream is its own — two drawers open on two agents share one store.
 * The remembered id dies with the component, though the installer does not: a
 * job of this agent and kind still running in the store is this one's too, so a
 * drawer closed and reopened (or a welcome left for Settings and back) finds
 * the install under way instead of offering to start a second.
 *
 * `done` is whether the step the job is for has been achieved (installed, or
 * signed in): a failure of an earlier run is then history and is not worded.
 */
export function useJob(agentId: string, kind: AgentJobOutput["kind"], done = false) {
  const [startedId, setStartedId] = useState<string | null>(null);
  // This agent and kind's latest job in the store (insertion order): running, it is this
  // one's whoever started it; finished with a non-zero code, it stays to say so on a remount.
  const latestId = useAgents(
    (state) =>
      Object.keys(state.jobs)
        .filter((id) => state.jobs[id]?.agentId === agentId && state.jobs[id]?.kind === kind)
        .at(-1) ?? null,
  );
  const latest = useAgents((state) => (latestId ? state.jobs[latestId] : undefined));
  const remembered = latest && (latest.exitCode === null || latest.exitCode !== 0) ? latestId : null;
  // The job this mount started, once a newer one of this agent and kind is in the store: it is
  // history (a failed run must not return after a later run succeeded), and `remembered` says
  // what the newer one left. Until the started job has reached the store it is the newest.
  const startedIsOld = useAgents(
    (state) => startedId !== null && startedId in state.jobs && startedId !== latestId,
  );
  // A job still running anywhere in the store beats the id this mount remembers.
  const jobId = (latest?.exitCode === null ? latestId : null) ?? (startedIsOld ? null : startedId) ?? remembered;
  const job = useAgents((state) => (jobId ? state.jobs[jobId] : undefined));
  const starting = useRef(false);

  const start = async (run: () => Promise<string>) => {
    if (starting.current) {
      return;
    }
    starting.current = true;
    try {
      setStartedId(await run());
    } finally {
      starting.current = false;
    }
  };

  return {
    jobId,
    output: job?.output ?? "",
    // A job with an exit code has finished, whatever the code was.
    running: jobId !== null && (job?.exitCode ?? null) === null,
    // A finished job's non-zero code, in words; the log above it is the why.
    failure:
      !done && job && job.exitCode !== null && job.exitCode !== 0
        ? `${kind === "install" ? "Install" : "Sign in"} failed (exit ${job.exitCode})`
        : null,
    start,
  };
}

/** The tail of a running job, scrolled to the bottom. */
export function JobLog({ output, failure = null }: { output: string; failure?: string | null }) {
  const ref = useRef<HTMLPreElement>(null);
  const text = useMemo(() => stripAnsi(output).trimEnd(), [output]);

  useEffect(() => {
    const node = ref.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [text]);

  return (
    <>
      {failure ? (
        <p className="mt-3 text-xs text-destructive" role="alert">
          {failure}
        </p>
      ) : null}
      <pre
        className="mt-3 max-h-40 overflow-auto rounded-lg border bg-muted/40 px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
        ref={ref}
      >
        {text === "" ? (
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Terminal className="size-3" />
            Waiting for output…
          </span>
        ) : (
          <code data-selectable>{text}</code>
        )}
      </pre>
    </>
  );
}

/**
 * Installers colour their output and redraw progress bars. This is a log, not a
 * terminal — the escapes would be printed literally — so they come out.
 */
function stripAnsi(text: string): string {
  return (
    text
      // CSI sequences: colour, cursor moves, the redraws a progress bar makes.
      // eslint-disable-next-line no-control-regex -- control characters are the subject
      .replace(/\u001B\[[0-9;?]*[A-Za-z]/g, "")
      // OSC sequences, which is how an installer sets the window title.
      // eslint-disable-next-line no-control-regex -- control characters are the subject
      .replace(/\u001B\][^\u0007\u001B]*(?:\u0007|\u001B\\)/g, "")
      // A pty ends lines with CRLF and a progress bar returns the carriage on
      // its own; both become newlines, so fifty redraws read as fifty lines
      // rather than one that overwrote itself.
      .replace(/\r\n?/g, "\n")
  );
}
