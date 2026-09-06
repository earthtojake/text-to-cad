# The workspaceHost runtime retires; the registry is the workspace plane

The v8 wire cleanup removes the `workspaceHost` contract and its runtime worker entirely
(13 host runtime contracts → 12). The registry established by ADR 0005 was already the
sole owner of workspace lifecycle; workspaceHost had shrunk to a residue of one observation
and three dead or single-caller verbs. This ADR records the collapse — it fulfills rather
than revises ADR 0005/0006, whose models are unchanged.

Disposition of the surface:

- `measureUsage` — the git-aware disk observation (total bytes plus reclaimable git-ignored
  artifact bytes) moves to `workspaceRegistry.measureUsage({ workspaceId })`, id-keyed like
  the registry's other per-workspace observations.
- `initializeWorkspace` — cut. Its one consumer, the automations runtime, rewires to
  `workspaceRegistry.createWorkspace` (idempotent, designed for registering existing paths,
  worktrees auto-adopting their parent repository) followed by `activateWorkspace`. Side
  benefit: automation workspaces become registry-visible at run start instead of waiting
  for adoption scans.
- `runWorkspaceScript` and `notices` — cut as dead. Production scripts flow through registry
  activation and `terminals.runWorkflow`; the UI reads notices from the registry records
  overlay.

The workspace-host worker leaves both worker graphs (the desktop gateway entries and the
workspace-server daemon's), and the `workspace-host-actions` mirror service is deleted. Its
session-cleanup code, which registry deactivation uses, survives as imported library code
under the registry runtime — an implementation detail with no wire surface. The aggregate
`workspaceWireContract` loses the `workspaceHost` key.

## Consequences

- One fewer required supervised child process per host; the automations worker gains an
  explicit dependency on the workspace-registry runtime in both graphs.
- Workspace observations, lifecycle, and now usage measurement live on a single contract;
  there is no second "host" plane to keep consistent with the registry.
- Re-adding any cut verb later is an additive minor bump under the v8 protocol.
