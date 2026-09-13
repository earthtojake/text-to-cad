export function getBranchTooltipText(
  headDisplay: string | null,
  headKind: 'branch' | 'detached' | 'unborn'
): string {
  if (headKind === 'detached') return `Detached HEAD at ${headDisplay ?? 'unknown'}`;
  if (headKind === 'unborn') return 'Create an initial commit first';
  return headDisplay ?? '';
}

export function getPublishTooltipText({
  isPublishing,
  headDisplay,
  headKind,
  shouldOfferAddRemote,
}: {
  isPublishing: boolean;
  headDisplay: string | null;
  headKind: 'branch' | 'detached' | 'unborn';
  shouldOfferAddRemote: boolean;
}): string {
  if (isPublishing) return 'Publishing...';
  if (headKind === 'detached') return 'Cannot publish: HEAD is detached';
  if (headKind === 'unborn') return 'Create an initial commit first';
  if (!headDisplay) return 'Create an initial commit first';
  if (shouldOfferAddRemote) return 'Create or link a remote, then publish this branch';
  return 'Publish branch';
}
