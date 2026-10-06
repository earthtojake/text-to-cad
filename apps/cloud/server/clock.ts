export interface Clock {
  now(): number;
}

export const systemClock: Clock = { now: () => Date.now() };

export const iso = (ms: number) => new Date(ms).toISOString();

/** The UTC calendar day a moment falls in, `YYYY-MM-DD`: the key every daily cap uses. */
export const utcDay = (ms: number) => iso(ms).slice(0, 10);

/** When the daily caps reset after `ms`: the next 00:00 UTC. */
export function nextUtcMidnight(ms: number): number {
  const date = new Date(ms);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + 1);
}

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
