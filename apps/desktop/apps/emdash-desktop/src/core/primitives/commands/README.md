# Commands

Commands are portable, schema-backed action definitions. Definitions contain
static metadata and optional keybindings; view scopes provide their runtime
availability and implementation.

```ts
const createBranchCommand = defineCommand({
  id: 'task.createBranch',
  title: 'Create Branch',
  category: 'Git',
  input: z.object({ branchName: z.string(), baseRef: z.string() }),
});
```

Command input describes arguments supplied for one invocation. Scope params
describe the context in which the command runs; callers must not duplicate
scope context in command input.
