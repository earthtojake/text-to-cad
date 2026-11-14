/** A newer version than the one running, as the server last knew it (`/api/v1/server`'s and a CAD app launch's `notice`). */
export interface UpdateNotice {
  /** The version this server runs. */
  version: string;
  /** The newer release the last version check saw. */
  latest: string;
}

/** Where the text-to-cad plugin, and the way to update it, are. */
export const REPOSITORY_URL = "https://github.com/earthtojake/text-to-cad";

/**
 * What the person sends their agent: the one text, in English in every locale, so it reads as the
 * plugin's skills do. The agent updates; nothing in a viewer does.
 */
export function updatePrompt(notice: Pick<UpdateNotice, "latest">): string {
  return `A new version of the text-to-cad plugin is available (v${notice.latest}). Update it from ${REPOSITORY_URL}`;
}

/** A notice as a server answers it, or null for anything else (none, or a shape this page does not read). */
export function readNotice(value: unknown): UpdateNotice | null {
  if (!value || typeof value !== "object") return null;
  const { version, latest } = value as Record<string, unknown>;
  return typeof version === "string" && typeof latest === "string" && version && latest ? { version, latest } : null;
}
