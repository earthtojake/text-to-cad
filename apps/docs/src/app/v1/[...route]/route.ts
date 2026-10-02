// api.texttocad.dev/v1/*: CAD's anonymous analytics (src/lib/analytics). The domain is this
// project's too, and every /v1 path is the handler's, which routes it.
import { handle } from "@/lib/analytics/handler.mjs";
import { postgresStore } from "@/lib/analytics/postgres.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

let store: ReturnType<typeof postgresStore> | undefined;
const serve = (request: Request) =>
  handle(request, (store ??= postgresStore(process.env.DATABASE_URL)), { cronSecret: process.env.CRON_SECRET });

export const GET = serve;
export const POST = serve;
export const DELETE = serve;
