/**
 * The recorded adapter transcripts on disk (`tests/fixtures/acp/*.jsonl`),
 * read for the reducer and connection tests. The frame → event logic is
 * `frames.ts`, so the renderer's tests can share it without Node.
 */
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { SessionState } from "@shared/acp/types";

import { parseFrames, stateFromFrames, type Frame } from "./frames";

export { eventsFromFrames, parseFrames, stateFromFrames, type Frame } from "./frames";

export const FIXTURE_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "fixtures",
  "acp",
);

export function fixtureFiles(): string[] {
  return readdirSync(FIXTURE_DIR)
    .filter((name) => name.endsWith(".jsonl"))
    .map((name) => path.join(FIXTURE_DIR, name));
}

export function readFixture(file: string): Frame[] {
  return parseFrames(readFileSync(file, "utf8"));
}

/** Fold a fixture into a SessionState. */
export function stateFromFixture(file: string, agentId = path.basename(file, ".jsonl")): SessionState {
  return stateFromFrames(readFixture(file), agentId);
}
