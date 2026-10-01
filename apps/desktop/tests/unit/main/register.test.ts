import { beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

const native = vi.hoisted(() => ({ handle: vi.fn(), removeHandler: vi.fn() }));
vi.mock("electron", () => ({ BrowserWindow: {}, ipcMain: native }));

import { registerIpc } from "@main/ipc/register";
import { IPC_INVOKE_PREFIX, invoke } from "@shared/ipc/define";

const contract = {
  a: { ping: invoke(z.void(), z.string()) },
  top: invoke(z.void(), z.void()),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("registerIpc", () => {
  it("registers every channel when the handler tree matches the contract", () => {
    registerIpc(contract, { a: { ping: () => "pong" }, top: () => undefined });
    expect(native.handle.mock.calls.map(([channel]) => channel as string).sort()).toEqual([
      `${IPC_INVOKE_PREFIX}a.ping`,
      `${IPC_INVOKE_PREFIX}top`,
    ]);
  });

  it("refuses a channel with no handler", () => {
    expect(() => registerIpc(contract, { a: {}, top: () => undefined } as never)).toThrow(
      "no IPC handler for channel a.ping",
    );
  });

  it("refuses a handler with no declared channel, before registering anything", () => {
    const handlers = { a: { ping: () => "pong", stray: () => 1 }, top: () => undefined };
    expect(() => registerIpc(contract, handlers)).toThrow("no IPC channel for handler a.stray");
    expect(native.handle).not.toHaveBeenCalled();
  });

  it("refuses an undeclared branch and a handler below a leaf", () => {
    // Built outside the call, as a spread-in branch is: the type checker only
    // flags excess keys on an object literal.
    const undeclaredBranch = { a: { ping: () => "pong" }, top: () => undefined, extra: { x: () => 1 } };
    expect(() => registerIpc(contract, undeclaredBranch)).toThrow("no IPC channel for handler extra.x");
    const belowLeaf = { a: { ping: () => "pong", deeper: { x: () => 1 } }, top: () => undefined };
    expect(() => registerIpc(contract, belowLeaf)).toThrow("no IPC channel for handler a.deeper.x");
  });
});
