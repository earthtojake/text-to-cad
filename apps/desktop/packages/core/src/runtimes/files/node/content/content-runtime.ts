import type { Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { expose } from '@emdash/wire/state';
import { filesContract, type FilesContract } from '#runtimes/files/api';
import type { FilesAllocationGraph } from '#runtimes/files/node/allocation/allocation-graph';
import { expectedFsError } from '#runtimes/files/node/api/errors';
import type { ContentResource } from './content-resource';

type ContentModel = FilesContract['content'];

export class FileContentRuntime {
  readonly model: LeasedLiveModelProvider<ContentModel>;

  private readonly hosts = new Map<string, LeasedLiveModelProvider<ContentModel>>();

  constructor(private readonly allocations: FilesAllocationGraph) {
    this.model = this.modelHost(filesContract.content);
  }

  modelHost(contract: ContentModel = filesContract.content): LeasedLiveModelProvider<ContentModel> {
    const existing = this.hosts.get(contract.id);
    if (existing) return existing;
    const host = expose(
      contract,
      {
        content: (key, scope) => this.contentState(key, scope),
      },
      {
        mutations: {
          write: (context) =>
            this.run(context.key, (resource) => resource.write(context), expectedFsError),
        },
      }
    );
    this.hosts.set(contract.id, host);
    return host;
  }

  async dispose(): Promise<void> {
    await Promise.all([...this.hosts.values()].map((host) => host.dispose()));
    this.hosts.clear();
  }

  private async contentState(
    key: Parameters<FilesAllocationGraph['acquireContent']>[0],
    scope: Scope
  ) {
    const lease = this.allocations.acquireContent(key);
    scope.add(() => lease.release());
    const resource = await lease.ready();
    return resource.state();
  }

  private async run<T, E>(
    key: Parameters<FilesAllocationGraph['acquireContent']>[0],
    work: (resource: ContentResource) => Promise<Result<T, E>>,
    mapError: (error: unknown) => E | undefined
  ): Promise<Result<T, E>> {
    const lease = this.allocations.acquireContent(key);
    try {
      return await work(await lease.ready());
    } catch (error) {
      const expected = mapError(error);
      if (expected !== undefined) return { success: false, error: expected };
      throw error;
    } finally {
      await lease.release();
    }
  }
}
