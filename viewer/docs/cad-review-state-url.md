# CAD Review State URL Payload

This document defines the state that should be shared when a CAD Explorer user copies a review URL. The goal is to reproduce the reviewed model context without copying raw browser session storage.

## Goal

A copied review URL should allow another viewer session to open the same CAD file and restore the review-relevant 3D context: camera, selected entities, visibility, active assembly context, and clipping.

The URL payload is not intended to mirror every transient UI state. Local persistence such as sessionStorage remains responsible for private, transparent restoration on the same browser.

## Priority model

- **P0 required**: missing this breaks review-state reproduction.
- **P1 recommended**: improves semantic fidelity and diagnostics, but the core 3D review can still open without it.
- **P2 optional**: useful for polish or format-specific workflows, but should not dominate the URL payload by default.
- **Do not share**: transient or local-only state.

## State inventory

| Area | Parameters | Priority | Why it matters | URL placement |
| --- | --- | --- | --- | --- |
| File identity | `file.key`, `file.cadPath` | P0 | Selects the model the review state applies to. All camera, selection, and visibility IDs are meaningless on the wrong file. | Keep `file` readable in the URL; include both values in `view`. |
| File metadata | `file.renderFormat` | P1 | Helps interpret format-specific state and validate restore behavior. | `view.file.renderFormat` |
| File validation | content/topology/render signatures | P1 | Detects stale links or same-name/different-content models before applying IDs incorrectly. | Future `view.file.signatures` |
| Camera | `position`, `target`, `up` | P0 | The minimum 3D viewpoint. | `view.camera.perspective` |
| Camera metadata | `modelKey`, `sceneScaleMode`, `coordinateSystem` | P0 | The same numeric camera can render differently if model binding, scale mode, or coordinate system differ. | `view.camera.perspective` |
| Projection | projection type, zoom/FOV | P1/future P0 | Needed once the viewer supports orthographic/perspective switching or explicit projection settings. | Future `view.camera.projection` |
| Scene mode | `explorerMode` | P2/future | The 0.2 workspace does not expose a durable scene-mode state yet. Add this only when the viewer has a concrete mode to read and restore. | Future `view.scene.explorerMode` |
| Scene mapping | `selectedRenderPartIdByAssemblyPartId` | P0 | Restores the render mesh that backs an assembly-part selection. | `view.scene.selectedRenderPartIdByAssemblyPartId` |
| Scene path | active assembly path / expanded assembly context | P0/P1 | Required when assembly expansion also represents the active review context; otherwise it is sidebar context. | `view.assembly.expandedAssemblyPartIds` |
| Selection | `selectedPartIds`, `selectedReferenceIds` | P0 | Defines what the review is pointing at. | `view.selection` |
| Stable selection fallback | `cadRefs` | P1 | Internal IDs are fast, but cadRef tokens are better fallbacks across minor topology/ID changes. | `view.selection.cadRefs` |
| Whole-model selection | selected whole-entry cadRef token | P1 | Distinguishes whole-model selection from no entity selection. | Future `view.selection.selectedWholeEntryCadRefToken` |
| Visibility | `hiddenPartIds` | P0 | Hidden geometry changes the actual reviewed view. | `view.visibility.hiddenPartIds` (currently normalized from legacy `assembly.hiddenPartIds`) |
| Visibility focus/isolate | focused/isolated part IDs and mode | P0/P1 | If the viewer is showing an isolated subset, the copied state must reproduce that subset. | Future `view.visibility` |
| Clip | complete clip settings object | P0 | Clipping changes the visible geometry and review target. Avoid reducing it to `axis,plane` only. | `view.clip` (currently normalized from legacy `view.clipSettings`) |
| Tree context | expanded STEP tree nodes | P1 | Helps recipients understand where the selected entity lives in the sidebar. | `view.assembly.expandedTreeNodeIds` |
| Review workspace | active tool/tab, selected sheet | P1 | Opens the recipient near the same review affordance, e.g. References. | Future `view.workspace` |
| Appearance | display mode, edges/wireframe | P1 if present | Can affect whether CAD review details are visible. | Future `view.appearance` |
| Theme | theme preset/settings | P2 | Affects visual appearance, but is user preference and currently localStorage-oriented. | Do not force by default. |
| Panel layout | sidebar/tool open, widths | P2 | Mostly device/user preference; widths are especially screen-dependent. | Avoid or keep minimal. |
| STEP parametric state | parameters, module enabled, animation pose | Format-specific P0/P1 | A parametric STEP file can represent a different model if parameters differ. | Future `view.format.stepModule` |
| URDF state | joint values | Format-specific P0 | Robot posture is part of the reviewed model. | Future `view.format.urdf` |
| DXF state | thickness and bend settings | Format-specific P0 | Sheet-metal geometry depends on these settings. | Future `view.format.dxf` |
| Hover | hovered part/ref | Do not share | Hover is transient and should not be part of a durable review link. | Exclude |
| Runtime state | loading/error/status | Do not share | Not review state. | Exclude |
| Browser persistence | raw sessionStorage/localStorage keys | Do not share | Local restore mechanism, not cross-user share state. | Exclude |

## P0 URL payload implemented now

The P0 payload should be a compact review-state document encoded into the `view` query parameter:

```text
?file=<fileKey>&view=<encoded-review-state>
```

The P0 document shape is:

```js
{
  schema: "cad-review-state",
  version: 1,
  file: {
    key: string,
    cadPath: string,
    renderFormat: string
  },
  camera: {
    perspective: {
      position: [number, number, number],
      target: [number, number, number],
      up: [number, number, number],
      modelKey: string,
      sceneScaleMode: string,
      coordinateSystem: string
    }
  },
  scene: {
    selectedRenderPartIdByAssemblyPartId: Record<string, string>
  },
  selection: {
    selectedPartIds: string[],
    selectedReferenceIds: string[],
    cadRefs: string[]
  },
  visibility: {
    hiddenPartIds: string[]
  },
  clip: object | null,
  assembly: {
    expandedAssemblyPartIds: string[]
  }
}
```

Legacy URL payloads using `cad-explorer-view-state` remain accepted for URL compatibility, but copied URLs should prefer the explicit `cad-review-state` P0 schema.

## Non-goals for the P0 pass

- Do not encode raw sessionStorage.
- Do not restore hover/tooltips/loading/error state.
- Do not force the recipient's theme or pixel layout.
- Do not solve format-specific STEP/URDF/DXF pose state yet; those belong to follow-up passes.
