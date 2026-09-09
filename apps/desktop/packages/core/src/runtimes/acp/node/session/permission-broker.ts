import type { RequestPermissionResponse } from '@agentclientprotocol/sdk';
import type { AcpPermissionRequest } from '#runtimes/acp/api';

type PermissionResolver = (response: RequestPermissionResponse) => void;

export class PermissionBroker {
  private readonly resolvers = new Map<string, PermissionResolver>();

  request(request: AcpPermissionRequest): Promise<RequestPermissionResponse> {
    return new Promise<RequestPermissionResponse>((resolve) => {
      this.resolvers.set(request.requestId, resolve);
    });
  }

  settle(requestId: string, optionId: string): boolean {
    const resolver = this.resolvers.get(requestId);
    if (!resolver) return false;
    this.resolvers.delete(requestId);
    resolver({ outcome: { outcome: 'selected', optionId } });
    return true;
  }

  cancel(requestId: string): boolean {
    const resolver = this.resolvers.get(requestId);
    if (!resolver) return false;
    this.resolvers.delete(requestId);
    resolver({ outcome: { outcome: 'cancelled' } });
    return true;
  }

  drain(requests: readonly AcpPermissionRequest[]): void {
    for (const request of requests) {
      this.cancel(request.requestId);
    }
  }
}
