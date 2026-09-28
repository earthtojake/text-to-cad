/**
 * General (plan §10): where files come from and go, and what the app is
 * allowed to do outside its own window — start itself, sit in the menu bar,
 * make a noise, count a launch.
 */
import { useEffect, useState } from "react";
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
import type { SentEvent, TelemetryStatus } from "@shared/ipc/telemetry";

const OPEN_WITH: { value: FileOpenDestination; label: string }[] = [
  { value: "reveal", label: isMac ? "Reveal in Finder" : "Show in Explorer" },
  { value: "editor", label: "Default editor" },
  { value: "custom", label: "Custom command" },
];

const TIMING: { value: NotificationSoundTiming; label: string }[] = [
  { value: "always", label: "Always" },
  { value: "unfocused", label: "When unfocused" },
];

/**
 * What telemetry sent this run, and whether it can send at all, from main
 * (`telemetry.status`, `telemetry.log`). Read when the page opens and again
 * when the switch is used; a list, not a promise.
 */
function useTelemetryReport(refreshKey: unknown) {
  const [status, setStatus] = useState<TelemetryStatus | null>(null);
  const [events, setEvents] = useState<SentEvent[]>([]);
  useEffect(() => {
    let cancelled = false;
    void Promise.all([window.textToCad.telemetry.status(), window.textToCad.telemetry.log()])
      .then(([nextStatus, log]) => {
        if (cancelled) return;
        setStatus(nextStatus);
        setEvents(log.events);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);
  return { status, events };
}

/** Why nothing is sent, in words, or null when it can be. */
export function telemetryStatusLine(status: TelemetryStatus | null): string | null {
  if (!status || status.available) return null;
  if (status.reason === "no-key") return "This build has no telemetry key, so nothing is sent whatever the switch says.";
  return `Off for this run: ${status.variable ?? "the environment"} is set. Nothing is sent whatever the switch says.`;
}

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

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
  const report = useTelemetryReport(settings.telemetry);
  const statusLine = telemetryStatusLine(report.status);

  return (
    <>
      <SettingCard title="Files and projects">
        <PathRow
          description="Where the Open folder chooser opens."
          keywords="directory workspace"
          onChoose={() => {
            void window.textToCad.dialogs
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
          description="text-to-cad follows the system language. More languages are not translated yet."
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
          description="Start text-to-cad when you log in."
          keywords="startup boot"
          onChange={(launchAtLogin) => patch({ launchAtLogin })}
          title="Launch at login"
        />
        {isMac ? (
          <SwitchRow
            checked={settings.showInMenuBar}
            description="Keep a text-to-cad item in the menu bar for bringing the window back."
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
          description="An aiff, wav, mp3 or m4a file. Empty plays text-to-cad's own chime."
          keywords="audio file custom"
          onChoose={() => {
            void window.textToCad.dialogs
              .chooseFile({
                title: "Notification sound",
                filters: [{ name: "Audio", extensions: ["aiff", "aif", "wav", "mp3", "m4a", "ogg"] }],
              })
              .then((chosen) => chosen && patch({ notificationSoundFile: chosen.path }));
          }}
          onClear={() => patch({ notificationSoundFile: null })}
          placeholder="text-to-cad chime"
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
            path, a file name, a project name, a prompt or an agent's output. Set{" "}
            <code>DO_NOT_TRACK=1</code> or <code>TEXT_TO_CAD_TELEMETRY=0</code> in the environment
            to switch it off for every profile.
          </p>
          {statusLine ? (
            <p className="mt-2 px-1 text-xs text-muted-foreground" data-telemetry-status>
              {statusLine}
            </p>
          ) : null}
          <div className="mt-3 px-1" data-telemetry-log>
            <p className="text-xs text-foreground">
              Sent this run: {report.events.length === 0 ? "nothing yet" : `${report.events.length} ${report.events.length === 1 ? "event" : "events"}`}
            </p>
            {report.events.length > 0 ? (
              <ol className="mt-1 max-h-40 overflow-y-auto rounded-lg bg-muted/50 px-3 py-2 font-mono text-[11px] leading-5 text-muted-foreground">
                {report.events.map((event, index) => (
                  <li key={`${event.at}-${index}`}>
                    <span className="text-foreground/70">{timeFormat.format(event.at)}</span> {event.name}
                    {Object.entries(event.props).map(([key, value]) => ` ${key}=${value}`).join("")}
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
        </SwitchRow>
      </SettingCard>
    </>
  );
}
