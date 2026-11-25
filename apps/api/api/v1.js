// api.texttocad.dev/v1/*: text-to-cad's version feed and its telemetry, forwarded to PostHog (src/). vercel.json
// rewrites every /v1 path to this one function, which keeps the path it was asked for, and the handler
// routes it.
import { handle } from '../src/handler.mjs';
import { clientOf, INSTALL_LIMIT, rateLimiter } from '../src/limit.mjs';
import { missingSettings, posthogStore, settingsOf } from '../src/posthog.mjs';
import { heldOf, pypiFeeds } from '../src/versions.mjs';

// Each lives as long as the instance: the store keeps health's answer a minute, the limiters /v1/forget's counts
// and /v1/install's.
let store;
const limiter = rateLimiter();
const installLimiter = rateLimiter(INSTALL_LIMIT);
// The version feed's two addresses, from one read of PyPI, holding back the releases the project's
// `CAD_HELD_RELEASES` names (README, "Holding a release").
const { releases, versions } = pypiFeeds({ held: heldOf(process.env) });
const serve = request => handle(request, (store ??= posthogStore(settingsOf(process.env))), {
  // Names only: what /v1/health reports missing, so a deploy without them fails its check.
  missing: missingSettings(process.env),
  // Where Vercel's edge places the request, from its IP address: passed on with the batch's events as a
  // country, and the address itself kept nowhere.
  country: request.headers.get('x-vercel-ip-country'),
  versions,
  releases,
  // Who is asking to forget, or reporting a failed install, by the address Vercel saw: counted in memory, hashed,
  // for ten minutes at most.
  limiter,
  installLimiter,
  client: clientOf(request.headers),
});

export const GET = serve;
export const POST = serve;
