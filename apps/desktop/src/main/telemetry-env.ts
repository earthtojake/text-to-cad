/**
 * The environment's say on telemetry, pure (`src/main/telemetry.ts` reads it
 * once at startup): `DO_NOT_TRACK`, the Console Do Not Track convention;
 * `TEXT_TO_CAD_TELEMETRY=0`, this app's own; `CI`, so a build farm never
 * counts as a person; and the test suites' `NODE_ENV=test`. The first that
 * says no is the answer, with its name, for Settings to print.
 */
export type EnvironmentOptOut = { variable: string; value: string };

const truthy = (value: string | undefined) =>
  value !== undefined && value !== "" && value !== "0" && value.toLowerCase() !== "false";

export function environmentOptOut(env: NodeJS.ProcessEnv = process.env): EnvironmentOptOut | null {
  if (truthy(env.DO_NOT_TRACK)) return { variable: "DO_NOT_TRACK", value: env.DO_NOT_TRACK ?? "" };
  if (env.TEXT_TO_CAD_TELEMETRY !== undefined && !truthy(env.TEXT_TO_CAD_TELEMETRY)) {
    return { variable: "TEXT_TO_CAD_TELEMETRY", value: env.TEXT_TO_CAD_TELEMETRY };
  }
  if (truthy(env.CI)) return { variable: "CI", value: env.CI ?? "" };
  if (env.NODE_ENV === "test") return { variable: "NODE_ENV", value: "test" };
  return null;
}
