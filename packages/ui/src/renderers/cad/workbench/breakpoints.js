export const CAD_WORKSPACE_MOBILE_BREAKPOINT_PX = 520;
export const CAD_WORKSPACE_DESKTOP_BREAKPOINT_PX = CAD_WORKSPACE_MOBILE_BREAKPOINT_PX;
export const CAD_WORKSPACE_FILE_VIEWER_DEFAULT_OPEN_BREAKPOINT_PX = 1024;
export const CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX = 1024;
export const CAD_WORKSPACE_BREAKPOINT_PX = CAD_WORKSPACE_DESKTOP_BREAKPOINT_PX;

export const CAD_WORKSPACE_DESKTOP_MEDIA_QUERY = `(min-width: ${CAD_WORKSPACE_MOBILE_BREAKPOINT_PX}px)`;
export const CAD_WORKSPACE_MOBILE_MEDIA_QUERY = `(max-width: ${CAD_WORKSPACE_MOBILE_BREAKPOINT_PX - 1}px)`;

export const CAD_WORKSPACE_LAYOUT_MODE = Object.freeze({
  DESKTOP: "desktop",
  MOBILE: "mobile"
});

export function getCadWorkspaceLayoutMode(width) {
  const numericWidth = Number(width);
  if (!Number.isFinite(numericWidth)) {
    return CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  }
  return numericWidth >= CAD_WORKSPACE_DESKTOP_BREAKPOINT_PX
    ? CAD_WORKSPACE_LAYOUT_MODE.DESKTOP
    : CAD_WORKSPACE_LAYOUT_MODE.MOBILE;
}

export function isCadWorkspaceMobileViewport(width) {
  return getCadWorkspaceLayoutMode(width) === CAD_WORKSPACE_LAYOUT_MODE.MOBILE;
}

export function isCadWorkspaceDesktopViewport(width) {
  return getCadWorkspaceLayoutMode(width) === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
}

export function isCadWorkspaceCompactFileSheetViewport(width) {
  const numericWidth = Number(width);
  if (!Number.isFinite(numericWidth)) {
    return false;
  }
  return (
    numericWidth >= CAD_WORKSPACE_MOBILE_BREAKPOINT_PX &&
    numericWidth < CAD_WORKSPACE_FILE_SHEET_COMPACT_BREAKPOINT_PX
  );
}

export function shouldCadWorkspaceDefaultFileViewerOpen(width, { hasSelectedFile = true } = {}) {
  return false;
}

export function shouldCadWorkspaceDefaultFileSettingsOpen(width) {
  return isCadWorkspaceDesktopViewport(width);
}
