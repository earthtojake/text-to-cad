import type {
  Client,
  CompleteElicitationNotification,
  CreateElicitationRequest,
  CreateElicitationResponse,
  CreateTerminalRequest,
  CreateTerminalResponse,
  KillTerminalRequest,
  KillTerminalResponse,
  ReadTextFileRequest,
  ReadTextFileResponse,
  ReleaseTerminalRequest,
  ReleaseTerminalResponse,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionNotification,
  TerminalOutputRequest,
  TerminalOutputResponse,
  WaitForTerminalExitRequest,
  WaitForTerminalExitResponse,
  WriteTextFileRequest,
  WriteTextFileResponse,
} from '@agentclientprotocol/sdk';
import type { NormalizedEvent } from '#runtimes/acp/api';
import type { AcpConnectionContext } from '#runtimes/acp/node/connection/source';
import type { FsPort } from './fs-port';
import type { TerminalPort } from './terminal-port';
import { redactToolOutputImageData } from './tool-output-redaction';

export interface InboundRouter {
  onSessionUpdate(
    connection: AcpConnectionContext,
    params: SessionNotification,
    event: NormalizedEvent
  ): Promise<void>;
  onPermissionRequest(
    connection: AcpConnectionContext,
    params: RequestPermissionRequest
  ): Promise<RequestPermissionResponse>;
  onCreateTerminal(
    connection: AcpConnectionContext,
    params: CreateTerminalRequest
  ): Promise<CreateTerminalResponse>;
  onElicitation(
    connection: AcpConnectionContext,
    params: CreateElicitationRequest
  ): Promise<CreateElicitationResponse>;
}

export interface AgentPorts {
  fs: FsPort;
  terminals: TerminalPort;
}

export function buildAgentClient(
  connection: AcpConnectionContext,
  router: InboundRouter,
  ports: AgentPorts
): Client {
  return {
    sessionUpdate: async (params: SessionNotification): Promise<void> => {
      // Enrichment hooks can promote rawOutput into persisted normalized text.
      // Normalize a byte-free copy while attachment ingress receives the
      // original notification through params.
      const normalized = connection.normalize(redactToolOutputImageData(params.update));
      await router.onSessionUpdate(connection, params, normalized);
    },

    requestPermission: (params: RequestPermissionRequest): Promise<RequestPermissionResponse> => {
      return router.onPermissionRequest(connection, params);
    },

    readTextFile: async (params: ReadTextFileRequest): Promise<ReadTextFileResponse> => {
      return ports.fs.readTextFile(params);
    },

    writeTextFile: async (params: WriteTextFileRequest): Promise<WriteTextFileResponse> => {
      return ports.fs.writeTextFile(params);
    },

    createTerminal: async (params: CreateTerminalRequest): Promise<CreateTerminalResponse> => {
      return router.onCreateTerminal(connection, params);
    },

    unstable_createElicitation: (
      params: CreateElicitationRequest
    ): Promise<CreateElicitationResponse> => {
      return router.onElicitation(connection, params);
    },

    unstable_completeElicitation: async (
      _params: CompleteElicitationNotification
    ): Promise<void> => {
      // URL elicitations are never created here (only form mode is advertised),
      // so there is nothing to complete.
    },

    terminalOutput: async (params: TerminalOutputRequest): Promise<TerminalOutputResponse> => {
      return ports.terminals.terminalOutput(params);
    },

    waitForTerminalExit: async (
      params: WaitForTerminalExitRequest
    ): Promise<WaitForTerminalExitResponse> => {
      return ports.terminals.waitForTerminalExit(params);
    },

    killTerminal: async (params: KillTerminalRequest): Promise<KillTerminalResponse> => {
      return ports.terminals.killTerminal(params);
    },

    releaseTerminal: async (params: ReleaseTerminalRequest): Promise<ReleaseTerminalResponse> => {
      return ports.terminals.releaseTerminal(params);
    },
  };
}
