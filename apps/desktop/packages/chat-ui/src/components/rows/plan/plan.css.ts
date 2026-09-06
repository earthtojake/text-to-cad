import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────
// Only the tokens used by PlanList layout (Plan.tsx). The card shell, header,
// and height tokens have moved to the CollapsibleCard primitive.

export type PlanStyleVars = {
  padX: number;
  padY: number;
  iconBox: number;
  iconGap: number;
  entryGap: number;
};

export const planVars = createVariableThemeContract<PlanStyleVars>({
  padX: null,
  padY: null,
  iconBox: null,
  iconGap: null,
  entryGap: null,
});
