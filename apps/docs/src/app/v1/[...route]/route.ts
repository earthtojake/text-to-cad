// api.texttocad.dev/v1/*: cadgen's version feed and its telemetry, forwarded to PostHog (src/lib/api). The
// domain is this project's too, and every /v1 path is the handler's, which routes it.
import { handle } from "@/lib/api/handler.mjs";
import { missingSettings, posthogStore, settingsOf } from "@/lib/api/posthog.mjs";
import { versions } from "@/lib/api/versions.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

let store: ReturnType<typeof posthogStore> | undefined;
const serve = (request: Request) =>
  handle(request, (store ??= posthogStore(settingsOf(process.env))), {
    // Names only: what /v1/health reports missing, so a deploy without them fails its check.
    missing: missingSettings(process.env),
    // Where Vercel's edge places the request, from its IP address: passed on with the batch's events as a
    // country, and the address itself kept nowhere.
    country: request.headers.get("x-vercel-ip-country"),
    versions,
  });

export const GET = serve;
export const POST = serve;
