// Vercel entry. vercel.json rewrites every route the static output does not answer to this
// function. A build keeps running after its response in waitUntil, inside maxDuration
// (800 s); dist/ is served as static output and objects come from R2.
import { waitUntil } from '@vercel/functions';
import type { Hono } from 'hono';
import { buildApp } from '../server/app.ts';
import { depsFromEnv } from '../server/deps.ts';

let app: Promise<Hono> | undefined;

function getApp(): Promise<Hono> {
  app ??= depsFromEnv(process.env, { background: (task) => waitUntil(task) }).then((deps) => buildApp(deps).app);
  app.catch(() => {
    app = undefined; // a failed start (database unreachable) is retried on the next request
  });
  return app;
}

const handler = async (request: Request) => (await getApp()).fetch(request);

export const GET = handler;
export const HEAD = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;
