import {
  hostRefEquals,
  hostRefFromParts,
  hostRefKey,
  sshConnectionIdOf,
  type HostRef,
} from '@emdash/core/primitives/host/api';

export type WorkspaceIdentity = Readonly<{
  workspaceId: string;
  host: HostRef;
  path: string;
  projectId: string;
}>;

export type WorkspaceHostStorage = Readonly<{
  type: 'local' | 'project-ssh';
  location: 'local' | 'remote';
  sshConnectionId: string | null;
}>;

export type WorkspaceIdentityRow = Readonly<{
  workspaceId: string;
  type: 'local' | 'project-ssh';
  location: 'local' | 'remote' | null;
  sshConnectionId: string | null;
  path: string;
  projectId: string;
}>;

export interface WorkspaceIdentitySource {
  findById(workspaceId: string): Promise<WorkspaceIdentityRow | null>;
  findRepositoryForProject(projectId: string): Promise<WorkspaceIdentityRow | null>;
  findByPath(path: string): Promise<readonly WorkspaceIdentityRow[]>;
}

export class WorkspaceIdentityService {
  private readonly byId = new Map<string, WorkspaceIdentity>();
  private readonly byProjectId = new Map<string, WorkspaceIdentity>();
  private readonly byPath = new Map<string, WorkspaceIdentity>();

  constructor(private readonly source: WorkspaceIdentitySource) {}

  async resolve(workspaceId: string): Promise<WorkspaceIdentity | null> {
    const cached = this.byId.get(workspaceId);
    if (cached) return cached;
    const row = await this.source.findById(workspaceId);
    const identity = row ? identityFromRow(row) : null;
    if (identity) this.cache(identity);
    return identity;
  }

  async resolveProject(projectId: string): Promise<WorkspaceIdentity | null> {
    const cached = this.byProjectId.get(projectId);
    if (cached) return cached;
    const row = await this.source.findRepositoryForProject(projectId);
    const identity = row ? identityFromRow(row) : null;
    if (identity) {
      this.byProjectId.set(projectId, identity);
      this.cache(identity);
    }
    return identity;
  }

  async findByPath(path: string, host?: HostRef): Promise<WorkspaceIdentity | null> {
    if (host) {
      const cached = this.byPath.get(pathKey(host, path));
      if (cached) return cached;
    }

    const rows = await this.source.findByPath(path);
    const identities = rows
      .map(identityFromRow)
      .filter((identity): identity is WorkspaceIdentity => identity !== null);
    for (const identity of identities) this.cache(identity);
    return selectIdentity(identities, host);
  }

  invalidate(workspaceId: string): void {
    const identity = this.byId.get(workspaceId);
    this.byId.delete(workspaceId);
    if (identity) {
      this.byProjectId.delete(identity.projectId);
      this.byPath.delete(pathKey(identity.host, identity.path));
    }
  }

  clear(): void {
    this.byId.clear();
    this.byProjectId.clear();
    this.byPath.clear();
  }

  private cache(identity: WorkspaceIdentity): void {
    this.byId.set(identity.workspaceId, identity);
    this.byPath.set(pathKey(identity.host, identity.path), identity);
  }
}

function identityFromRow(row: WorkspaceIdentityRow): WorkspaceIdentity | null {
  return {
    workspaceId: row.workspaceId,
    host: hostRefFromParts(row.location, row.sshConnectionId),
    path: row.path,
    projectId: row.projectId,
  };
}

export function workspaceHostStorage(host: HostRef): WorkspaceHostStorage {
  const sshConnectionId = sshConnectionIdOf(host);
  return sshConnectionId
    ? { type: 'project-ssh', location: 'remote', sshConnectionId }
    : { type: 'local', location: 'local', sshConnectionId: null };
}

function selectIdentity(
  identities: readonly WorkspaceIdentity[],
  host?: HostRef
): WorkspaceIdentity | null {
  const matches = host
    ? identities.filter((identity) => hostRefEquals(identity.host, host))
    : identities;
  return [...matches].sort(compareIdentities)[0] ?? null;
}

function compareIdentities(left: WorkspaceIdentity, right: WorkspaceIdentity): number {
  return (
    compareStrings(hostRefKey(left.host), hostRefKey(right.host)) ||
    compareStrings(left.workspaceId, right.workspaceId)
  );
}

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function pathKey(host: HostRef, path: string): string {
  return `${hostRefKey(host)}:${path}`;
}
