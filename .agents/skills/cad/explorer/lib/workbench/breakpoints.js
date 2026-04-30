export const CAD_WORKSPACE_BREAKPOINT_PX = 768;

export const CAD_WORKSPACE_DESKTOP_MEDIA_QUERY = `(min-width: ${CAD_WORKSPACE_BREAKPOINT_PX}px)`;
export const CAD_WORKSPACE_MOBILE_MEDIA_QUERY = `(max-width: ${CAD_WORKSPACE_BREAKPOINT_PX - 1}px)`;

export function isCadWorkspaceDesktopViewport(width) {
  const numericWidth = Number(width);
  return Number.isFinite(numericWidth) && numericWidth >= CAD_WORKSPACE_BREAKPOINT_PX;
}
