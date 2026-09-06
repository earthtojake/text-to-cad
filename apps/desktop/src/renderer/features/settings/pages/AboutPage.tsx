/**
 * About & Updates (plan §10). The version, where it came from, the one
 * button the updater's current state allows — and the CAD runtime's status,
 * read-only: the runtime ships inside the app (plan §8, as revised), so what
 * used to be a page of its own is a block here that says whether it works,
 * with the one thing a person can do about it (Repair: look again).
 */
import { useEffect } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import {
  ActionRow,
  SettingCard,
  SettingRow,
  SwitchRow,
  ValueRow,
  useRowMatch,
} from "@renderer/features/settings/SettingCard";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { StatusLabel, type Tone } from "@renderer/features/settings/StatusDot";
import { useAppInfo } from "@renderer/features/settings/use-app-info";
import { useAgents } from "@renderer/state/agents";
import { usePlugins } from "@renderer/state/plugins";
import { useRuntime } from "@renderer/state/runtime";
import { useUpdates } from "@renderer/state/updates";
import type { PluginStatus } from "@shared/ipc/plugins";
import type { RuntimeSource, RuntimeState } from "@shared/ipc/runtime";

const REPOSITORY = "https://github.com/earthtojake/text-to-cad";
const DOCS = "https://texttocad.dev";
const LICENSES = `${REPOSITORY}/blob/main/LICENSE`;

const PLATFORMS: Record<string, string> = {
  darwin: "macOS",
  win32: "Windows",
  linux: "Linux",
};

const openExternal = (url: string) => () => void window.hardcore.shell.openExternal({ url });

export function AboutPage() {
  const info = useAppInfo();
  const settings = useSettingsValue();
  const patch = useSettingsPatch();

  return (
    <>
      <SettingCard title="About">
        <ValueRow
          description="Hardcore ships the cadgen release of the same number."
          keywords="build number release"
          title="Version"
          tone="strong"
          value={info?.version ?? "…"}
        />
        <ValueRow
          keywords="operating system os"
          title="Platform"
          value={info ? (PLATFORMS[info.platform] ?? info.platform) : "…"}
        />
        <ValueRow
          description="Development builds run from a checkout and are never updated in place."
          keywords="stable dev release track"
          title="Channel"
          value={info?.isDev ? "Development" : "Stable"}
        />
      </SettingCard>

      <SettingCard title="Updates">
        <SwitchRow
          checked={settings.checkUpdatesOnLaunch}
          description="Ask GitHub Releases for a newer build at launch, and every six hours after that."
          keywords="automatic check release"
          onChange={(checkUpdatesOnLaunch) => patch({ checkUpdatesOnLaunch })}
          title="Check for updates automatically"
        />
        <UpdateRow />
      </SettingCard>

      <RuntimeCard appVersion={info?.version ?? null} />

      <SettingCard title="Links">
        <ActionRow
          description="The CAD skills, cadgen and this app."
          keywords="documentation help guide"
          label="Open docs"
          onClick={openExternal(DOCS)}
          title="Documentation"
        />
        <ActionRow
          description="Issues, releases and the source of everything here."
          keywords="github source code"
          label="Open on GitHub"
          onClick={openExternal(REPOSITORY)}
          title="Repository"
        />
        <ActionRow
          description="Hardcore is MIT-licensed and built on other people's work."
          keywords="licences open source attribution mit"
          label="View licenses"
          onClick={openExternal(LICENSES)}
          title="Open-source licenses"
        />
      </SettingCard>
    </>
  );
}

/**
 * The updater, as one row: what the state is on the left, the only action that
 * state allows on the right.
 *
 * Nothing downloads without being asked and nothing restarts without being
 * asked — that is why `autoDownload` is off in `src/main/updater.ts`, and why
 * this is a button rather than a progress bar that appeared on its own.
 */
function UpdateRow() {
  const status = useUpdates((state) => state.status);
  const busy = useUpdates((state) => state.busy);
  const check = useUpdates((state) => state.check);
  const download = useUpdates((state) => state.download);
  const install = useUpdates((state) => state.install);

  const version = status.version ? ` ${status.version}` : "";

  const { description, action } = {
    unsupported: {
      description: "Updates are delivered to installed builds; this one runs from a checkout.",
      action: null,
    },
    idle: {
      description: "Hardcore is up to date.",
      action: { label: "Check now", onClick: check },
    },
    checking: { description: "Checking GitHub Releases…", action: null },
    available: {
      description: `Version${version} is available.`,
      action: { label: "Download", onClick: download },
    },
    downloading: {
      description: `Downloading${version}… ${Math.round(status.percent ?? 0)}%`,
      action: null,
    },
    downloaded: {
      description: `Version${version} is ready. Restarting installs it.`,
      action: { label: "Restart", onClick: install },
    },
    error: {
      description: status.message ?? "The update check failed.",
      action: { label: "Try again", onClick: check },
    },
  }[status.state];

  return (
    <SettingRow
      control={
        action ? (
          <Button
            className="h-8"
            disabled={busy}
            onClick={() => void action.onClick()}
            size="sm"
            variant={status.state === "downloaded" ? "default" : "secondary"}
          >
            {action.label}
          </Button>
        ) : (
          <span className="text-sm text-muted-foreground">
            {status.state === "checking" || status.state === "downloading" ? "…" : "—"}
          </span>
        )
      }
      description={description}
      keywords="update download install restart version"
      title="Software update"
    />
  );
}

/* -------------------------------------------------------------------------- */
/* The CAD runtime block                                                       */
/* -------------------------------------------------------------------------- */

const STATE_TONE: Record<RuntimeState, Tone> = {
  missing: "bad",
  ready: "ok",
  error: "bad",
};

const STATE_LABEL: Record<RuntimeState, string> = {
  missing: "Missing",
  ready: "Ready",
  error: "Failed",
};

const SOURCE_LABEL: Record<RuntimeSource, string> = {
  bundled: "Bundled with the app",
  checkout: "The checkout's .venv",
  override: "Override interpreter",
};

/**
 * `cad:check` as four rows: the runtime, cadgen, the viewer, and the plugin
 * per installed agent. Read-only apart from Repair, which is a fresh probe —
 * there is nothing to install.
 */
function RuntimeCard({ appVersion }: { appVersion: string | null }) {
  const status = useRuntime((state) => state.status);
  const busy = useRuntime((state) => state.busy);
  const load = useRuntime((state) => state.load);
  const repair = useRuntime((state) => state.repair);
  const agents = useAgents((state) => state.agents);
  const pluginStatuses = usePlugins((state) => state.statuses);
  const loadPlugins = usePlugins((state) => state.load);

  useEffect(() => {
    void load();
    void loadPlugins();
  }, [load, loadPlugins]);

  const installed = agents.filter((agent) => agent.installed);
  const cadgenMatches =
    status?.cadgenVersion != null && appVersion !== null && status.cadgenVersion === appVersion;

  return (
    <SettingCard title="CAD runtime">
      <SettingRow
        control={
          <>
            <StatusLabel tone={status ? STATE_TONE[status.state] : "busy"}>
              {status ? STATE_LABEL[status.state] : "Checking…"}
            </StatusLabel>
            <Button
              className="h-8 gap-1.5"
              disabled={busy || status === null}
              onClick={() => void repair()}
              size="sm"
              variant="secondary"
            >
              <RefreshCw className="size-3.5" />
              Repair
            </Button>
          </>
        }
        description={
          status?.state === "ready"
            ? `${status.source ? SOURCE_LABEL[status.source] : "Interpreter"}: ${status.python ?? ""}`
            : (status?.message ?? "The pinned Python and cadgen that ship inside Hardcore.")
        }
        keywords="python cadgen runtime repair interpreter bundled"
        title="Runtime"
      >
        {status?.log && status.state !== "ready" ? (
          <p className="truncate text-[11px] text-muted-foreground" title={status.log}>
            Log: <span data-selectable>{status.log}</span>
          </p>
        ) : null}
      </SettingRow>

      <SettingRow
        control={
          <StatusLabel tone={cadgenMatches ? "ok" : status?.cadgenVersion ? "warn" : "idle"}>
            {status?.cadgenVersion
              ? `${status.cadgenVersion}${cadgenMatches ? "" : ` · app is ${appVersion ?? "…"}`}`
              : "—"}
          </StatusLabel>
        }
        description="Hardcore and cadgen are released from one commit and must be the same version."
        keywords="wheel version pin occt build123d"
        title="cadgen"
      />

      <SettingRow
        control={
          <StatusLabel tone={status?.viewerBuilt ? "ok" : "idle"}>
            {status?.viewerBuilt ? "Ready" : "—"}
          </StatusLabel>
        }
        description="cadgen's viewer backend, which the file tab runs per project."
        keywords="viewer backend step glb render"
        title="Viewer"
      />

      {installed.length === 0 ? (
        <EmptyPluginsRow />
      ) : (
        installed.map((agent) => (
          <PluginRow key={agent.id} name={agent.name} status={pluginStatuses[agent.id] ?? null} />
        ))
      )}
    </SettingCard>
  );
}

function EmptyPluginsRow() {
  const matched = useRowMatch("Plugin", "No agents installed", "skills cad hardcore-app");
  if (!matched) {
    return null;
  }
  return (
    <p className="px-4 py-3 text-sm text-muted-foreground">
      No agents are installed yet. The Hardcore plugin is installed into each agent that is.
    </p>
  );
}

/** The Hardcore plugin — the cad skills and hardcore-app — in one agent. */
function PluginRow({ name, status }: { name: string; status: PluginStatus | null }) {
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
    <SettingRow
      control={<StatusLabel tone={tone}>{label}</StatusLabel>}
      description="The Hardcore plugin: the cad skills and hardcore-app."
      keywords="hardcore plugin skills marketplace cad"
      title={`Plugin in ${name}`}
    />
  );
}
