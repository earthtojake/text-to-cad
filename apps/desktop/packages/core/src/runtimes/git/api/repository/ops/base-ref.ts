export function computeBaseRef(
  baseRef?: string | null,
  remote?: string | null,
  branch?: string | null
): string {
  const remoteName = (() => {
    const trimmed = (remote ?? '').trim();
    if (!trimmed) return '';
    if (/^[A-Za-z0-9._-]+$/.test(trimmed) && !trimmed.includes('://')) return trimmed;
    return 'origin';
  })();

  const normalize = (value?: string | null): string | undefined => {
    if (!value) return undefined;
    const trimmed = value.trim();
    if (!trimmed || trimmed.includes('://')) return undefined;

    if (trimmed.includes('/')) {
      const [head, ...rest] = trimmed.split('/');
      const branchPart = rest.join('/').replace(/^\/+/, '');
      if (head && branchPart) return `${head}/${branchPart}`;
      if (!head && branchPart) {
        return remoteName ? `${remoteName}/${branchPart}` : branchPart;
      }
      return undefined;
    }

    const suffix = trimmed.startsWith('/') ? trimmed.slice(1) : trimmed;
    return remoteName ? `${remoteName}/${suffix}` : suffix;
  };

  const defaultBranch = remoteName ? `${remoteName}/main` : 'main';
  return normalize(baseRef) ?? normalize(branch) ?? defaultBranch;
}
