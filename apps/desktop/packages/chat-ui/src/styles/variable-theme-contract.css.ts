import { createThemeContract } from '@vanilla-extract/css';

export function createVariableThemeContract<TDef extends Record<string, number>>(tokens: {
  [K in keyof TDef]: null;
}) {
  return createThemeContract(tokens);
}
