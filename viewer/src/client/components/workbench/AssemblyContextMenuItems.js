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
  hideAllLabel = "Hide all instances",
  showVisibility = true,
  visibilityDisabled = false,
  showHideAll = false,
  showExpandCollapse = false,
  expandSelectedDisabled = true,
  collapseSelectedDisabled = true,
  expandAllDisabled = true,
  collapseAllDisabled = true,
  onCopyReference,
  onSelect,
  onIsolate,
  onExitAllIsolate,
  onHideOther,
  onHideAll,
  onToggleVisibility,
  onExpandSelected,
  onCollapseSelected,
  onExpandAll,
  onCollapseAll
}) {
  const normalizedActionCount = Math.max(Number(actionCount) || 1, 1);
  const multiAction = normalizedActionCount > 1;
  const selectLabel = selected
    ? multiAction ? "Deselect selected" : "Deselect"
    : "Select";
  const isolateLabel = isolated
    ? "Exit isolate"
    : multiAction ? "Isolate selected" : "Isolate";
  const visibilityLabel = hidden
    ? "Reveal"
    : multiAction ? "Hide selected" : "Hide";

  return (
    <>
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
          <AssemblyContextMenuItemLabel>Hide other instances</AssemblyContextMenuItemLabel>
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
      {showExpandCollapse ? (
        <>
          <Separator />
          <Item
            className={itemClassName}
            disabled={expandSelectedDisabled}
            onSelect={onExpandSelected}
          >
            <AssemblyContextMenuItemLabel>Expand selected</AssemblyContextMenuItemLabel>
          </Item>
          <Item
            className={itemClassName}
            disabled={collapseSelectedDisabled}
            onSelect={onCollapseSelected}
          >
            <AssemblyContextMenuItemLabel>Collapse selected</AssemblyContextMenuItemLabel>
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
