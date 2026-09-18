import { z } from "zod";
import { BrowserTargetSchema, BrowserInputSchema } from "../browser";
import { invoke } from "./define";
const Scope = z.object({ sessionId: z.string().min(1), projectId: z.string().min(1), root: z.string().nullable().optional() });
const At = Scope.extend({ tabId: z.string().min(1) });
export const browserIpc = {
  browser: {
    ensure: invoke(At.extend({ url: z.string().nullable().optional() }), BrowserTargetSchema),
    metadata: invoke(At, BrowserTargetSchema),
    navigate: invoke(At.extend({ url: z.string().optional(), direction: z.enum(["back", "forward", "reload", "stop"]).optional() }), BrowserTargetSchema),
    input: invoke(At.extend({ input: BrowserInputSchema }), BrowserTargetSchema),
    present: invoke(At.extend({ lease: z.string().min(1), bounds: z.object({ x: z.number().nonnegative(), y: z.number().nonnegative(), width: z.number().positive(), height: z.number().positive() }).nullable() }), z.void()),
    close: invoke(At, z.void()),
    clearConsole: invoke(At, z.void()),
    capture: invoke(At.extend({ url: z.string().url(), generation: z.number().int().nonnegative(), kind: z.enum(["selection", "screenshot"]) }), z.object({ base64: z.string(), mimeType: z.string(), url: z.string(), generation: z.number() })),
  },
};
