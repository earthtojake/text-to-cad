import { z } from 'zod';

export const SESSION_PLAN_ID = 'session-plan';

export const planEntryStatusSchema = z.enum(['pending', 'in_progress', 'completed']);
export type PlanEntryStatus = z.infer<typeof planEntryStatusSchema>;

export const planEntryPrioritySchema = z.enum(['high', 'medium', 'low']);
export type PlanEntryPriority = z.infer<typeof planEntryPrioritySchema>;

export const planEntrySchema = z.object({
  /** Reducer-synthesized id; ACP plan updates do not provide stable entry ids. */
  id: z.string(),
  /** Provider plan-entry text/step label, not a structured Emdash task. */
  content: z.string(),
  status: planEntryStatusSchema,
  priority: planEntryPrioritySchema,
});
export type PlanEntry = z.infer<typeof planEntrySchema>;

/** Raw provider plan entry before the reducer assigns a stable session-local id. */
export const planEntryInputSchema = planEntrySchema.omit({ id: true });
export type PlanEntryInput = z.infer<typeof planEntryInputSchema>;

export const planStateSchema = z.object({
  /** Stable id of the session-scoped plan slice referenced by transcript markers. */
  id: z.string(),
  /** Latest full plan snapshot; providers replace the whole list on each update. */
  entries: z.array(planEntrySchema),
  /** Epoch ms when the reducer last received a plan update. */
  updatedAt: z.number(),
});
export type PlanState = z.infer<typeof planStateSchema>;
