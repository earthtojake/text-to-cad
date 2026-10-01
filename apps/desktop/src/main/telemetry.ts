/**
 * Anonymous usage counts, off unless two separate things are true: a build-time
 * key (`TEXT_TO_CAD_APTABASE_KEY`, compiled in as `__APTABASE_KEY__` by
 * electron.vite.config.ts) and the user's own `telemetry` setting, which is on
 * with an opt-out (plan §14) and lives in Settings › General, beside the table
 * below.
 *
 * Without the key this module is inert — a development checkout and a community
 * build send nothing, and no network call is even attempted.
 *
 * ## What is sent
 *
 * Four events, and nothing else. The whole vocabulary is the `Event` union
 * below, so "what does this app phone home about" is answerable by reading one
 * type rather than grepping for call sites:
 *
 * | Event | Property | Why it is safe |
 * | --- | --- | --- |
 * | `app_launched` | — | a count of launches |
 * | `session_created` | `agent` — the registry id (`claude-code`, `codex`, …) | a fixed set of identifiers from the app's own table |
 * | `file_opened` | `extension` — `step`, `md`, `py`, … | the extension only, lowercased, never the name or the path |
 * | `settings_changed` | `key` — the settings field's name | the name of the field, never its value |
 *
 * Aptabase adds the app version, the OS and a per-install random id on its own.
 * Nothing here ever carries a path, a file name, a project name, a prompt, an
 * agent's output, or the contents of a setting.
 */
import { isDeepStrictEqual } from "node:util";

import { initialize, trackEvent } from "@aptabase/electron/main";
import { app } from "electron";

import { settings } from "./db/repositories";
import type { Settings } from "../shared/types";

const APTABASE_KEY = __APTABASE_KEY__;

let initialized = false;

/**
 * Every event the app can send, with the exact properties it may carry.
 *
 * A union rather than a `track(name, props)` free-for-all: the README documents
 * what is sent, and a documented list is only true if adding a fifth event is a
 * change to this type.
 */
export type Event =
  | { name: "app_launched" }
  | { name: "session_created"; agent: string }
  | { name: "file_opened"; extension: string }
  | { name: "settings_changed"; key: keyof Settings & string };

/**
 * Called once, at the top level of `src/main/index.ts` — BEFORE `app.whenReady()`.
 * Aptabase's `initialize` registers a privileged scheme, which Electron only
 * allows before ready, and so it returns early ("must be invoked before the app
 * is ready. Tracking will be disabled.") when the app already is. Called late,
 * every `trackEvent` would push into its pre-init buffer and nothing would ever
 * be sent — so a late call here refuses rather than pretending to be on.
 *
 * The app version reaches Aptabase from `app.getVersion()` on its own; nothing
 * is passed here beyond the key. The user's setting is not read here (the
 * database is not open yet): `track` reads it per event.
 */
export function initTelemetry() {
  if (!APTABASE_KEY || initialized) {
    return;
  }
  if (app.isReady()) {
    console.warn("[telemetry] initTelemetry() after app ready; telemetry disabled for this launch");
    return;
  }
  initialized = true;
  void initialize(APTABASE_KEY).catch((error: unknown) => {
    initialized = false;
    console.warn("[telemetry] initialize failed", error);
  });
}

/** The settings fields whose value differs between two snapshots. */
export function changedSettingsKeys<T extends object>(previous: T, next: T, patch: Partial<T>): (keyof T & string)[] {
  return (Object.keys(patch) as (keyof T & string)[]).filter(
    (key) => !isDeepStrictEqual(previous[key], next[key]),
  );
}

/**
 * Record an event, if telemetry is both configured and switched on.
 *
 * The setting is read per call rather than cached: turning telemetry off in
 * Settings has to stop the next event, not the next launch.
 */
export function track(event: Event) {
  if (!initialized) {
    return;
  }
  try {
    if (!settings.get().telemetry) {
      return;
    }
    const { name, ...props } = event;
    void trackEvent(name, Object.keys(props).length > 0 ? props : undefined);
  } catch (error) {
    // Telemetry must never be able to take the app down.
    console.warn("[telemetry] dropped event", event.name, error);
  }
}

/**
 * The extension of a path, lowercased and without its dot — the only part of a
 * file name `file_opened` is allowed to carry. Answers `"none"` for a file with
 * no extension so the event still counts, and `"other"` for a suffix that is
 * not a short run of letters and digits: whatever follows the last dot of
 * `plan.acme-q3-layoffs` is part of a name, not a file type.
 */
export function fileExtension(filePath: string): string {
  const base = filePath.split(/[\\/]/).pop() ?? "";
  const dot = base.lastIndexOf(".");
  if (dot <= 0 || dot === base.length - 1) {
    return "none";
  }
  const extension = base.slice(dot + 1).toLowerCase();
  return /^[a-z0-9]{1,8}$/.test(extension) ? extension : "other";
}

/** True when a key was compiled in — Settings shows the switch either way. */
export function telemetryAvailable() {
  return Boolean(APTABASE_KEY);
}
