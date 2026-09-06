/**
 * CAD Runtime (plan §8): `cad:check` as a page.
 *
 * The runtime is a pinned Python under this app's data folder with the bundled
 * cadgen wheel installed into it — about a gigabyte, so it is provisioned on
 * first launch rather than shipped in the installer. P5 provisions it; this
 * page is what says whether it worked, and the only place a person can ask for
 * it to be repaired.
 *
 * Until P5 lands `runtime.status` answers `missing`, which is the truth about
 * every build that has not run its provisioner.
 */
import { useEffect } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import {
  SettingCard,
  SettingRow,
  TextRow,
  useRowMatch,
} from "@renderer/features/settings/SettingCard";
import { StatusLabel, type Tone } from "@renderer/features/settings/StatusDot";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { useAppInfo } from "@renderer/features/settings/use-app-info";
import { useAgents } from "@renderer/state/agents";
import { usePlugins } from "@renderer/state/plugins";
import { useRuntime } from "@renderer/state/runtime";
import type { PluginStatus } from "@shared/ipc/plugins";
import type { RuntimeState } from "@shared/ipc/runtime";

const STATE_TONE: Record<RuntimeState, Tone> = {
  missing: "warn",
  installing: "busy",
  ready: "ok",
  error: "bad",
};

const STATE_LABEL: Record<RuntimeState, string> = {
  missing: "Not installed",
  installing: "Installing…",
  ready: "Ready",
  error: "Failed",
};

export function CadRuntimePage() {
  const settings = useSettingsValue();
  const patch = useSettingsPatch();
  const info = useAppInfo();
  const status = useRuntime((state) => state.status);
  const busy = useRuntime((state) => state.busy);
  const progress = useRuntime((state) => state.progress);
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
    status.cadgenVersion !== null && info !== null && status.cadgenVersion === info.version;

  return (
    <>
      <SettingCard title="Runtime">
        <SettingRow
          control={
            <>
              <StatusLabel tone={STATE_TONE[status.state]}>
                {STATE_LABEL[status.state]}
              </StatusLabel>
              <Button
                className="h-8 gap-1.5"
                disabled={busy || status.state === "installing"}
                onClick={() => void repair()}
                size="sm"
                variant={status.state === "ready" ? "secondary" : "default"}
              >
                <RefreshCw className="size-3.5" />
                {status.state === "ready" ? "Repair" : "Install"}
              </Button>
            </>
          }
          description={
            status.message ??
            "A pinned Python and the cadgen wheel that ships with this app, in this app's data folder."
          }
          keywords="python cadgen install repair provision"
          title="CAD runtime"
        >
          {progress ? (
            <pre className="max-h-32 overflow-auto rounded-lg border bg-muted/40 px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
              <code data-selectable>{progress}</code>
            </pre>
          ) : null}
        </SettingRow>

        <SettingRow
          control={
            <StatusLabel tone={status.python ? "ok" : "idle"}>
              {status.python ?? "Not provisioned"}
            </StatusLabel>
          }
          description={
            status.overridden
              ? "From the interpreter override below."
              : "The managed interpreter this app installed for itself."
          }
          keywords="interpreter venv python3"
          title="Python"
        />

        <SettingRow
          control={
            <StatusLabel tone={cadgenMatches ? "ok" : status.cadgenVersion ? "warn" : "idle"}>
              {status.cadgenVersion
                ? `${status.cadgenVersion}${cadgenMatches ? "" : ` · app is ${info?.version ?? "…"}`}`
                : "Not installed"}
            </StatusLabel>
          }
          description="Hardcore and cadgen are released from one commit and must be the same version."
          keywords="wheel version pin occt build123d"
          title="cadgen"
        />

        <SettingRow
          control={
            <StatusLabel tone={status.viewerBuilt ? "ok" : "idle"}>
              {status.viewerBuilt ? "Bundled" : "Not present"}
            </StatusLabel>
          }
          description="The CAD Viewer's client, which the wheel carries and the file tab renders."
          keywords="viewer client step glb render"
          title="Viewer client"
        />
      </SettingCard>

      <SettingCard title="Hardcore plugin — the cad skills and hardcore-app, per agent">
        {installed.length === 0 ? (
          <EmptyPluginsRow />
        ) : (
          installed.map((agent) => (
            <PluginRow
              key={agent.id}
              name={agent.name}
              status={pluginStatuses[agent.id] ?? null}
            />
          ))
        )}
      </SettingCard>

      <SettingCard title="Advanced">
        <TextRow
          description="Use this interpreter instead of the managed one. A checkout's .venv/bin/python, for development."
          keywords="override CAD_DESKTOP_PYTHON venv interpreter path"
          onChange={(value) => patch({ cadPythonOverride: value.trim() === "" ? null : value })}
          placeholder="/path/to/.venv/bin/python"
          title="Override interpreter"
          value={settings.cadPythonOverride ?? ""}
          width="w-[320px]"
        />
      </SettingCard>
    </>
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
      // No description: the card's heading says what the plugin is, and
      // repeating it under every agent's name is noise, not information.
      keywords="hardcore plugin skills marketplace cad"
      title={name}
    />
  );
}
