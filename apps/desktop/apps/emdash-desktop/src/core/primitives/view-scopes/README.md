# View Scopes

View scopes define hierarchical command contexts independently of navigation.
A scope definition declares its validated params, command set, activation mode,
and optional traits. A runtime implementation binds each declared command to
availability and execution behavior.

```ts
const taskViewScope = defineViewScope({
  id: 'view.task',
  params: z.object({ projectId: z.string(), taskId: z.string() }),
  commands: [archiveTaskCommand],
  activation: 'logical',
  key: ({ taskId }) => taskId,
});
```

Scope params identify the context, such as the current task. Command input
contains invocation-specific arguments, such as a new branch name. A command
binding closes over scope params and receives validated command input.

Scope command implementations belong to live scope instances. Logical scopes
are activated by navigation, while focus scopes are selected by delegated DOM
focus events.

Capturing overlays are an independent activation layer. While an overlay is
open, the runtime keeps the current logical scope and underlying focus scope
unchanged, but resolves commands against the top overlay (or a focused scope
inside it). Activate a layer with `scopes.activateCapture(instance)` and dispose
the returned handle when it closes. The identity-keyed order supports removal
in any order; reactivating a layer moves it to the top, while stale disposers are
ignored. Detachment or disposal also removes the layer. Below-capture queries
derive the layer beneath the top capture, then the current ambient path, without
reading a historical snapshot. Closing the final layer therefore reveals the
current underlying focus or logical scope.
