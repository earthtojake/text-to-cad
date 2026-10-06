// What compute costs, and the caps on it the server enforces itself (law 5):
//   per job      a timeout and a vCPU count;
//   per person   vCPU-seconds per UTC day (a job starts only with time left today, and is
//                given no more than what is left);
//   everyone     a daily budget in dollars at Vercel Sandbox rates.
// A job RESERVES its worst case before it starts, with conditional updates the database
// applies atomically, and SETTLES what it really used when it ends.
import type { Limits } from './config.ts';
import type { Clock } from './clock.ts';
import { iso, nextUtcMidnight, utcDay } from './clock.ts';
import type { Queryable } from './db/index.ts';
import { CloudError } from './errors.ts';

export interface Reservation {
  day: string;
  vcpuSeconds: number;
  usd: number;
}

export interface Usage {
  vcpuSeconds: number;
  usd: number;
  wallMs: number;
  activeCpuMs?: number;
}

/** Dollars for `vcpus` provisioned for `wallMs`, with active CPU when the provider reports it. */
export function costUsd(limits: Limits, vcpus: number, wallMs: number, activeCpuMs?: number): number {
  const hours = wallMs / 3_600_000;
  const cpuHours = activeCpuMs !== undefined ? activeCpuMs / 3_600_000 : vcpus * hours;
  return cpuHours * limits.cpuHourUsd + vcpus * limits.memoryGbPerVcpu * hours * limits.gbHourUsd;
}

export function usageOf(limits: Limits, vcpus: number, wallMs: number, activeCpuMs?: number): Usage {
  return { vcpuSeconds: (vcpus * wallMs) / 1000, usd: costUsd(limits, vcpus, wallMs, activeCpuMs), wallMs, activeCpuMs };
}

function resetsAt(clock: Clock) {
  return iso(nextUtcMidnight(clock.now()));
}

/**
 * Reserve a job's worst case. Returns the timeout it may run for: the job's own limit,
 * shortened to what is left of the person's day. Throws a 429 naming the cap otherwise.
 */
export async function reserve(
  db: Queryable,
  limits: Limits,
  clock: Clock,
  userId: string,
  job: { vcpus: number; timeoutSeconds: number },
): Promise<{ reservation: Reservation; timeoutSeconds: number }> {
  const day = utcDay(clock.now());
  await db.query('insert into usage_daily (user_id, day) values ($1, $2) on conflict do nothing', [userId, day]);
  await db.query('insert into budget_daily (day) values ($1) on conflict do nothing', [day]);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const { rows } = await db.query<{ used: number; reserved: number }>(
      'select vcpu_seconds::float8 as used, reserved_vcpu_seconds::float8 as reserved from usage_daily where user_id = $1 and day = $2',
      [userId, day],
    );
    const left = limits.userDailyVcpuSeconds - (rows[0]?.used ?? 0) - (rows[0]?.reserved ?? 0);
    const timeoutSeconds = Math.min(job.timeoutSeconds, Math.floor(left / job.vcpus));
    if (timeoutSeconds < limits.minJobSeconds) {
      throw new CloudError(429, 'daily_limit', `You have used today's compute: ${limits.userDailyVcpuSeconds} vCPU-seconds per person per day (${Math.max(0, Math.floor(left))} left, and a job needs at least ${limits.minJobSeconds * job.vcpus}). It resets at ${resetsAt(clock)}.`, { cap: 'user_daily_vcpu_seconds', limit: limits.userDailyVcpuSeconds, resetsAt: resetsAt(clock) });
    }
    const vcpuSeconds = timeoutSeconds * job.vcpus;
    const claimed = await db.query(
      `update usage_daily set reserved_vcpu_seconds = reserved_vcpu_seconds + $3
       where user_id = $1 and day = $2 and vcpu_seconds + reserved_vcpu_seconds + $3 <= $4`,
      [userId, day, vcpuSeconds, limits.userDailyVcpuSeconds],
    );
    if (claimed.rowCount === 0) continue; // another job of theirs claimed time first: re-read
    const usd = costUsd(limits, job.vcpus, timeoutSeconds * 1000);
    const budget = await db.query(
      `update budget_daily set reserved_usd = reserved_usd + $2
       where day = $1 and spent_usd + reserved_usd + $2 <= $3`,
      [day, usd, limits.dailyBudgetUsd],
    );
    if (budget.rowCount === 0) {
      await release(db, userId, { day, vcpuSeconds, usd: 0 });
      throw new CloudError(429, 'budget_exhausted', `The service has spent its compute budget for today (US$${limits.dailyBudgetUsd} across everyone). It resets at ${resetsAt(clock)}.`, { cap: 'daily_budget_usd', resetsAt: resetsAt(clock) });
    }
    return { reservation: { day, vcpuSeconds, usd }, timeoutSeconds };
  }
  throw new CloudError(429, 'daily_limit', 'Too many jobs started at once; try again.', { cap: 'user_daily_vcpu_seconds' });
}

async function release(db: Queryable, userId: string, reservation: Reservation) {
  await db.query(
    'update usage_daily set reserved_vcpu_seconds = greatest(0, reserved_vcpu_seconds - $3) where user_id = $1 and day = $2',
    [userId, reservation.day, reservation.vcpuSeconds],
  );
  if (reservation.usd > 0) {
    await db.query('update budget_daily set reserved_usd = greatest(0, reserved_usd - $2) where day = $1', [reservation.day, reservation.usd]);
  }
}

/** Replace a reservation with what the job used (on the day it was reserved). */
export async function settle(db: Queryable, userId: string, reservation: Reservation, used: Usage | null, counts: { builds?: number; jobs?: number } = {}) {
  await db.query(
    `update usage_daily set
       reserved_vcpu_seconds = greatest(0, reserved_vcpu_seconds - $3),
       vcpu_seconds = vcpu_seconds + $4,
       builds = builds + $5,
       jobs = jobs + $6
     where user_id = $1 and day = $2`,
    [userId, reservation.day, reservation.vcpuSeconds, used?.vcpuSeconds ?? 0, counts.builds ?? 0, counts.jobs ?? 0],
  );
  await db.query(
    `update budget_daily set reserved_usd = greatest(0, reserved_usd - $2), spent_usd = spent_usd + $3 where day = $1`,
    [reservation.day, reservation.usd, used?.usd ?? 0],
  );
}

export async function usageToday(db: Queryable, limits: Limits, clock: Clock, userId: string) {
  const day = utcDay(clock.now());
  const { rows } = await db.query<{ used: number; reserved: number; builds: number; jobs: number }>(
    'select vcpu_seconds::float8 as used, reserved_vcpu_seconds::float8 as reserved, builds, jobs from usage_daily where user_id = $1 and day = $2',
    [userId, day],
  );
  const row = rows[0] ?? { used: 0, reserved: 0, builds: 0, jobs: 0 };
  return {
    day,
    vcpuSeconds: Math.round(row.used),
    reservedVcpuSeconds: Math.round(row.reserved),
    limitVcpuSeconds: limits.userDailyVcpuSeconds,
    builds: row.builds,
    jobs: row.jobs,
    resetsAt: resetsAt(clock),
  };
}
