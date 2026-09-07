function AssemblyContextMenuItemLabel({ children }) {
  return <span className="min-w-0 truncate">{children}</span>;
}

export default function AssemblyContextMenuItems({
  Item,
  Separator,
  itemClassName = "text-xs",
  selected = false,
  isolated = false,
  hidden = false,
  actionCount = 1,
  copyReferenceDisabled = false,
  selectDisabled = false,
  showIsolate = true,
  isolateDisabled = false,
  showExitAllIsolate = false,
  exitAllIsolateDisabled = false,
  showHideOther = true,
  hideOtherDisabled = false,
  hideAllDisabled = true,
  hideAllLabel = "Show all",
  showVisibility = true,
  visibilityDisabled = false,
  showCameraActions = false,
  resetZoomDisabled = false,
  zoomToFitDisabled = false,
  showHideAll = false,
  showExpandCollapse = false,
  expandSelectedDisabled = true,
  collapseSelectedDisabled = true,
  expandAllDisabled = true,
  collapseAllDisabled = true,
  onAddToPrompt,
  onCopyReference,
  onSelect,
  onIsolate,
  onExitAllIsolate,
  onHideOther,
  onHideAll,
  onToggleVisibility,
  onResetZoom,
  onZoomToFit,
  onExpandSelected,
  onCollapseSelected,
  onExpandAll,
  onCollapseAll
}) {
  const selectLabel = selected ? "Deselect" : "Select";
  const isolateLabel = isolated
    ? "Exit isolate"
    : "Isolate";
  const visibilityLabel = hidden
    ? "Reveal"
    : "Hide";

  return (
    <>
      {onAddToPrompt ? (
        <Item className={itemClassName} disabled={copyReferenceDisabled} onSelect={onAddToPrompt}>
          <AssemblyContextMenuItemLabel>Add to prompt</AssemblyContextMenuItemLabel>
        </Item>
      ) : null}
      <Item
        className={itemClassName}
        disabled={copyReferenceDisabled}
        onSelect={onCopyReference}
      >
        <AssemblyContextMenuItemLabel>Copy Reference</AssemblyContextMenuItemLabel>
      </Item>
      <Separator />
      <Item
        className={itemClassName}
        disabled={selectDisabled}
        onSelect={onSelect}
      >
        <AssemblyContextMenuItemLabel>{selectLabel}</AssemblyContextMenuItemLabel>
      </Item>
      {showIsolate ? (
        <Item
          className={itemClassName}
          disabled={isolateDisabled}
          onSelect={onIsolate}
        >
          <AssemblyContextMenuItemLabel>{isolateLabel}</AssemblyContextMenuItemLabel>
        </Item>
      ) : null}
      {showExitAllIsolate ? (
        <Item
          className={itemClassName}
          disabled={exitAllIsolateDisabled}
          onSelect={onExitAllIsolate}
        >
          <AssemblyContextMenuItemLabel>Exit all isolates</AssemblyContextMenuItemLabel>
        </Item>
      ) : null}
      {showHideOther || showHideAll || showVisibility ? <Separator /> : null}
      {showHideOther ? (
        <Item
          className={itemClassName}
          disabled={hideOtherDisabled}
          onSelect={onHideOther}
        >
          <AssemblyContextMenuItemLabel>Hide others</AssemblyContextMenuItemLabel>
        </Item>
      ) : null}
      {showHideAll ? (
        <Item
          className={itemClassName}
          disabled={hideAllDisabled}
          onSelect={onHideAll}
        >
          <AssemblyContextMenuItemLabel>{hideAllLabel}</AssemblyContextMenuItemLabel>
        </Item>
      ) : null}
      {showVisibility ? (
        <Item
          className={itemClassName}
          disabled={visibilityDisabled}
          onSelect={onToggleVisibility}
        >
          <AssemblyContextMenuItemLabel>{visibilityLabel}</AssemblyContextMenuItemLabel>
        </Item>
      ) : null}
      {showCameraActions ? (
        <>
          <Separator />
          <Item
            className={itemClassName}
            disabled={resetZoomDisabled}
            onSelect={onResetZoom}
          >
            <AssemblyContextMenuItemLabel>Reset Zoom</AssemblyContextMenuItemLabel>
          </Item>
          <Item
            className={itemClassName}
            disabled={zoomToFitDisabled}
            onSelect={onZoomToFit}
          >
            <AssemblyContextMenuItemLabel>Zoom To Fit</AssemblyContextMenuItemLabel>
          </Item>
        </>
      ) : null}
      {showExpandCollapse ? (
        <>
          <Separator />
          <Item
            className={itemClassName}
            disabled={expandSelectedDisabled}
            onSelect={onExpandSelected}
          >
            <AssemblyContextMenuItemLabel>Expand</AssemblyContextMenuItemLabel>
          </Item>
          <Item
            className={itemClassName}
            disabled={collapseSelectedDisabled}
            onSelect={onCollapseSelected}
          >
            <AssemblyContextMenuItemLabel>Collapse</AssemblyContextMenuItemLabel>
          </Item>
          <Item
            className={itemClassName}
            disabled={expandAllDisabled}
            onSelect={onExpandAll}
          >
            <AssemblyContextMenuItemLabel>Expand all</AssemblyContextMenuItemLabel>
          </Item>
          <Item
            className={itemClassName}
            disabled={collapseAllDisabled}
            onSelect={onCollapseAll}
          >
            <AssemblyContextMenuItemLabel>Collapse all</AssemblyContextMenuItemLabel>
          </Item>
        </>
      ) : null}
    </>
  );
}
