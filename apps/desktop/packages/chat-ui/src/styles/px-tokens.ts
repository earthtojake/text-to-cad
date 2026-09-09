export function pxTokens<V extends Record<string, number>>(vars: V): { [K in keyof V]: string } {
  return Object.fromEntries(Object.entries(vars).map(([k, n]) => [k, `${n}px`])) as {
    [K in keyof V]: string;
  };
}
