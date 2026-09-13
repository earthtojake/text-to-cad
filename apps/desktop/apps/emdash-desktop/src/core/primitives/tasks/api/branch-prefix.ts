/** Strip leading/trailing path separators so `${prefix}/${branch}` stays a valid ref. */
export function normalizeBranchPrefix(prefix: string): string {
  return prefix.trim().replace(/^\/+|\/+$/g, '');
}
