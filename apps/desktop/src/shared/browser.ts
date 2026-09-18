import { z } from "zod";

export const BrowserTargetSchema = z.object({
  tabId: z.string(), projectId: z.string(), root: z.string(), url: z.string(),
  generation: z.number().int().nonnegative(), title: z.string(), loading: z.boolean(), canGoBack: z.boolean(), canGoForward: z.boolean(),
  visible: z.boolean(),
  logs: z.array(z.object({ level: z.enum(["log", "warn", "error"]), message: z.string() })),
});
export type BrowserTarget = z.infer<typeof BrowserTargetSchema>;
export const BrowserAtSchema = z.object({ tabId: z.string().min(1) });
export const BrowserInputSchema = z.discriminatedUnion("action", [
  z.object({ action: z.literal("click"), backendNodeId: z.number().int().positive() }),
  z.object({ action: z.literal("point"), x: z.number().nonnegative(), y: z.number().nonnegative() }),
  z.object({ action: z.literal("type"), text: z.string().max(100_000), backendNodeId: z.number().int().positive().optional(), clear: z.boolean().optional() }),
  z.object({ action: z.literal("key"), key: z.enum(["Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]), modifiers: z.number().int().min(0).max(15).optional() }),
  z.object({ action: z.literal("scroll"), x: z.number().nonnegative(), y: z.number().nonnegative(), deltaX: z.number().default(0), deltaY: z.number() }),
]);
export type BrowserInput = z.infer<typeof BrowserInputSchema>;
export const browserMethodSchemas = {
  list: z.object({}),
  open: z.object({ tabId: z.string().min(1).optional(), url: z.string().nullable().optional() }),
  state: BrowserAtSchema,
  screenshot: BrowserAtSchema,
  navigate: BrowserAtSchema.extend({ url: z.string().optional(), direction: z.enum(["back", "forward", "reload", "stop"]).optional() }),
  input: BrowserAtSchema.extend({ input: BrowserInputSchema }),
  close: BrowserAtSchema,
} as const;
export type BrowserMethod = keyof typeof browserMethodSchemas;
