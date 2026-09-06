/**
 * About & Updates (plan §10). The version, where it came from, and the one
 * button the updater's current state allows.
 */
import { Button } from "@renderer/components/ui/button";
import {
  ActionRow,
  SettingCard,
  SettingRow,
  SwitchRow,
  ValueRow,
} from "@renderer/features/settings/SettingCard";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { useAppInfo } from "@renderer/features/settings/use-app-info";
import { useUpdates } from "@renderer/state/updates";

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
