/**
 * Agent settings, in a right-hand drawer (Emdash's shape, plan §2).
 *
 * Everything about one agent that the app can answer without starting it: where
 * its binary is, whether the user is signed in, whether Hardcore's plugin is
 * installed into it, and what the app will type when it launches it. The two
 * long-running actions — install and sign in — are pty jobs in main whose
 * output streams into the log under the button that started them, because an
 * installer that prints nothing for ninety seconds is indistinguishable from
 * one that has hung.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, Terminal } from "lucide-react";

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
import { AgentMark } from "@renderer/features/settings/AgentMark";
import { StatusLabel, type Tone } from "@renderer/features/settings/StatusDot";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { useAgents } from "@renderer/state/agents";
import { usePlugins } from "@renderer/state/plugins";
import type { AgentStatus, AuthState, Platform } from "@shared/agents";

const AUTH_TONE: Record<AuthState, Tone> = {
  authenticated: "ok",
  unauthenticated: "warn",
  unknown: "idle",
  "not-required": "ok",
};

const AUTH_LABEL: Record<AuthState, string> = {
  authenticated: "Signed in",
  unauthenticated: "Not signed in",
  unknown: "Unknown",
  "not-required": "No sign-in needed",
};

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
  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent
        className="w-full gap-0 overflow-y-auto p-0 sm:max-w-[520px]"
        side="right"
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
            <SheetDescription className="mt-0.5 text-xs">{agent.description}</SheetDescription>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            <span className="text-foreground">Supports:</span> {supports(agent)}
          </p>
          <Button
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={() =>
              void window.hardcore.shell.openExternal({ url: agent.websiteUrl })
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
        <PluginSection agent={agent} />
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
  const { jobId, output, running, start } = useJob();

  if (agent.installed) {
    return (
      <Section title="Installation">
        <div className="flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2.5 text-xs">
          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />
          <p className="min-w-0 break-all text-muted-foreground" data-selectable>
            Found at <span className="text-foreground">{agent.binaryPath}</span>
            {agent.version ? ` · v${agent.version}` : ""}
          </p>
        </div>
        {jobId ? <JobLog output={output} /> : null}
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
          onClick={() => void window.hardcore.shell.openExternal({ url: agent.docsUrl })}
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
          {running ? <Loader2 className="size-3.5 animate-spin" /> : null}
          Install
        </Button>
      </div>
      <p className="mt-2 font-mono text-[11px] break-all text-muted-foreground" data-selectable>
        {methods[index]?.command}
      </p>
      {jobId ? <JobLog output={output} /> : null}
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
  const { jobId, output, running, start } = useJob();

  const cliLogin = agent.authMethods.find((method) => method.type === "cli-login");
  const apiKey = agent.authMethods.find((method) => method.type === "api-key");

  return (
    <Section
      action={<StatusLabel tone={AUTH_TONE[agent.auth]}>{AUTH_LABEL[agent.auth]}</StatusLabel>}
      title="Authentication"
    >
      {cliLogin ? (
        <div className="flex items-center justify-between gap-3">
          <p className="min-w-0 text-xs text-muted-foreground">{cliLogin.label}</p>
          <Button
            className="h-8 gap-1.5"
            // Signing in runs the agent's own CLI, which has to be installed.
            disabled={running || !agent.installed}
            onClick={() => void start(() => login(agent.id))}
            size="sm"
            variant={agent.auth === "authenticated" ? "secondary" : "default"}
          >
            {running ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {agent.auth === "authenticated" ? "Sign in again" : "Sign in"}
          </Button>
        </div>
      ) : null}

      {!agent.installed && cliLogin ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Install {agent.name} first — signing in runs its own CLI.
        </p>
      ) : null}

      {apiKey ? (
        <div className="mt-3 rounded-lg border bg-muted/40 px-3 py-2.5">
          <p className="text-xs text-muted-foreground">
            {apiKey.label}: set one of these in the shell Hardcore launches from, then press
            Refresh.
          </p>
          <p className="mt-1.5 font-mono text-[11px]" data-selectable>
            {apiKey.envVars.join("  ·  ")}
          </p>
        </div>
      ) : null}

      {jobId ? <JobLog output={output} /> : null}
    </Section>
  );
}

/* -------------------------------------------------------------------------- */

function PluginSection({ agent }: { agent: AgentStatus }) {
  const status = usePlugins((state) => state.statuses[agent.id]);
  const installing = usePlugins((state) => state.installing === agent.id);
  const install = usePlugins((state) => state.install);
  const load = usePlugins((state) => state.load);

  useEffect(() => {
    if (!status) {
      void load();
    }
  }, [status, load]);

  const state = status?.state ?? "not-installed";
  const tone: Tone =
    state === "installed" ? "ok" : state === "update-available" ? "warn" : "idle";
  const label =
    state === "installed"
      ? `Installed ${status?.installedVersion ?? ""}`.trim()
      : state === "update-available"
        ? "Update available"
        : state === "unsupported"
          ? "No plugin system"
          : "Not installed";

  return (
    <Section action={<StatusLabel tone={tone}>{label}</StatusLabel>} title="Plugins">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm">Hardcore plugin</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            The cad skills and hardcore-app-use, installed where {agent.name} looks for them, and
            versioned with this app.
          </p>
        </div>
        <Button
          className="h-8 gap-1.5"
          disabled={installing || state === "unsupported"}
          onClick={() => void install(agent.id)}
          size="sm"
          variant={state === "installed" ? "secondary" : "default"}
        >
          {installing ? <Loader2 className="size-3.5 animate-spin" /> : null}
          {state === "update-available" ? "Update" : state === "installed" ? "Reinstall" : "Install"}
        </Button>
      </div>
      {status?.message ? (
        <p className="mt-2 text-xs text-muted-foreground">{status.message}</p>
      ) : null}
    </Section>
  );
}

/* -------------------------------------------------------------------------- */

function McpSection({ agent }: { agent: AgentStatus }) {
  const count = usePlugins((state) => state.statuses[agent.id]?.mcpServers ?? 0);
  return (
    <Section title="MCP servers">
      <p className="text-xs text-muted-foreground">
        {count === 0
          ? `None configured for ${agent.name}. Every Hardcore session also gets the app's own server, which is how an agent opens a file in the explorer.`
          : `${count} configured for ${agent.name}, plus Hardcore's own.`}
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

  // Initialised from the stored value and owned by the fields after that; the
  // drawer is keyed by agent id, so switching agents remounts this rather than
  // synchronising two copies of the same string.
  const [extraArgs, setExtraArgs] = useState(() => (override?.extraArgs ?? []).join(" "));
  const [env, setEnv] = useState(() => formatEnv(override?.env ?? {}));

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
        onBlur={() => save(extraArgs, env)}
        onChange={(event) => setExtraArgs(event.target.value)}
        placeholder="--verbose --model gpt-6"
        value={extraArgs}
      />

      <label className="mt-3 block text-xs" htmlFor={`${agent.id}-env`}>
        Environment
      </label>
      <Textarea
        className="mt-1.5 min-h-16 font-mono text-xs"
        id={`${agent.id}-env`}
        onBlur={() => save(extraArgs, env)}
        onChange={(event) => setEnv(event.target.value)}
        placeholder={"KEY=value\nANOTHER=value"}
        value={env}
      />
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        One per line. Merged over the launch environment when Hardcore starts {agent.name}.
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

/** `KEY=value` lines → a record. Blank lines and comments are ignored. */
export function parseEnv(text: string): Record<string, string> {
  const entries: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "" || trimmed.startsWith("#")) {
      continue;
    }
    const split = trimmed.indexOf("=");
    if (split <= 0) {
      continue;
    }
    entries[trimmed.slice(0, split).trim()] = trimmed.slice(split + 1).trim();
  }
  return entries;
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
 */
function useJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useAgents((state) => (jobId ? state.jobs[jobId] : undefined));
  const starting = useRef(false);

  const start = async (run: () => Promise<string>) => {
    if (starting.current) {
      return;
    }
    starting.current = true;
    try {
      setJobId(await run());
    } finally {
      starting.current = false;
    }
  };

  return {
    jobId,
    output: job?.output ?? "",
    // A job with an exit code has finished, whatever the code was.
    running: jobId !== null && (job?.exitCode ?? null) === null,
    start,
  };
}

/** The tail of a running job, scrolled to the bottom. */
function JobLog({ output }: { output: string }) {
  const ref = useRef<HTMLPreElement>(null);
  const text = useMemo(() => stripAnsi(output).trimEnd(), [output]);

  useEffect(() => {
    const node = ref.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [text]);

  return (
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
