export function nextTerminalName(names: string[]): string {
  const taken = new Set(
    names
      .map((n) => /^Terminal (\d+)$/.exec(n)?.[1])
      .filter(Boolean)
      .map(Number)
  );
  let n = 1;
  while (taken.has(n)) n++;
  return `Terminal ${n}`;
}
