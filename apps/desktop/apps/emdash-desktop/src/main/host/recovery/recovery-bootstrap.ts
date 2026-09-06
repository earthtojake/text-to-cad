/**
 * Pure types and HTML-injection utility for the recovery window. This module has
 * no imports so it is trivially testable and cannot contribute to a boot failure.
 */

export type RecoveryState = {
  errorMessage: string;
  version: string;
  updaterActive: boolean;
  updateStatus: string;
  availableVersion: string | undefined;
  downloadProgress: number | undefined;
  error: string | undefined;
};

/**
 * Replace the `__RECOVERY_BOOTSTRAP__` sentinel in the HTML template with the
 * serialised bootstrap payload. The `</script>` sequence is escaped so that a
 * crafted error message cannot close the inline script block early.
 */
export function injectBootstrap(html: string, bootstrap: RecoveryState): string {
  const sentinel = '__RECOVERY_BOOTSTRAP__';
  if (!html.includes(sentinel)) {
    throw new Error('Recovery HTML is missing its bootstrap sentinel');
  }
  const json = JSON.stringify(bootstrap, (_key, value: unknown) =>
    value === undefined ? null : value
  ).replace(/<\/script>/gi, '<\\/script>');
  return html.replace(sentinel, json);
}
