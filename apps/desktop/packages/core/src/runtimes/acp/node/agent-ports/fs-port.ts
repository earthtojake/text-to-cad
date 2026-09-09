import type {
  ReadTextFileRequest,
  ReadTextFileResponse,
  WriteTextFileRequest,
  WriteTextFileResponse,
} from '@agentclientprotocol/sdk';
import type { AcpProcessHost } from '#runtimes/acp/api/transport';
import { readTextFile, writeTextFile } from './fs-text';

type FsHost = Pick<AcpProcessHost, 'fs'>;

export class FsPort {
  constructor(private readonly host: FsHost) {}

  async readTextFile(params: ReadTextFileRequest): Promise<ReadTextFileResponse> {
    const content = await readTextFile(this.host.fs, params.path);
    return { content };
  }

  async writeTextFile(params: WriteTextFileRequest): Promise<WriteTextFileResponse> {
    await writeTextFile(this.host.fs, params.path, params.content);
    return {};
  }
}
