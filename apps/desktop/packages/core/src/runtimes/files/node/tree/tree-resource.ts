import path from 'node:path';
import { ok, type Result } from '@emdash/shared';
import {
  cell,
  revisionOf,
  snapshot,
  type Cell,
  type ExposedMutationContext,
  type Revision,
} from '@emdash/wire/state';
import { DEFAULT_TREE_EXCLUDE, ExclusionPolicy } from '#primitives/exclusion-policy/api';
import {
  parsePortableRelativePath,
  ROOT_RELATIVE_PATH,
  type PortableRelativePath,
} from '#primitives/path/api';
import {
  isExpandableFileEntry,
  type FileEntry,
  type FileTreeModel,
  type FsError,
  type filesContract,
} from '#runtimes/files/api';
import type { TreeIdentity } from '#runtimes/files/node/allocation/identity';
import type {
  AbsoluteChange,
  RootChange,
  RootResource,
} from '#runtimes/files/node/root/root-resource';
import { TreeDirectoryReader } from './directory-reader';
import { classifyTreeChanges } from './watch-classifier';

type TreeModel = typeof filesContract.tree.model;
type TreeMutationName = Extract<keyof TreeModel['mutations'], string>;
type TreeMutationContext<Name extends TreeMutationName> = ExposedMutationContext<TreeModel, Name>;
type ExpansionDepth = 1 | 2;

export type TreeResourceOptions = {
  identity: TreeIdentity;
  root: RootResource;
  onError?: (context: string, error: unknown) => void;
};

export class TreeResource {
  readonly identity: TreeIdentity;

  private readonly state: Cell<FileTreeModel>;
  private readonly exclusions: ExclusionPolicy;
  private readonly reader: TreeDirectoryReader;
  private readonly unsubscribeRoot: () => void;
  private readonly onError: (context: string, error: unknown) => void;
  private lane: Promise<void> = Promise.resolve();
  private resyncRun: Promise<void> | null = null;
  private trailingResyncRequested = false;
  private disposed = false;

  constructor(private readonly options: TreeResourceOptions) {
    this.identity = options.identity;
    this.exclusions = new ExclusionPolicy(options.identity.exclusions ?? DEFAULT_TREE_EXCLUDE);
    this.reader = new TreeDirectoryReader(options.root.paths, this.exclusions);
    this.onError = options.onError ?? (() => {});
    this.state = cell(initialTree(options.identity.root.root));
    this.unsubscribeRoot = options.root.subscribe((changes) => this.onRootChanges(changes));
  }

  source(): Cell<FileTreeModel> {
    this.assertActive();
    return this.state;
  }

  expand(context: TreeMutationContext<'expand'>): Promise<Result<void, FsError>> {
    return this.run(async () => {
      const result = await this.expandPath(
        context.input.path,
        context.mutationId,
        normalizeExpansionDepth(context.input.depth)
      );
      if (!result.success) return result;
      await context.observed('tree', result.data);
      return ok<void>();
    });
  }

  reveal(context: TreeMutationContext<'reveal'>): Promise<Result<void, FsError>> {
    return this.run(async () => {
      const validated = this.options.root.paths.resolveEntry(context.input.path);
      if (!validated.success) return validated;
      const target = validated.data.path;
      let revision = revisionOf(this.state);
      for (const ancestor of ancestorPaths(target)) {
        if (this.directoryChildrenLoaded(ancestor)) continue;
        const expanded = await this.expandPath(ancestor, context.mutationId);
        if (!expanded.success) return expanded;
        revision = expanded.data;
      }
      const targetEntry = this.current().entries[target];
      if (!targetEntry) {
        return { success: false, error: { type: 'not-found', path: target } };
      }
      if (isExpandableFileEntry(targetEntry)) {
        const depth = normalizeExpansionDepth(context.input.depth);
        if (depth === 1 && this.directoryChildrenLoaded(target)) {
          await context.observed('tree', revision);
          return ok<void>();
        }
        const expanded = await this.expandPath(target, context.mutationId, depth);
        if (!expanded.success) return expanded;
        revision = expanded.data;
      }
      await context.observed('tree', revision);
      return ok<void>();
    });
  }

  refresh(context: TreeMutationContext<'refresh'>): Promise<Result<void, FsError>> {
    return this.run(async () => {
      const revision = await this.resync(this.current(), [context.mutationId]);
      await context.observed('tree', revision);
      return ok<void>();
    });
  }

  /**
   * Reflects the files runtime's own successful stateless fs mutations into
   * this tree session at ack time (spec §3.4): converts host-absolute changes
   * to this root's relative paths and resolves once the tree state has been
   * reconciled. The fs watcher covers external changes only.
   */
  applyAbsoluteChanges(changes: AbsoluteChange[]): Promise<void> {
    if (this.disposed) return Promise.resolve();
    const rootChanges = changes.flatMap((change): RootChange[] => {
      const relative = this.options.root.paths.toRelative(change.absolutePath);
      return relative === null ? [] : [{ kind: change.kind, path: relative }];
    });
    const relevant = this.filterExcludedChanges(rootChanges);
    if (relevant.length === 0) return Promise.resolve();
    return this.run(() => this.reconcileChanges(relevant));
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.trailingResyncRequested = false;
    this.unsubscribeRoot();
    await this.lane;
  }

  private async expandPath(
    entryPath: PortableRelativePath,
    mutationId?: string,
    depth: ExpansionDepth = 1
  ): Promise<Result<Revision, FsError>> {
    const validated = this.options.root.paths.resolveEntry(entryPath);
    if (!validated.success) return validated;
    const model = this.current();
    const entry = model.entries[validated.data.path];
    if (!entry) return { success: false, error: { type: 'not-found', path: validated.data.path } };
    if (!isExpandableFileEntry(entry)) {
      return {
        success: false,
        error: { type: 'not-a-directory', path: validated.data.path },
      };
    }

    const children = await this.reader.readChildren(entry.path);
    if (!children.success) return children;
    reconcileDirectory(model, entry.path, children.data);
    if (depth > 1) {
      await this.expandLoadedChildren(model, entry.path);
    }
    return ok(
      this.state.set(model, {
        mutationIds: mutationId === undefined ? undefined : [mutationId],
      })
    );
  }

  private async expandLoadedChildren(
    model: FileTreeModel,
    entryPath: PortableRelativePath
  ): Promise<void> {
    const entry = model.entries[entryPath];
    if (!entry) return;
    for (const childPath of entry.children) {
      const child = model.entries[childPath];
      if (!child || !isExpandableFileEntry(child)) continue;
      const children = await this.reader.readChildren(child.path);
      if (!children.success) {
        this.onError(`files tree eager expand ${child.path}`, children.error);
        continue;
      }
      reconcileDirectory(model, child.path, children.data);
    }
  }

  private onRootChanges(changes: RootChange[]): void {
    const relevantChanges = this.filterExcludedChanges(changes);
    if (relevantChanges.length === 0) return;
    if (classifyTreeChanges(this.current(), relevantChanges).resync) {
      this.requestResync();
      return;
    }
    void this.run(() => this.reconcileChanges(relevantChanges)).catch((error: unknown) => {
      this.onError(`files tree watch ${this.identity.treeId}`, error);
    });
  }

  private filterExcludedChanges(changes: RootChange[]): RootChange[] {
    return changes.filter((change) => {
      if (change.kind === 'resync') return true;
      return !this.exclusions.excludes(change.path);
    });
  }

  private async reconcileChanges(changes: RootChange[]): Promise<void> {
    const current = this.current();
    const effects = classifyTreeChanges(current, changes);
    if (effects.resync) {
      await this.resync(current);
      return;
    }

    let changed = false;
    for (const parent of effects.loadedParents) {
      if (!current.entries[parent]?.childrenLoaded) continue;
      const children = await this.reader.readChildren(parent);
      if (!children.success) {
        this.onError(`files tree refresh ${parent}`, children.error);
        continue;
      }
      reconcileDirectory(current, parent, children.data);
      changed = true;
    }
    if (changed) this.state.set(current);
  }

  private async resync(
    previous: FileTreeModel,
    mutationIds?: readonly string[]
  ): Promise<Revision> {
    const loaded = Object.values(previous.entries)
      .filter((entry) => entry.childrenLoaded)
      .map((entry) => entry.path)
      .sort((left, right) => depth(left) - depth(right));
    const next = initialTree(this.identity.root.root);
    for (const entryPath of loaded) {
      const entry = next.entries[entryPath];
      if (!entry || !isExpandableFileEntry(entry)) continue;
      const children = await this.reader.readChildren(entryPath);
      if (!children.success) {
        this.onError(`files tree resync ${entryPath}`, children.error);
        continue;
      }
      reconcileDirectory(next, entryPath, children.data);
    }
    return this.state.set(next, {
      mutationIds: mutationIds ? [...mutationIds] : undefined,
    });
  }

  private requestResync(): void {
    if (this.disposed) return;
    if (this.resyncRun) {
      this.trailingResyncRequested = true;
      return;
    }

    const run = this.run(() => this.drainResyncs());
    this.resyncRun = run;
    void run.then(
      () => this.finishResyncRun(run),
      (error: unknown) => {
        this.onError(`files tree resync ${this.identity.treeId}`, error);
        this.finishResyncRun(run);
      }
    );
  }

  private async drainResyncs(): Promise<void> {
    do {
      this.trailingResyncRequested = false;
      await this.resync(this.current());
    } while (this.trailingResyncRequested && !this.disposed);
  }

  private finishResyncRun(run: Promise<void>): void {
    if (this.resyncRun !== run) return;
    this.resyncRun = null;
    if (!this.trailingResyncRequested || this.disposed) return;
    this.trailingResyncRequested = false;
    this.requestResync();
  }

  private current(): FileTreeModel {
    return structuredClone(snapshot(this.state).value);
  }

  private directoryChildrenLoaded(entryPath: PortableRelativePath): boolean {
    const entry = snapshot(this.state).value.entries[entryPath];
    return !!entry && isExpandableFileEntry(entry) && entry.childrenLoaded;
  }

  private run<T>(work: () => Promise<T>): Promise<T> {
    this.assertActive();
    const result = this.lane.then(work, work);
    this.lane = result.then(
      () => undefined,
      () => undefined
    );
    return result;
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('TreeResource is disposed');
  }
}

function initialTree(root: FileTreeModel['root']): FileTreeModel {
  const rootPath = root.segments.at(-1) ?? '';
  const name = path.basename(rootPath) || rootPath;
  return {
    root,
    entries: {
      '': {
        path: ROOT_RELATIVE_PATH,
        name,
        parentPath: null,
        kind: 'directory',
        childrenLoaded: false,
        children: [],
      },
    },
  };
}

function normalizeExpansionDepth(depth: number | undefined): ExpansionDepth {
  return depth === 2 ? 2 : 1;
}

function ancestorPaths(target: PortableRelativePath): PortableRelativePath[] {
  const segments = target === '' ? [] : target.split('/');
  const ancestors: PortableRelativePath[] = [];
  for (let index = 0; index < segments.length; index += 1) {
    if (index === 0) {
      ancestors.push(ROOT_RELATIVE_PATH);
      continue;
    }
    const ancestor = parsePortableRelativePath(segments.slice(0, index).join('/'));
    if (ancestor.success) ancestors.push(ancestor.data);
  }
  return ancestors;
}

function reconcileDirectory(
  model: FileTreeModel,
  parentPath: PortableRelativePath,
  incoming: FileEntry[]
): void {
  const parent = model.entries[parentPath];
  if (!parent) return;
  const incomingPaths = new Set(incoming.map((entry) => entry.path));
  for (const previousPath of parent.children) {
    if (!incomingPaths.has(previousPath)) removeSubtree(model, previousPath);
  }

  for (const entry of incoming) {
    const previous = model.entries[entry.path];
    if (previous && isExpandableFileEntry(previous) && isExpandableFileEntry(entry)) {
      entry.childrenLoaded = previous.childrenLoaded;
      entry.children = previous.children;
      entry.hasChildren = previous.hasChildren;
    } else if (previous) {
      removeDescendants(model, previous.path);
    }
    model.entries[entry.path] = entry;
  }
  parent.children = incoming.map((entry) => entry.path);
  parent.childrenLoaded = true;
  parent.hasChildren = incoming.length > 0;
}

function removeDescendants(model: FileTreeModel, parentPath: PortableRelativePath): void {
  const prefix = parentPath === '' ? '' : `${parentPath}/`;
  for (const entryPath of Object.keys(model.entries)) {
    if (entryPath !== parentPath && (prefix === '' || entryPath.startsWith(prefix))) {
      delete model.entries[entryPath];
    }
  }
}

function removeSubtree(model: FileTreeModel, entryPath: PortableRelativePath): void {
  removeDescendants(model, entryPath);
  delete model.entries[entryPath];
}

function depth(entryPath: PortableRelativePath): number {
  return entryPath === '' ? 0 : entryPath.split('/').length;
}
