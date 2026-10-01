/**
 * Agents (plan §2, Emdash's page): the registry crossed with what the detector
 * found on this machine, in three groups, and a drawer for one of them.
 *
 * The page never starts an agent. Everything on it — installed or not, signed
 * in or not, which binary, which version — comes from `agents.list`, which is a
 * cache of a PATH probe. Spawning an adapter to find out whether an agent works
 * is what the first session is for.
 */
import { useEffect, useId, useMemo, useState } from "react";
import { AlertCircle, BookOpen, Download, RefreshCw, Search } from "lucide-react";
import { cn } from "cn";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { Alert, AlertDescription, AlertTitle } from "@renderer/components/ui/alert";
import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import { AgentDrawer } from "@renderer/features/settings/AgentDrawer";
import { AgentMark } from "@renderer/features/settings/AgentMark";
import { InlineCode } from "@renderer/features/settings/inline-code";
import { SettingCard, useRowMatch } from "@renderer/features/settings/SettingCard";
import { StatusDot, type Tone } from "@renderer/features/settings/StatusDot";
import { matchesQuery, useSettingsQuery } from "@renderer/features/settings/search";
import { useAppInfo } from "@renderer/features/settings/use-app-info";
import { useAgents } from "@renderer/state/agents";
import { errorMessage } from "@shared/ipc/errors";
import type { AgentStatus, Platform } from "@shared/agents";

/**
 * The four the app is built around: two that load the skills text-to-cad hands a
 * session by themselves, and two whose ACP support is first-party. Recommending
 * is not ranking — everything else is in the same list, one group down.
 */
const RECOMMENDED = new Set(["claude-code", "codex", "gemini-cli", "github-copilot"]);

const PLATFORMS: Record<string, Platform> = {
  darwin: "macos",
  win32: "windows",
  linux: "linux",
};

/** What the Settings search reads on an agent's row. */
function agentRowText(agent: AgentStatus) {
  return [agent.name, agent.description, `agent acp ${agent.id}`];
}

export function AgentsPage() {
  const agents = useAgents((state) => state.agents);
  const ready = useAgents((state) => state.ready);
  const loadError = useAgents((state) => state.loadError);
  const load = useAgents((state) => state.load);
  const refresh = useAgents((state) => state.refresh);
  const info = useAppInfo();
  const [filter, setFilter] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  // Two pieces of state for one drawer: which agent it is showing, and whether
  // it is open. The first outlives the second so the panel still has contents
  // while it slides out.
  const [shownId, setShownId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    void load();
  }, [load]);

  const platform = info ? (PLATFORMS[info.platform] ?? "linux") : "macos";

  // The Settings search hides rows through `useRowMatch`; the counts have to
  // ask the same question or "Installed (4)" sits over one row.
  const query = useSettingsQuery();

  const groups = useMemo(() => {
    const visible = agents.filter(
      (agent) =>
        matchesQuery(filter, agent.name, agent.description, agent.id) &&
        matchesQuery(query, ...agentRowText(agent)),
    );
    return {
      installed: visible.filter((agent) => agent.installed),
      recommended: visible.filter((agent) => !agent.installed && RECOMMENDED.has(agent.id)),
      rest: visible.filter((agent) => !agent.installed && !RECOMMENDED.has(agent.id)),
    };
  }, [agents, filter, query]);

  const shown = agents.find((agent) => agent.id === shownId) ?? null;

  const openAgent = (id: string) => {
    setShownId(id);
    setDrawerOpen(true);
  };

  return (
    <>
      <div className="mb-5 flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Search agents"
            className="h-8 pl-8! text-sm"
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Search agents"
            value={filter}
          />
        </div>
        <Button
          className="h-8 gap-1.5"
          disabled={refreshing}
          onClick={() => {
            setRefreshing(true);
            // A refresh main refuses is the same "Could not read the agent list" alert a failed first read draws.
            void refresh()
              .catch((error) => useAgents.setState({ loadError: errorMessage(error) }))
              .finally(() => setRefreshing(false));
          }}
          size="sm"
          variant="secondary"
        >
          <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {loadError ? (
        <Alert className="mb-4" variant="destructive">
          <AlertCircle />
          <AlertTitle>Could not read the agent list</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : null}

      {!ready && agents.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">Looking for agents on this machine…</p>
      ) : null}

      <AgentGroup
        agents={groups.installed}
        onOpen={openAgent}
        title={`Installed (${groups.installed.length})`}
      />
      <AgentGroup
        agents={groups.recommended}
        onOpen={openAgent}
        title={`Recommended (${groups.recommended.length})`}
      />
      <AgentGroup
        agents={groups.rest}
        onOpen={openAgent}
        title={`Not installed (${groups.rest.length})`}
      />

      {ready && !loadError && !query && groups.installed.length + groups.recommended.length + groups.rest.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">No agent matches “{filter}”.</p>
      ) : null}

      <AgentDrawer
        agent={shown}
        onOpenChange={setDrawerOpen}
        open={drawerOpen}
        platform={platform}
      />
    </>
  );
}

function AgentGroup({
  title,
  agents,
  onOpen,
}: {
  title: string;
  agents: AgentStatus[];
  onOpen: (id: string) => void;
}) {
  if (agents.length === 0) {
    return null;
  }
  return (
    <SettingCard title={title}>
      {agents.map((agent) => (
        <AgentRow agent={agent} key={agent.id} onOpen={() => onOpen(agent.id)} />
      ))}
    </SettingCard>
  );
}

/**
 * One agent. The row opens the drawer; the two trailing controls are its
 * siblings, not its children — a control inside a button (or a `role=button`)
 * is nested-interactive, one stop a screen reader cannot tell apart — so the
 * row is a toolbar-like line: the agent's button, then Docs and Install.
 * A pointer anywhere on the line opens the drawer as before; the trailing
 * buttons stop their own clicks.
 */
function AgentRow({ agent, onOpen }: { agent: AgentStatus; onOpen: () => void }) {
  const matched = useRowMatch(...agentRowText(agent));
  const detailId = useId();
  if (!matched) {
    return null;
  }

  // Next to "checking sign-in…" the dot claims nothing, as the drawer's does.
  const tone: Tone = agent.installed
    ? agent.auth === "unauthenticated"
      ? agent.probing
        ? "idle"
        : "warn"
      : "ok"
    : "idle";
  const detail = agent.installed
    ? [
        agent.version ? `v${agent.version}` : null,
        // The CLI's version is the person's; the adapter's is the app's pin.
        agent.adapter ? `adapter ${agent.adapter.version}` : null,
        agent.auth === "unauthenticated" ? (agent.probing ? "checking sign-in…" : "not signed in") : null,
      ]
        .filter(Boolean)
        .join(" · ") || "installed"
    : <InlineCode text={agent.description} />;

  return (
    <div
      className="flex w-full items-center gap-3 px-4 py-2.5 transition-colors hover:bg-accent/50"
      data-agent-row={agent.id}
      onClick={onOpen}
    >
      <button
        // The agent's name; the line under it is its description.
        aria-describedby={detailId}
        aria-label={agent.name}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        onClick={(event) => {
          // The line's own click opens it, once.
          event.stopPropagation();
          onOpen();
        }}
        type="button"
      >
        <AgentMark icon={agent.icon} id={agent.id} name={agent.name} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-sm">
            {agent.name}
            {agent.installed ? <StatusDot tone={tone} /> : null}
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground" id={detailId}>{detail}</span>
        </span>
      </button>
      <IconButton
        label={`${agent.name} documentation`}
        onClick={() => void window.textToCad.shell.openExternal({ url: agent.docsUrl })}
      >
        <BookOpen className="size-3.5" />
      </IconButton>
      {agent.installed ? null : (
        // Installing opens the drawer rather than starting a command from a
        // list row: there is a choice of install method, and an install with
        // no visible output is one nobody can tell has failed.
        <IconButton label={`Install ${agent.name}…`} onClick={onOpen}>
          <Download className="size-3.5" />
        </IconButton>
      )}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <TooltipHint content={label}>
      <Button
        aria-label={label}
        className="size-7 shrink-0 text-muted-foreground"
        onClick={(event) => {
          event.stopPropagation();
          onClick();
        }}
        size="icon"
        variant="ghost"
      >
        {children}
      </Button>
    </TooltipHint>
  );
}
