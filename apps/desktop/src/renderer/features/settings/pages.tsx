import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@renderer/components/ui/select";
import { Switch } from "@renderer/components/ui/switch";
import { PendingRow, SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { useSettings } from "@renderer/state/settings";
import { useUpdates } from "@renderer/state/updates";
import type { AppInfo, GitMode, ThemePreference } from "@shared/types";
import type { SettingsSection } from "@renderer/state/ui";

/**
 * The seven Settings pages (plan §10).
 *
 * P0 wires the ones whose state already exists — theme, telemetry, git
 * defaults, notification switches — and marks the rest with the phase that
 * fills them in. Every row is a `SettingRow`, so a page is a list of rows and
 * the layout is not something a page gets to decide.
 */
export function SettingsPage({ section }: { section: SettingsSection }) {
  switch (section) {
    case "general":
      return <GeneralPage />;
    case "agents":
      return <AgentsPage />;
    case "appearance":
      return <AppearancePage />;
    case "git":
      return <GitPage />;
    case "cad-runtime":
      return <CadRuntimePage />;
    case "shortcuts":
      return <ShortcutsPage />;
    case "about":
      return <AboutPage />;
  }
}

/* -------------------------------------------------------------------------- */

function GeneralPage() {
  const settings = useSettings((state) => state.settings);
  const patch = useSettings((state) => state.patch);

  return (
    <>
      <SettingCard title="App">
        <SettingRow
          control={
            <Switch
              checked={settings?.launchAtLogin ?? false}
              onCheckedChange={(launchAtLogin) => void patch({ launchAtLogin })}
            />
          }
          description="Start Hardcore when you log in."
          title="Launch at login"
        />
        <SettingRow
          control={
            <Switch
              checked={settings?.showInMenuBar ?? false}
              onCheckedChange={(showInMenuBar) => void patch({ showInMenuBar })}
            />
          }
          description="Keep an icon in the menu bar while the window is closed."
          title="Show in menu bar"
        />
        <SettingRow
          control={
            <Switch
              checked={settings?.telemetry ?? false}
              onCheckedChange={(telemetry) => void patch({ telemetry })}
            />
          }
          description="Anonymous counts of which features are used. Off by default; never file names, paths or prompts."
          title="Share usage data"
        />
      </SettingCard>

      <SettingCard title="Notifications">
        <SettingRow
          control={
            <Switch
              checked={settings?.notificationsEnabled ?? true}
              onCheckedChange={(notificationsEnabled) => void patch({ notificationsEnabled })}
            />
          }
          description="Tell me when a turn finishes while Hardcore is in the background."
          title="Notify on completion"
        />
        <SettingRow
          control={
            <Switch
              checked={settings?.notificationSound ?? false}
              onCheckedChange={(notificationSound) => void patch({ notificationSound })}
            />
          }
          description="Play a sound with the notification."
          title="Sound"
        />
      </SettingCard>

      <SettingCard title="Projects">
        <PendingRow
          description="Where the Add project dialog opens."
          phase="P6"
          title="Default project folder"
        />
      </SettingCard>
    </>
  );
}

/* -------------------------------------------------------------------------- */

function AgentsPage() {
  return (
    <SettingCard title="Agents">
      <PendingRow
        description="Installed, recommended and available agents, with install and auth state."
        phase="P1 · P6"
        title="Agent registry"
      />
      <PendingRow
        description="Hardcore's cad plugin and the hardcore-app skill, installed where each agent looks for them."
        phase="P5"
        title="Plugin install per agent"
      />
    </SettingCard>
  );
}

/* -------------------------------------------------------------------------- */

const THEMES: { value: ThemePreference; label: string; icon: React.ReactNode }[] = [
  { value: "system", label: "System", icon: <Monitor className="size-4" /> },
  { value: "light", label: "Light", icon: <Sun className="size-4" /> },
  { value: "dark", label: "Dark", icon: <Moon className="size-4" /> },
];

function AppearancePage() {
  const theme = useSettings((state) => state.settings?.theme ?? "system");
  const setTheme = useSettings((state) => state.setTheme);

  return (
    <>
      <SettingCard title="Theme">
        <div className="grid grid-cols-3 gap-3 p-4">
          {THEMES.map((option) => (
            <button
              aria-pressed={theme === option.value}
              className={cn(
                "flex flex-col items-center gap-2 rounded-lg border px-3 py-4 text-xs transition-colors",
                theme === option.value
                  ? "border-primary bg-accent"
                  : "hover:bg-accent/50",
              )}
              key={option.value}
              onClick={() => void setTheme(option.value)}
              type="button"
            >
              <span className="text-muted-foreground">{option.icon}</span>
              {option.label}
            </button>
          ))}
        </div>
      </SettingCard>

      <SettingCard title="Typography and density">
        <PendingRow description="Accent colour, fonts and contrast." phase="P6" title="Accent and fonts" />
      </SettingCard>
    </>
  );
}

/* -------------------------------------------------------------------------- */

const GIT_MODES: { value: GitMode; label: string }[] = [
  { value: "none", label: "Plain directory" },
  { value: "checkout", label: "Current branch" },
  { value: "worktree", label: "New worktree" },
];

function GitPage() {
  const settings = useSettings((state) => state.settings);
  const patch = useSettings((state) => state.patch);

  return (
    <>
      <SettingCard title="Sessions">
        <SettingRow
          control={
            <Select
              onValueChange={(value) => void patch({ defaultGitMode: value as GitMode })}
              value={settings?.defaultGitMode ?? "checkout"}
            >
              <SelectTrigger className="w-[180px]" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GIT_MODES.map((mode) => (
                  <SelectItem key={mode.value} value={mode.value}>
                    {mode.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
          description="What a new session's working directory is. Overridable per session."
          title="Default git mode"
        />
        <SettingRow
          control={
            <Input
              className="h-8 w-[180px]"
              onChange={(event) => void patch({ branchPrefix: event.target.value })}
              value={settings?.branchPrefix ?? "hardcore/"}
            />
          }
          description="Prepended to branches Hardcore creates."
          title="Branch prefix"
        />
      </SettingCard>

      <SettingCard title="Worktrees">
        <SettingRow
          control={
            <Switch
              checked={settings?.fetchBeforeCreate ?? true}
              onCheckedChange={(fetchBeforeCreate) => void patch({ fetchBeforeCreate })}
            />
          }
          description="Fetch the remote before branching a new worktree."
          title="Fetch before create"
        />
        <SettingRow
          control={
            <Switch
              checked={settings?.autoDeleteWorktrees ?? false}
              onCheckedChange={(autoDeleteWorktrees) => void patch({ autoDeleteWorktrees })}
            />
          }
          description={`Keep the ${settings?.worktreeKeepLimit ?? 10} most recent and remove the rest.`}
          title="Auto-delete old worktrees"
        />
        <PendingRow
          description="Where worktrees are created. Defaults to ~/.hardcore/worktrees."
          phase="P7"
          title="Worktree root"
        />
      </SettingCard>
    </>
  );
}

/* -------------------------------------------------------------------------- */

function CadRuntimePage() {
  return (
    <SettingCard title="CAD runtime">
      <PendingRow
        description="The managed Python and the bundled cadgen wheel, installed under this app's data folder."
        phase="P5"
        title="Runtime status"
      />
      <PendingRow
        description="Point Hardcore at a checkout's .venv instead of the managed runtime."
        phase="P5"
        title="Python override"
      />
      <PendingRow description="Reinstall the runtime from the bundled wheel." phase="P5" title="Repair" />
    </SettingCard>
  );
}

/* -------------------------------------------------------------------------- */

const SHORTCUTS: [string, string][] = [
  ["Command palette", "⌘K"],
  ["Toggle sidebar", "⌘B"],
  ["Toggle explorer", "⌘⌥B"],
  ["New session", "⌘N"],
  ["Settings", "⌘,"],
];

function ShortcutsPage() {
  return (
    <SettingCard title="Keyboard shortcuts">
      {SHORTCUTS.map(([label, keys]) => (
        <SettingRow
          control={
            <kbd className="rounded-md border bg-muted px-2 py-1 font-mono text-xs">{keys}</kbd>
          }
          key={label}
          title={label}
        />
      ))}
    </SettingCard>
  );
}

/* -------------------------------------------------------------------------- */

function AboutPage() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const settings = useSettings((state) => state.settings);
  const patch = useSettings((state) => state.patch);

  useEffect(() => {
    void window.hardcore.app.info().then(setInfo);
  }, []);

  return (
    <>
      <SettingCard title="About">
        <SettingRow
          control={<span className="text-sm text-muted-foreground">{info?.version ?? "…"}</span>}
          description="Hardcore ships with the cadgen release of the same number."
          title="Version"
        />
        <SettingRow
          control={<span className="text-sm text-muted-foreground">{info?.platform ?? "…"}</span>}
          title="Platform"
        />
        <SettingRow
          control={
            <Button
              onClick={() =>
                void window.hardcore.shell.openExternal({
                  url: "https://github.com/earthtojake/text-to-cad",
                })
              }
              size="sm"
              variant="secondary"
            >
              Open on GitHub
            </Button>
          }
          title="Source"
        />
      </SettingCard>

      <SettingCard title="Updates">
        <SettingRow
          control={
            <Switch
              checked={settings?.checkUpdatesOnLaunch ?? true}
              onCheckedChange={(checkUpdatesOnLaunch) => void patch({ checkUpdatesOnLaunch })}
            />
          }
          description="Ask GitHub Releases for a newer build when Hardcore starts, and every six hours after that."
          title="Check for updates automatically"
        />
        <UpdateRow />
      </SettingCard>
    </>
  );
}

/**
 * The updater, as one row: what the state is on the left, the only action that
 * state allows on the right.
 *
 * Nothing downloads without being asked and nothing restarts without being
 * asked — that is the whole reason `autoDownload` is off in
 * `src/main/updater.ts`, and the reason this is a button rather than a
 * progress bar that appeared on its own.
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
      description: `Downloading${version}… ${status.percent ?? 0}%`,
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
          <Button disabled={busy} onClick={() => void action.onClick()} size="sm" variant="secondary">
            {action.label}
          </Button>
        ) : (
          <span className="text-sm text-muted-foreground">
            {status.state === "checking" || status.state === "downloading" ? "…" : "—"}
          </span>
        )
      }
      description={description}
      title="Software update"
    />
  );
}
