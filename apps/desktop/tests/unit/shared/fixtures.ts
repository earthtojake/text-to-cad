/**
 * Replay a recorded adapter transcript (`tests/fixtures/acp/*.jsonl`, written
 * by `scripts/acp-harness.mjs --record`) through the reducer, the way the
 * live connection would: each wire frame becomes the reducer event the
 * connection would have dispatched for it.
 *
 * A fixture line is `{ dir: "in" | "out", at, msg }` — `in` is agent → client.
 */
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { pendingPermissionFromRequest, reduce, sessionModes, configOptions } from "@shared/acp/reduce";
import { initialSessionState, type SessionEvent, type SessionState } from "@shared/acp/types";

export const FIXTURE_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "fixtures",
  "acp",
);

export type Frame = { dir: "in" | "out"; at: number; msg: Record<string, unknown> };

export function fixtureFiles(): string[] {
  return readdirSync(FIXTURE_DIR)
    .filter((name) => name.endsWith(".jsonl"))
    .map((name) => path.join(FIXTURE_DIR, name));
}

export function readFixture(file: string): Frame[] {
  return readFileSync(file, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Frame);
}

/** The reducer events a connection would dispatch for these frames, in order. */
export function eventsFromFrames(frames: Frame[]): SessionEvent[] {
  const events: SessionEvent[] = [];
  const outRequests = new Map<unknown, Record<string, unknown>>();
  const inRequests = new Map<unknown, { requestId: string }>();
  let permissionCounter = 0;
  let acpSessionId: string | null = null;

  for (const frame of frames) {
    const { msg, at } = frame;
    const method = msg.method as string | undefined;
    const id = msg.id;
    const params = (msg.params ?? {}) as Record<string, unknown>;

    if (frame.dir === "out") {
      if (method && id !== undefined) {
        outRequests.set(id, msg);
        if (method === "session/prompt") {
          events.push({
            type: "prompt/start",
            turnId: `turn-${id}`,
            content: (params.prompt as { type: "text"; text: string }[]).filter((b) => b.type === "text"),
            at,
          });
        }
      } else if (id !== undefined && inRequests.has(id)) {
        // The client's answer to an agent request.
        const pending = inRequests.get(id)!;
        const result = msg.result as { outcome?: { outcome: string; optionId?: string } } | undefined;
        const outcome = result?.outcome;
        if (outcome) {
          events.push({
            type: "permission/resolve",
            requestId: pending.requestId,
            outcome:
              outcome.outcome === "selected"
                ? { state: "selected", optionId: outcome.optionId! }
                : { state: "cancelled" },
            at,
          });
        }
      }
      continue;
    }

    // dir === "in"
    if (method === "session/update") {
      events.push({
        type: "session/update",
        acpSessionId: params.sessionId as string,
        update: params.update as SessionEvent extends { update: infer U } ? U : never,
        at,
      });
      continue;
    }
    if (method === "session/request_permission" && id !== undefined) {
      const requestId = `perm-${++permissionCounter}`;
      const request = pendingPermissionFromRequest(requestId, params);
      if (request) {
        inRequests.set(id, { requestId });
        events.push({ type: "permission/request", request, at });
      }
      continue;
    }
    if (method) {
      continue; // fs/terminal requests and extension notifications
    }
    // A response to one of our requests.
    const request = outRequests.get(id);
    if (!request) {
      continue;
    }
    const result = msg.result as Record<string, unknown> | undefined;
    const error = msg.error as { message: string } | undefined;
    switch (request.method) {
      case "session/new":
      case "session/load": {
        if (error) {
          events.push({ type: "status", status: "error", error: error.message, at });
          break;
        }
        const modes = result?.modes as { currentModeId: string; availableModes: unknown } | undefined;
        acpSessionId =
          (result?.sessionId as string | undefined) ??
          ((request.params as Record<string, unknown>).sessionId as string | undefined) ??
          acpSessionId;
        events.push({
          type: "session/connected",
          acpSessionId: acpSessionId ?? "",
          modes: modes
            ? { currentModeId: modes.currentModeId, availableModes: sessionModes(modes.availableModes) }
            : null,
          configOptions: result?.configOptions ? configOptions(result.configOptions) : null,
          loading: request.method === "session/load",
          at,
        });
        if (request.method === "session/load") {
          events.push({ type: "session/loaded", at });
        }
        break;
      }
      case "session/prompt": {
        if (error) {
          events.push({ type: "prompt/error", message: error.message, at });
        } else {
          const usage = result?.usage as Record<string, number | null | undefined> | undefined;
          events.push({
            type: "prompt/end",
            stopReason: (result?.stopReason as SessionEvent extends { stopReason: infer S } ? S : never) ?? "end_turn",
            usage: usage
              ? {
                  totalTokens: usage.totalTokens ?? 0,
                  inputTokens: usage.inputTokens ?? 0,
                  outputTokens: usage.outputTokens ?? 0,
                  thoughtTokens: usage.thoughtTokens ?? null,
                  cachedReadTokens: usage.cachedReadTokens ?? null,
                  cachedWriteTokens: usage.cachedWriteTokens ?? null,
                }
              : null,
            at,
          });
        }
        break;
      }
      default:
        break;
    }
  }
  return events;
}

/** Fold a fixture into a SessionState. */
export function stateFromFixture(file: string, agentId = path.basename(file, ".jsonl")): SessionState {
  const events = eventsFromFrames(readFixture(file));
  return events.reduce(reduce, initialSessionState("fixture", agentId));
}
