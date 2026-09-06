/**
 * The contract machinery: how a channel is declared and what can be derived
 * from a declaration. No channels live here — `../ipc.ts` assembles those, and
 * the per-branch modules beside this one declare them.
 *
 * Its own module because the branches import `invoke` and `../ipc.ts` imports
 * the branches. With the helpers in `../ipc.ts` that is a cycle, and a cycle
 * whose failure mode is a temporal-dead-zone error at import time: the branch
 * module runs first and calls `invoke` before the `const` it closes over
 * exists. One module that depends on nothing in this directory is the fix.
 */
import type { z } from "zod";

const INVOKE = Symbol.for("hardcore.ipc.invoke");

/** One request/response channel. */
export type InvokeDef<Req extends z.ZodType = z.ZodType, Res extends z.ZodType = z.ZodType> = {
  readonly [INVOKE]: true;
  readonly request: Req;
  readonly response: Res;
};

/** A branch of the contract tree. */
export type IpcNode = InvokeDef | { readonly [key: string]: IpcNode };

/**
 * Declare a request/response channel.
 *
 * `z.void()` on either side is the honest way to say "no argument" / "no
 * answer"; it makes the generated client method callable with no arguments.
 */
export function invoke<Req extends z.ZodType, Res extends z.ZodType>(
  request: Req,
  response: Res,
): InvokeDef<Req, Res> {
  return { [INVOKE]: true, request, response };
}

/** Narrow a contract node to a leaf. */
export function isInvokeDef(node: unknown): node is InvokeDef {
  return typeof node === "object" && node !== null && INVOKE in node;
}

/**
 * Declare the contract. Identity at run time — its whole job is to pin the
 * literal type of the tree so `HardcoreApi` and `IpcHandlers` can be derived
 * from it.
 */
export function defineIpc<const T extends IpcNode>(contract: T): T {
  return contract;
}

/** Walk a contract tree, yielding `["a.b.c", def]` for every leaf. */
export function ipcChannels(node: IpcNode, prefix: string[] = []): [string, InvokeDef][] {
  if (isInvokeDef(node)) {
    return [[prefix.join("."), node]];
  }
  return Object.entries(node).flatMap(([key, child]) => ipcChannels(child, [...prefix, key]));
}

/** The renderer-facing shape of a contract tree. */
export type IpcClient<T> =
  T extends InvokeDef<infer Req, infer Res>
    ? (request: z.input<Req>) => Promise<z.output<Res>>
    : { readonly [K in keyof T]: IpcClient<T[K]> };

/**
 * The main-process shape of a contract tree. Handlers receive the *parsed*
 * request and may return either the parsed or the input form of the response —
 * whatever they return is validated before it crosses the bridge.
 */
export type IpcHandlers<T, Ctx = unknown> =
  T extends InvokeDef<infer Req, infer Res>
    ? (request: z.output<Req>, ctx: Ctx) => z.input<Res> | Promise<z.input<Res>>
    : { readonly [K in keyof T]: IpcHandlers<T[K], Ctx> };

/** The channel prefix every IPC name shares, so nothing else can squat one. */
export const IPC_INVOKE_PREFIX = "hardcore:";
export const IPC_EVENT_PREFIX = "hardcore!";
