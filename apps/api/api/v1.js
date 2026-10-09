// api.texttocad.dev/v1/*: cadgen's version feed and its telemetry, forwarded to PostHog (src/). vercel.json
// rewrites every /v1 path to this one function, which keeps the path it was asked for, and the handler
// routes it.
import { handle } from '../src/handler.mjs';
import { missingSettings, posthogStore, settingsOf } from '../src/posthog.mjs';
import { versions } from '../src/versions.mjs';

let store;
const serve = request => handle(request, (store ??= posthogStore(settingsOf(process.env))), {
  // Names only: what /v1/health reports missing, so a deploy without them fails its check.
  missing: missingSettings(process.env),
  // Where Vercel's edge places the request, from its IP address: passed on with the batch's events as a
  // country, and the address itself kept nowhere.
  country: request.headers.get('x-vercel-ip-country'),
  versions,
});

export const GET = serve;
export const POST = serve;
