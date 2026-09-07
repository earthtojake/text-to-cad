/**
 * General (plan §10): where files come from and go, and what the app is
 * allowed to do outside its own window — start itself, sit in the menu bar,
 * make a noise, count a launch.
 */
import { Play } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { Switch } from "@renderer/components/ui/switch";
import {
  PathRow,
  SelectRow,
  SettingCard,
  SettingRow,
  SwitchRow,
  TextRow,
} from "@renderer/features/settings/SettingCard";
import { playNotificationSound } from "@renderer/features/settings/sound";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { isMac } from "@renderer/lib/platform";
import type { FileOpenDestination, NotificationSoundTiming } from "@shared/types";

const OPEN_WITH: { value: FileOpenDestination; label: string }[] = [
  { value: "reveal", label: isMac ? "Reveal in Finder" : "Show in Explorer" },
  { value: "editor", label: "Default editor" },
  { value: "custom", label: "Custom command" },
];

const TIMING: { value: NotificationSoundTiming; label: string }[] = [
  { value: "always", label: "Always" },
  { value: "unfocused", label: "When unfocused" },
];

/** The whole vocabulary of `src/main/telemetry.ts`, printed rather than summarised. */
const TELEMETRY_EVENTS: [string, string][] = [
  ["App launched", "nothing else"],
  ["Session created", "which agent, by its registry id"],
  ["File opened", "the extension — step, md, py — never the name or the path"],
  ["Settings changed", "the name of the field, never its value"],
];

export function GeneralPage() {
  const settings = useSettingsValue();
  const patch = useSettingsPatch();

  return (
    <>
      <SettingCard title="Files and projects">
        <PathRow
          description="Where the Add project chooser opens."
          keywords="directory workspace"
          onChoose={() => {
            void window.hardcore.dialogs
              .chooseDirectory({
                title: "Default project folder",
                defaultPath: settings.defaultProjectFolder ?? undefined,
              })
              .then((chosen) => chosen && patch({ defaultProjectFolder: chosen.path }));
          }}
          onClear={() => patch({ defaultProjectFolder: null })}
          placeholder="Your home folder"
          title="Default project folder"
          value={settings.defaultProjectFolder}
        />
        <SelectRow
          description="What “Open” does with a file the explorer is showing."
          keywords="finder explorer editor external"
          onChange={(fileOpenDestination) => patch({ fileOpenDestination })}
          options={OPEN_WITH}
          title="Open files with"
          value={settings.fileOpenDestination}
        />
        {settings.fileOpenDestination === "custom" ? (
          <TextRow
            description="Run for the file being opened. {path} is replaced with its absolute path."
            keywords="command line argument"
            onChange={(fileOpenCommand) => patch({ fileOpenCommand })}
            placeholder="code -g {path}"
            title="Custom command"
            value={settings.fileOpenCommand}
            width="w-[280px]"
          />
        ) : null}
        <SelectRow
          description="Hardcore follows the system language. More languages are not translated yet."
          keywords="locale translation"
          onChange={(language) => patch({ language })}
          options={[{ value: "auto", label: "Auto" }]}
          title="Language"
          value={settings.language}
          width="w-[140px]"
        />
      </SettingCard>

      <SettingCard title="App">
        <SwitchRow
          checked={settings.launchAtLogin}
          description="Start Hardcore when you log in."
          keywords="startup boot"
          onChange={(launchAtLogin) => patch({ launchAtLogin })}
          title="Launch at login"
        />
        {isMac ? (
          <SwitchRow
            checked={settings.showInMenuBar}
            description="Keep a Hardcore item in the menu bar for bringing the window back."
            keywords="tray status bar"
            onChange={(showInMenuBar) => patch({ showInMenuBar })}
            title="Show in menu bar"
          />
        ) : null}
      </SettingCard>

      <SettingCard title="Notifications">
        <SwitchRow
          checked={settings.notificationsEnabled}
          description="Tell me when a turn finishes or an agent asks for permission."
          keywords="notify alert"
          onChange={(notificationsEnabled) => patch({ notificationsEnabled })}
          title="Notifications"
        />
        <SettingRow
          control={
            <>
              <Button
                className="h-8 gap-1.5"
                disabled={!settings.notificationsEnabled || !settings.notificationSound}
                onClick={() => void playNotificationSound(settings.notificationSoundFile)}
                size="sm"
                variant="secondary"
              >
                <Play className="size-3.5" />
                Preview
              </Button>
              <Switch
                aria-label="Sound"
                checked={settings.notificationSound}
                disabled={!settings.notificationsEnabled}
                onCheckedChange={(notificationSound) => patch({ notificationSound })}
              />
            </>
          }
          description="Play a sound with the notification."
          keywords="audio chime"
          title="Sound"
        />
        <PathRow
          chooseLabel="Choose…"
          description="An aiff, wav, mp3 or m4a file. Empty plays Hardcore's own chime."
          keywords="audio file custom"
          onChoose={() => {
            void window.hardcore.dialogs
              .chooseFile({
                title: "Notification sound",
                filters: [{ name: "Audio", extensions: ["aiff", "aif", "wav", "mp3", "m4a", "ogg"] }],
              })
              .then((chosen) => chosen && patch({ notificationSoundFile: chosen.path }));
          }}
          onClear={() => patch({ notificationSoundFile: null })}
          placeholder="Hardcore chime"
          title="Custom sound"
          value={settings.notificationSoundFile}
        />
        <SelectRow
          description="Whether the sound plays while you are looking at the window."
          keywords="focus background"
          onChange={(notificationSoundTiming) => patch({ notificationSoundTiming })}
          options={TIMING}
          title="Play sound"
          value={settings.notificationSoundTiming}
          width="w-[180px]"
        />
        <SwitchRow
          checked={settings.notificationOsBanners}
          description="Show notifications in the system's own notification centre as well."
          keywords="banner system notification centre center"
          onChange={(notificationOsBanners) => patch({ notificationOsBanners })}
          title="OS notifications"
        />
      </SettingCard>

      <SettingCard title="Privacy">
        <SwitchRow
          checked={settings.telemetry}
          description="Anonymous counts through Aptabase. Four events, listed below, and nothing else."
          keywords="telemetry analytics aptabase usage data"
          onChange={(telemetry) => patch({ telemetry })}
          title="Share usage data"
        >
          <dl className="grid grid-cols-[minmax(0,9rem)_1fr] gap-x-4 gap-y-1 rounded-lg bg-muted/50 px-3 py-2.5 text-xs">
            {TELEMETRY_EVENTS.map(([event, carries]) => (
              <div className="contents" key={event}>
                <dt className="text-foreground">{event}</dt>
                <dd className="text-muted-foreground">{carries}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 px-1 text-xs text-muted-foreground">
            Aptabase adds the app version, the OS and a random per-install id. Nothing carries a
            path, a file name, a project name, a prompt or an agent's output.
          </p>
        </SwitchRow>
      </SettingCard>
    </>
  );
}
