/** The variable a release's own build names its version in. */
export declare const RELEASE_ENV: "TEXT_TO_CAD_RELEASE";

export interface BuildIdOptions {
  /** The version the build is of (its app's package version, stamped from VERSION). */
  version: string;
  env?: Record<string, string | undefined>;
  /** A directory of the checkout the build is made from. */
  cwd?: string;
  now?: Date;
}

/**
 * This build's id: "" for the release's own build of `version`, else the checkout's commit
 * (`b80844940`, or `b80844940-dirty`), else the time of the build (UTC, `20261007153012`).
 */
export declare function buildId(options: BuildIdOptions): string;
