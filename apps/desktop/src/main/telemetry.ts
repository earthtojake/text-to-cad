/**
 * Anonymous usage counts, off unless two separate things are true: a build-time
 * key (`TEXT_TO_CAD_APTABASE_KEY`, compiled in as `__APTABASE_KEY__` by
 * electron.vite.config.ts) and the user's own `telemetry` setting, which is on
 * with an opt-out (plan §14) and lives in Settings › General, beside the table
 * below.
 *
 * Without the key this module is inert — a development checkout and a community
 * build send nothing, and no network call is even attempted. The environment
 * can switch it off too (`environmentOptOut`): `DO_NOT_TRACK=1`, the Console Do
 * Not Track convention; `CI`, so a build farm never counts as a person;
 * `TEXT_TO_CAD_TELEMETRY=0`; and the test suites' `NODE_ENV=test`.
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
 *
 * ## Nothing before the person has been told
 *
 * The first launch shows a notice saying exactly this, with a Turn off button
 * (`features/settings/telemetry-notice.ts`). Until the notice has been shown
 * once (`telemetryNoticeShown`), events are held in a small queue for this run
 * and go out when it has; if the run ends first, they are dropped. So the first
 * event ever sent is one the person could have stopped.
 *
 * ## What was sent
 *
 * Every event that went out this run is kept in memory (`sentEvents`), and
 * Settings › General prints the list: the answer to "what has it sent?" is the
 * list itself, not a promise.
 */
import { initialize, trackEvent } from "@aptabase/electron/main";

import { settings } from "./db/repositories";
import { environmentOptOut, type EnvironmentOptOut } from "./telemetry-env";
import { SettingsSchema, type Settings } from "../shared/types";

const APTABASE_KEY = __APTABASE_KEY__;

let initialized = false;
let environmentReason: EnvironmentOptOut | null = null;

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

/** One event that went out, for the log. */
export type SentEvent = { name: Event["name"]; props: Record<string, string>; at: number };

/** The settings fields `settings_changed` may name: the schema's, and no other. */
const SETTINGS_KEYS = new Set(Object.keys(SettingsSchema.shape));

/**
 * Called once at startup, after the database is open. The app version reaches
 * Aptabase from `app.getVersion()` on its own; nothing is passed here beyond
 * the key.
 */
export function initTelemetry(env: NodeJS.ProcessEnv = process.env) {
  environmentReason = environmentOptOut(env);
  if (!APTABASE_KEY || environmentReason) {
    return;
  }
  void initialize(APTABASE_KEY);
  initialized = true;
}

/** How many events wait for the notice, at most: a launch's worth, not a session's. */
const QUEUE_LIMIT = 20;
/** How many sent events the log keeps. */
const LOG_LIMIT = 100;
const queued: Event[] = [];
const sent: SentEvent[] = [];

function send(event: Event) {
  const { name, ...rest } = event;
  const props = Object.fromEntries(Object.entries(rest).map(([key, value]) => [key, String(value)]));
  void trackEvent(name, Object.keys(props).length > 0 ? props : undefined);
  sent.push({ name, props, at: Date.now() });
  if (sent.length > LOG_LIMIT) sent.splice(0, sent.length - LOG_LIMIT);
}

/**
 * Record an event, if telemetry is both configured and switched on.
 *
 * The setting is read per call rather than cached: turning telemetry off in
 * Settings has to stop the next event, not the next launch. Before the notice
 * has been shown the event waits (see the header).
 */
export function track(event: Event) {
  if (!initialized) {
    return;
  }
  try {
    if (event.name === "settings_changed" && !SETTINGS_KEYS.has(event.key)) {
      return;
    }
    const current = settings.get();
    if (!current.telemetry) {
      return;
    }
    if (!current.telemetryNoticeShown) {
      if (queued.length < QUEUE_LIMIT) queued.push(event);
      return;
    }
    send(event);
  } catch (error) {
    // Telemetry must never be able to take the app down.
    console.warn("[telemetry] dropped event", event.name, error);
  }
}

/**
 * The notice has been shown: what waited goes out now, unless the person used
 * the notice to turn telemetry off, in which case it is dropped — that is what
 * the wait was for.
 */
export function flushTelemetryQueue() {
  const waiting = queued.splice(0, queued.length);
  if (!initialized) return;
  try {
    if (!settings.get().telemetry) return;
    for (const event of waiting) send(event);
  } catch (error) {
    console.warn("[telemetry] dropped queued events", error);
  }
}

/** What went out this run, oldest first. */
export function sentEvents(): SentEvent[] {
  return sent.map((event) => ({ ...event, props: { ...event.props } }));
}

/**
 * The extension of a path, lowercased and without its dot — the only part of a
 * file name `file_opened` is allowed to carry. Answers `"none"` for a file with
 * no extension so the event still counts.
 */
export function fileExtension(filePath: string): string {
  const base = filePath.split(/[\\/]/).pop() ?? "";
  const dot = base.lastIndexOf(".");
  if (dot <= 0 || dot === base.length - 1) {
    return "none";
  }
  return base.slice(dot + 1).toLowerCase();
}

/** True when a key was compiled in — Settings shows the switch either way. */
export function telemetryAvailable() {
  return Boolean(APTABASE_KEY);
}

/**
 * Why nothing is being sent, when nothing is, for Settings to say: no key in
 * this build, or the environment's variable. Null when telemetry can send.
 */
export function telemetryStatus(): { available: boolean; reason: "no-key" | "environment" | null; variable: string | null } {
  if (!APTABASE_KEY) return { available: false, reason: "no-key", variable: null };
  if (environmentReason) return { available: false, reason: "environment", variable: environmentReason.variable };
  return { available: true, reason: null, variable: null };
}
