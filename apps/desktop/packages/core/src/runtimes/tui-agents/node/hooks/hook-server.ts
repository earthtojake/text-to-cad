import crypto from 'node:crypto';
import http from 'node:http';
import type { Logger } from '@emdash/shared/logger';
import type { HookHandler, HookServerHandle } from './types';

export class TuiHookServer {
  private server: http.Server | null = null;
  private port = 0;
  private token = '';
  private starting: Promise<HookServerHandle> | null = null;

  constructor(
    private readonly handler: HookHandler,
    private readonly logger: Logger
  ) {}

  async ensureStarted(): Promise<HookServerHandle> {
    if (this.server && this.port > 0) return { port: this.port, token: this.token };
    if (this.starting) return this.starting;

    this.token = crypto.randomUUID();
    this.server = http.createServer((req, res) => {
      if (req.method !== 'POST' || req.url !== '/hook') {
        res.writeHead(404);
        res.end();
        return;
      }
      if (req.headers['x-emdash-token'] !== this.token) {
        this.logger.warn('TuiHookServer: rejected request with invalid token');
        res.writeHead(403);
        res.end();
        return;
      }

      let body = '';
      req.on('data', (chunk: Buffer) => {
        body += chunk.toString();
        if (body.length > 1_000_000) {
          req.destroy();
        }
      });

      req.on('end', () => {
        const ptyId = String(req.headers['x-emdash-pty-id'] || '');
        const type = String(req.headers['x-emdash-event-type'] || '');
        if (!ptyId || !type) {
          this.logger.warn('TuiHookServer: malformed request: missing ptyId or type headers');
          res.writeHead(400);
          res.end();
          return;
        }
        this.handler({ ptyId, type, body })
          .then(() => {
            res.writeHead(200);
            res.end();
          })
          .catch((error) => {
            this.logger.warn('TuiHookServer: handler error', { error: String(error) });
            res.writeHead(500);
            res.end();
          });
      });
    });

    this.starting = new Promise<HookServerHandle>((resolve, reject) => {
      this.server!.listen(0, '127.0.0.1', () => {
        const addr = this.server!.address();
        if (addr && typeof addr === 'object') {
          this.port = addr.port;
        }
        this.logger.info('TuiHookServer: started', { port: this.port });
        resolve({ port: this.port, token: this.token });
      });
      this.server!.on('error', (error) => {
        this.logger.error('TuiHookServer: failed to start', { error: String(error) });
        this.server = null;
        this.port = 0;
        this.starting = null;
        reject(error);
      });
    }).finally(() => {
      this.starting = null;
    });

    return this.starting;
  }

  stop(): void {
    if (this.server) {
      this.server.close();
      this.server = null;
      this.port = 0;
    }
  }
}
