# @emdash/core

`@emdash/core` owns Emdash's shared domain APIs and the host-scoped runtime and
service implementations used by the desktop app and workspace-server. It is the
package for code that must be shared across hosts without putting that ownership
in an app package.

Core keeps domain definitions close to their implementations, but separates
portable APIs from platform-specific code through explicit subpath exports. A
consumer should be able to tell from the import path whether it is importing
shared vocabulary, a Node implementation, or a browser implementation.

## Package Structure

Source modules live under `src/` and are grouped by module type:

```text
src/
  primitives/
  services/
  runtimes/
  workspace-server/
```

### Primitives

`primitives/` contains reusable vocabulary and small infrastructure that does
not own a product domain. Primitives may define schemas, value objects,
deterministic helpers, and narrowly scoped policies.

Examples include host-aware paths, host identity, skill schemas, MCP schemas,
agent environment helpers, plugin file-system ports, and concurrency helpers.

Primitives may depend on other primitives, but they must not depend on services
or runtimes.

### Services

`services/` contains focused capabilities that can be injected into runtimes or
host composition code. Services may own bounded resources, expose ports, provide
Node or browser implementations, or define Wire contracts for smaller shared
capabilities.

Examples include execution contexts, PTY management, filesystem watching, host
dependency detection, and agent plugin support.

Services may depend on primitives and explicitly lower-level services. They must
not depend on runtimes.

### Runtimes

`runtimes/` contains host-scoped composition roots for larger product domains.
A runtime typically implements a public Wire contract, owns domain state and
resources, and coordinates injected services and primitives.

Current runtime domains include:

- `acp`
- `agent-config`
- `files`
- `git`
- `tui-agents`
- `workspace`

Runtimes are peers. A runtime must not import another runtime; cross-runtime
composition belongs in the desktop host, workspace-server host, or another
explicit composition root.

### Workspace Server

`workspace-server/` is a special composition root, not a fourth general module
type. It owns workspace-server protocol versions, shared host schemas, aggregate
Wire contracts, and host-owned composition helpers. It may compose runtime APIs,
services, and primitives.

## Surface Conventions

Each module is split by platform surface:

```text
<module-type>/<module-name>/
  api/
  node/
  browser/
```

Modules only add the surfaces they need.

### `api`

`api/` is the portable public surface. It may contain Wire contracts, serialized
models, DTOs, Zod schemas, public ports, typed errors, and pure helpers needed by
consumers.

`api/` must not import `node/` or `browser/`, use platform modules, spawn
processes, or own background work.

### `node`

`node/` contains Node-specific implementations: runtime and service factories,
Wire components, Wire controllers, procedure implementations, filesystem/Git/PTY/subprocess
behavior, and resource allocation. App-owned worker entry files adapt components to process hosting
with `runWireComponentWorker()`.

### `browser`

`browser/` contains browser-specific implementations of portable APIs. Browser
surfaces may import `api/` and other `browser/` surfaces, but must not import
Node code.

## Subpath Exports

Public imports must select an explicit module type, module name, and surface:

```text
@emdash/core/<module-type>/<module-name>/<surface>
```

Examples:

```ts
import { gitContract } from '@emdash/core/runtimes/git/api';
import { GitRuntime, gitComponent } from '@emdash/core/runtimes/git/node';

import type { IWatchService } from '@emdash/core/services/fs-watch/api';
import { createNativeWatchService } from '@emdash/core/services/fs-watch/node';

import { parseAbsolute, type HostAbsolutePath } from '@emdash/core/primitives/path/api';
```

Avoid ambiguous module-root exports such as `@emdash/core/runtimes/git`.
Consumers should choose `api`, `node`, or `browser` explicitly.

Inside `packages/core/src`, package subpath imports (the `imports` field in
`package.json`) are used for cross-directory imports:

```ts
import { parseAbsolute } from '#primitives/path/api';
import { createNativeWatchService } from '#services/fs-watch/node';
import { gitContract } from '#runtimes/git/api';
```

Those subpath imports are internal to Core source and resolve through Core's
own `package.json`, so consumers need no extra configuration. Code outside
Core should import through public `@emdash/core/...` subpaths.

## More Details

See [`../../agents/architecture/core-modules.md`](../../agents/architecture/core-modules.md)
for the full architecture notes, dependency rules, and migration guidance.
