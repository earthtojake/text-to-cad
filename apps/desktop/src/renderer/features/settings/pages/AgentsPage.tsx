/**
 * Agents (plan §2, Emdash's page): the registry crossed with what the detector
 * found on this machine, in three groups, and a drawer for one of them.
 *
 * The page never starts an agent. Everything on it — installed or not, signed
 * in or not, which binary, which version — comes from `agents.list`, which is a
 * cache of a PATH probe. Spawning an adapter to find out whether an agent works
 * is what the first session is for.
 */
import { useEffect, useMemo, useState } from "react";
import { BookOpen, Download, RefreshCw, Search } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import { AgentDrawer } from "@renderer/features/settings/AgentDrawer";
import { AgentMark } from "@renderer/features/settings/AgentMark";
import { SettingCard, useRowMatch } from "@renderer/features/settings/SettingCard";
import { StatusDot, type Tone } from "@renderer/features/settings/StatusDot";
import { matchesQuery } from "@renderer/features/settings/search";
import { useAppInfo } from "@renderer/features/settings/use-app-info";
import { useAgents } from "@renderer/state/agents";
import { usePlugins } from "@renderer/state/plugins";
import type { AgentStatus, Platform } from "@shared/agents";

/**
 * The four the app is built around: two with a plugin system Hardcore's skills
 * install into, and two whose ACP support is first-party. Recommending is not
 * ranking — everything else is in the same list, one group down.
 */
const RECOMMENDED = new Set(["claude-code", "codex", "gemini-cli", "github-copilot"]);

const PLATFORMS: Record<string, Platform> = {
  darwin: "macos",
  win32: "windows",
  linux: "linux",
};

export function AgentsPage() {
  const agents = useAgents((state) => state.agents);
  const ready = useAgents((state) => state.ready);
  const load = useAgents((state) => state.load);
  const refresh = useAgents((state) => state.refresh);
  const loadPlugins = usePlugins((state) => state.load);
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
    void loadPlugins();
  }, [load, loadPlugins]);

  const platform = info ? (PLATFORMS[info.platform] ?? "linux") : "macos";

  const groups = useMemo(() => {
    const visible = agents.filter((agent) =>
      matchesQuery(filter, agent.name, agent.description, agent.id),
    );
    return {
      installed: visible.filter((agent) => agent.installed),
      recommended: visible.filter((agent) => !agent.installed && RECOMMENDED.has(agent.id)),
      rest: visible.filter((agent) => !agent.installed && !RECOMMENDED.has(agent.id)),
    };
  }, [agents, filter]);

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
            className="h-8 pl-8 text-sm"
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
            void refresh().finally(() => setRefreshing(false));
          }}
          size="sm"
          variant="secondary"
        >
          <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
          Refresh
        </Button>
      </div>

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

      {ready && groups.installed.length + groups.recommended.length + groups.rest.length === 0 ? (
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
 * One agent. The whole row opens the drawer; the two trailing controls are
 * buttons inside it, so the click that opens the docs must not also open the
 * drawer behind them.
 */
function AgentRow({ agent, onOpen }: { agent: AgentStatus; onOpen: () => void }) {
  const matched = useRowMatch(agent.name, agent.description, `agent acp ${agent.id}`);
  if (!matched) {
    return null;
  }

  const tone: Tone = agent.installed
    ? agent.auth === "unauthenticated"
      ? "warn"
      : "ok"
    : "idle";
  const detail = agent.installed
    ? [agent.version ? `v${agent.version}` : null, agent.auth === "unauthenticated" ? "not signed in" : null]
        .filter(Boolean)
        .join(" · ") || "installed"
    : agent.description;

  return (
    <div
      // Named explicitly: a div with `role="button"` and interactive children
      // gets no name from its contents, so without this the row is a button
      // with no label to a screen reader and to the e2e suite alike.
      aria-label={agent.name}
      className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent/50"
      // The row is a button; the trailing icons are buttons inside it, which
      // is not valid HTML nesting — so the row is a div with a button's role
      // and its keyboard behaviour instead.
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      role="button"
      tabIndex={0}
    >
      <AgentMark icon={agent.icon} id={agent.id} name={agent.name} />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm">
          {agent.name}
          {agent.installed ? <StatusDot tone={tone} /> : null}
        </p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{detail}</p>
      </div>
      <IconButton
        label={`${agent.name} documentation`}
        onClick={() => void window.hardcore.shell.openExternal({ url: agent.docsUrl })}
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
    <Button
      aria-label={label}
      className="size-7 shrink-0 text-muted-foreground"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      size="icon"
      title={label}
      variant="ghost"
    >
      {children}
    </Button>
  );
}
