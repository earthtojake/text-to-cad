// The part menu: what can be done to one node of the model, wherever it was
// asked for. The camera is NOT here — framing lives in the zoom menu beside the
// Inspector's readout, so no item of this menu can contradict the active tool.
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

/**
 * That same menu, from the descriptor the workspace builds for a node
 * (`assemblyNodeMenu` in `CadFileView`). The viewport's dropdown and the model
 * tree's context menu are one list over one node, so this is the only place the
 * descriptor is turned into items and the two cannot drift apart.
 *
 * `actions` holds the handlers, each called with the descriptor.
 * `disabled` disables every item at once, for a tree whose selection is blocked.
 */
export function AssemblyPartMenuItems({ menu, Item, Separator, itemClassName = "text-xs", disabled = false, actions = {} }) {
  const run = (action) => () => action?.(menu);
  const off = (flag) => disabled || flag === true;
  return (
    <AssemblyContextMenuItems
      Item={Item}
      Separator={Separator}
      itemClassName={itemClassName}
      selected={menu.selected === true}
      isolated={menu.focused === true}
      hidden={menu.hidden === true}
      actionCount={menu.actionCount}
      onAddToPrompt={actions.onAddToPrompt ? run(actions.onAddToPrompt) : undefined}
      copyReferenceDisabled={disabled || !String(menu.copyText || "").trim()}
      selectDisabled={off(menu.selectDisabled)}
      showIsolate={menu.showIsolate !== false}
      isolateDisabled={off(menu.isolateDisabled)}
      showExitAllIsolate={menu.showExitAllIsolate === true}
      exitAllIsolateDisabled={off(menu.exitAllIsolateDisabled)}
      showHideOther={menu.showHideOther !== false}
      hideOtherDisabled={off(menu.hideOtherDisabled)}
      showVisibility={menu.showVisibility !== false}
      visibilityDisabled={off(menu.visibilityDisabled)}
      showHideAll={menu.showHideAll === true}
      hideAllDisabled={off(menu.hideAllDisabled)}
      hideAllLabel={String(menu.hideAllLabel || "").trim() || "Show all"}
      showExpandCollapse={menu.showExpandCollapse === true}
      expandSelectedDisabled={disabled || menu.expandSelectedDisabled !== false}
      collapseSelectedDisabled={disabled || menu.collapseSelectedDisabled !== false}
      expandAllDisabled={disabled || menu.expandAllDisabled !== false}
      collapseAllDisabled={disabled || menu.collapseAllDisabled !== false}
      onCopyReference={run(actions.onCopyReference)}
      onSelect={run(actions.onSelect)}
      onIsolate={run(actions.onIsolate)}
      onExitAllIsolate={run(actions.onExitAllIsolate)}
      onHideOther={run(actions.onHideOther)}
      onHideAll={run(actions.onHideAll)}
      onToggleVisibility={run(menu.hidden === true ? actions.onReveal : actions.onHide)}
      onExpandSelected={run(actions.onExpandSelected)}
      onCollapseSelected={run(actions.onCollapseSelected)}
      onExpandAll={run(actions.onExpandAll)}
      onCollapseAll={run(actions.onCollapseAll)}
    />
  );
}
