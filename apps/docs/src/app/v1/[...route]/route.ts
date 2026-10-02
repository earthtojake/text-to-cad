// api.texttocad.dev/v1/*: CAD's anonymous analytics (src/lib/analytics). The domain is this
// project's too, and every /v1 path is the handler's, which routes it.
import { handle } from "@/lib/analytics/handler.mjs";
import { postgresStore } from "@/lib/analytics/postgres.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

let store: ReturnType<typeof postgresStore> | undefined;
const serve = (request: Request) =>
  handle(request, (store ??= postgresStore(process.env.DATABASE_URL)), {
    cronSecret: process.env.CRON_SECRET,
    // Names only: what /v1/health reports missing, so a deploy without them fails its check.
    missing: [!process.env.DATABASE_URL && "DATABASE_URL", !process.env.CRON_SECRET && "CRON_SECRET"].filter(Boolean) as string[],
    // Where Vercel's edge places the request, from its IP address: counted into the countries'
    // totals, never kept with a batch.
    country: request.headers.get("x-vercel-ip-country"),
  });

export const GET = serve;
export const POST = serve;
