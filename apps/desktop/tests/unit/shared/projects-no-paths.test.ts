/**
 * AGENTS.md: projects are derived directory groups, and no channel takes a
 * directory by name — a folder becomes a project only through a chooser main
 * opened, the sample main copied, or a session that already records it. So
 * no request under `projects.*` has a `path` or `directory` field, at any
 * depth.
 */
import type { z } from "zod";
import { expect, it } from "vitest";

import { ipcChannels } from "@shared/ipc/define";
import { ipcContract } from "@shared/ipc";

const FORBIDDEN = new Set(["path", "directory"]);

type Internals = { _zod: { def: Record<string, unknown> & { type: string; shape?: Record<string, unknown> } } };
const isSchema = (value: unknown): value is Internals =>
  typeof value === "object" && value !== null && "_zod" in value;

/** Every object key reachable from a schema: shapes, wrappers, unions, arrays, pipes, lazies. */
function keysOf(schema: z.ZodType, seen = new Set<unknown>()): string[] {
  if (seen.has(schema)) return [];
  seen.add(schema);
  const def = (schema as unknown as Internals)._zod.def;
  const keys = def.type === "object" && def.shape ? Object.keys(def.shape) : [];
  const children: unknown[] = [];
  const collect = (value: unknown) => {
    if (isSchema(value)) children.push(value);
    else if (Array.isArray(value)) value.forEach(collect);
    else if (typeof value === "function" && def.type === "lazy") collect((value as () => unknown)());
    else if (typeof value === "object" && value !== null && !(value instanceof RegExp)) Object.values(value).forEach(collect);
  };
  Object.values(def).forEach(collect);
  return [...keys, ...children.flatMap((child) => keysOf(child as z.ZodType, seen))];
}

it("finds the projects channels it guards", () => {
  expect(ipcChannels(ipcContract.projects, ["projects"]).map(([name]) => name)).toContain("projects.add");
});

it("takes no path or directory in any projects.* request", () => {
  const offenders = ipcChannels(ipcContract.projects, ["projects"]).flatMap(([name, def]) =>
    keysOf(def.request)
      .filter((key) => FORBIDDEN.has(key))
      .map((key) => `${name}: ${key}`),
  );
  expect(offenders.join("\n"), "projects.* requests that name a directory").toBe("");
});
