// Who is calling. Three ways in:
//   * `CLOUD_AUTH=dev`: everyone is the user `dev` (local development only);
//   * `Authorization: Bearer t2c_…`: an API key (only its SHA-256 is stored);
//   * `Authorization: Bearer <JWT>`: an OAuth access token from AUTH_ISSUER, verified
//     against its JWKS, with this server's resource URL as the audience.
// The web pages sign in with OIDC (authorization code + PKCE) and a signed cookie.
import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from 'jose';
import type { Clock } from './clock.ts';
import { iso } from './clock.ts';
import type { Config } from './config.ts';
import type { Db } from './db/index.ts';
import { CloudError, badRequest, forbidden } from './errors.ts';
import { API_KEY_PREFIX, newApiKey, newId, sha256Hex } from './ids.ts';

export interface User {
  id: string;
  issuer: string;
  subject: string;
  email: string | null;
  name: string | null;
}

export type Credential = 'dev' | 'api_key' | 'oauth' | 'session';

export type AuthResult =
  | { ok: true; user: User; via: Credential }
  | { ok: false; reason: 'missing' | 'invalid'; message: string };

export interface ApiKeyView {
  id: string;
  name: string;
  prefix: string;
  createdAt: string;
  lastUsedAt: string | null;
}

export interface Auth {
  mode: 'dev' | 'oauth';
  authenticate(request: Request): Promise<AuthResult>;
  /** The signed-in person of a web page, from the session cookie (or `dev`). */
  sessionUser(request: Request): Promise<{ user: User; csrf: string } | null>;
  protectedResourceMetadata(resource: string): Record<string, unknown>;
  challenge(resourceMetadataUrl: string, error?: string): string;
  ensureUser(issuer: string, subject: string, claims?: { email?: unknown; name?: unknown }): Promise<User>;
  createApiKey(user: User, name: string): Promise<ApiKeyView & { key: string }>;
  listApiKeys(user: User): Promise<ApiKeyView[]>;
  deleteApiKey(user: User, id: string): Promise<boolean>;
  checkCsrf(request: Request, token: unknown): Promise<boolean>;
  loginRedirect(next: string): Promise<{ location: string; cookie: string }>;
  completeLogin(request: Request): Promise<{ user: User; next: string; cookies: string[] }>;
  logoutCookie(): string;
}

export interface AuthOptions {
  config: Config;
  db: Db;
  clock: Clock;
  /** Overrides the issuer's JWKS (tests use a local key set). */
  jwks?: JWTVerifyGetKey;
  /** Fetch for OIDC discovery and the token endpoint (tests inject one). */
  fetch?: typeof fetch;
}

const SESSION_COOKIE = 't2c_session';
const LOGIN_COOKIE = 't2c_login';
const SESSION_DAYS = 30;

const b64url = (bytes: Buffer | Uint8Array) => Buffer.from(bytes).toString('base64url');

export function readCookie(request: Request, name: string): string | null {
  const header = request.headers.get('cookie');
  if (!header) return null;
  for (const part of header.split(';')) {
    const index = part.indexOf('=');
    if (index > 0 && part.slice(0, index).trim() === name) return decodeURIComponent(part.slice(index + 1).trim());
  }
  return null;
}

export function createAuth({ config, db, clock, jwks, fetch: fetchImpl = fetch }: AuthOptions): Auth {
  const secret = config.auth.sessionSecret;
  const secure = config.publicUrl.startsWith('https://');
  const cookieFlags = `Path=/; HttpOnly; SameSite=Lax${secure ? '; Secure' : ''}`;

  const sign = (value: string) => b64url(createHmac('sha256', secret).update(value).digest());
  function seal(payload: Record<string, unknown>): string {
    const body = b64url(Buffer.from(JSON.stringify(payload)));
    return `${body}.${sign(body)}`;
  }
  function unseal(token: string | null): Record<string, any> | null {
    if (!token) return null;
    const [body, mac] = token.split('.');
    if (!body || !mac) return null;
    const expected = Buffer.from(sign(body));
    const given = Buffer.from(mac);
    if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
    try {
      const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
      if (typeof payload.e !== 'number' || payload.e < clock.now()) return null;
      return payload;
    } catch {
      return null;
    }
  }

  let discovery: Promise<Record<string, any>> | undefined;
  function discover(): Promise<Record<string, any>> {
    if (!config.auth.issuer) return Promise.reject(new CloudError(503, 'auth_unconfigured', 'Sign-in is not configured on this server (AUTH_ISSUER is unset).'));
    discovery ??= fetchImpl(`${config.auth.issuer}/.well-known/openid-configuration`).then(async (response) => {
      if (!response.ok) throw new Error(`OIDC discovery failed: ${response.status}`);
      return response.json() as Promise<Record<string, any>>;
    });
    discovery.catch(() => {
      discovery = undefined;
    });
    return discovery;
  }
  let remoteJwks: JWTVerifyGetKey | undefined;
  async function keySet(): Promise<JWTVerifyGetKey> {
    if (jwks) return jwks;
    if (!remoteJwks) {
      const url = config.auth.jwksUrl ?? (await discover()).jwks_uri;
      if (!url) throw new Error('no JWKS URL: set AUTH_JWKS_URL');
      remoteJwks = createRemoteJWKSet(new URL(url));
    }
    return remoteJwks;
  }

  async function ensureUser(issuer: string, subject: string, claims: { email?: unknown; name?: unknown } = {}): Promise<User> {
    const email = typeof claims.email === 'string' ? claims.email.slice(0, 320) : null;
    const name = typeof claims.name === 'string' ? claims.name.slice(0, 200) : null;
    const id = issuer === 'dev' && subject === 'dev' ? 'dev' : newId();
    const { rows } = await db.query<User>(
      `insert into users (id, issuer, subject, email, name, created_at) values ($1, $2, $3, $4, $5, $6)
       on conflict (issuer, subject) do update set
         email = coalesce(excluded.email, users.email), name = coalesce(excluded.name, users.name)
       returning id, issuer, subject, email, name`,
      [id, issuer, subject, email, name, iso(clock.now())],
    );
    return rows[0];
  }

  const devUser = () => ensureUser('dev', 'dev', { name: 'Developer' });

  async function userById(id: string): Promise<User | null> {
    const { rows } = await db.query<User>('select id, issuer, subject, email, name from users where id = $1', [id]);
    return rows[0] ?? null;
  }

  async function verifyJwt(token: string): Promise<User> {
    if (!config.auth.issuer) throw new Error('OAuth tokens are not accepted: AUTH_ISSUER is unset');
    const { payload } = await jwtVerify(token, await keySet(), {
      issuer: [config.auth.issuer, `${config.auth.issuer}/`],
      audience: config.auth.audiences,
      clockTolerance: 5,
    });
    if (!payload.sub) throw new Error('the token has no subject');
    // One spelling of the issuer per person, whichever form (trailing slash or not) the token used.
    return ensureUser(config.auth.issuer, payload.sub, payload as JWTPayload & { email?: unknown; name?: unknown });
  }

  async function verifyApiKey(key: string): Promise<User | null> {
    const { rows } = await db.query<User & { key_id: string }>(
      `select u.id, u.issuer, u.subject, u.email, u.name, k.id as key_id
       from api_keys k join users u on u.id = k.user_id where k.hash = $1`,
      [sha256Hex(key)],
    );
    const row = rows[0];
    if (!row) return null;
    const now = clock.now();
    await db.query(
      'update api_keys set last_used_at = $2 where id = $1 and (last_used_at is null or last_used_at < $3)',
      [row.key_id, iso(now), iso(now - 60_000)],
    );
    return { id: row.id, issuer: row.issuer, subject: row.subject, email: row.email, name: row.name };
  }

  async function sessionUser(request: Request): Promise<{ user: User; csrf: string } | null> {
    if (config.auth.mode === 'dev') return { user: await devUser(), csrf: sign('csrf:dev') };
    const session = unseal(readCookie(request, SESSION_COOKIE));
    if (!session || typeof session.u !== 'string') return null;
    const user = await userById(session.u);
    return user ? { user, csrf: sign(`csrf:${session.n}`) } : null;
  }

  const toView = (row: Record<string, any>): ApiKeyView => ({
    id: row.id,
    name: row.name,
    prefix: row.prefix,
    createdAt: new Date(row.created_at).toISOString(),
    lastUsedAt: row.last_used_at ? new Date(row.last_used_at).toISOString() : null,
  });

  return {
    mode: config.auth.mode,

    async authenticate(request) {
      const header = request.headers.get('authorization');
      if (config.auth.mode === 'dev') return { ok: true, user: await devUser(), via: 'dev' };
      if (!header) return { ok: false, reason: 'missing', message: 'Sign in first: send an API key or an OAuth access token as a Bearer token.' };
      const match = /^Bearer\s+(\S+)\s*$/i.exec(header);
      if (!match) return { ok: false, reason: 'invalid', message: 'The Authorization header must be "Bearer <token>".' };
      const token = match[1];
      if (token.startsWith(API_KEY_PREFIX)) {
        const user = await verifyApiKey(token);
        return user ? { ok: true, user, via: 'api_key' } : { ok: false, reason: 'invalid', message: 'This API key is not valid (it may have been deleted).' };
      }
      try {
        return { ok: true, user: await verifyJwt(token), via: 'oauth' };
      } catch (error) {
        return { ok: false, reason: 'invalid', message: `The access token was refused: ${(error as Error).message}` };
      }
    },

    sessionUser,

    protectedResourceMetadata(resource) {
      return {
        resource,
        authorization_servers: config.auth.issuer ? [config.auth.issuer] : [],
        bearer_methods_supported: ['header'],
        scopes_supported: config.auth.scopes.split(/\s+/).filter(Boolean),
        resource_name: 'Text-to-CAD Cloud',
        resource_documentation: `${config.publicUrl}/`,
      };
    },

    challenge(resourceMetadataUrl, error) {
      return `Bearer resource_metadata="${resourceMetadataUrl}"${error ? `, error="${error}"` : ''}`;
    },

    ensureUser,

    async createApiKey(user, rawName) {
      const name = String(rawName ?? '').replace(/[\u0000-\u001f\u007f]+/g, ' ').trim().slice(0, 80) || 'API key';
      const { rows: count } = await db.query<{ n: number }>('select count(*)::int as n from api_keys where user_id = $1', [user.id]);
      if ((count[0]?.n ?? 0) >= 20) throw badRequest('You have 20 API keys; delete one before creating another.');
      const key = newApiKey();
      const view = { id: newId(), name, prefix: `${key.slice(0, 8)}…`, createdAt: iso(clock.now()), lastUsedAt: null };
      await db.query(
        'insert into api_keys (id, user_id, name, hash, prefix, created_at) values ($1, $2, $3, $4, $5, $6)',
        [view.id, user.id, name, sha256Hex(key), view.prefix, view.createdAt],
      );
      return { ...view, key };
    },

    async listApiKeys(user) {
      const { rows } = await db.query('select id, name, prefix, created_at, last_used_at from api_keys where user_id = $1 order by created_at desc', [user.id]);
      return rows.map(toView);
    },

    async deleteApiKey(user, id) {
      const { rowCount } = await db.query('delete from api_keys where id = $1 and user_id = $2', [id, user.id]);
      return rowCount > 0;
    },

    async checkCsrf(request, token) {
      const origin = request.headers.get('origin');
      if (origin && origin !== config.publicUrl) return false;
      const session = await sessionUser(request);
      if (!session || typeof token !== 'string') return false;
      const expected = Buffer.from(session.csrf);
      const given = Buffer.from(token);
      return expected.length === given.length && timingSafeEqual(expected, given);
    },

    async loginRedirect(next) {
      if (config.auth.mode === 'dev') return { location: next, cookie: '' };
      if (!config.auth.clientId) throw new CloudError(503, 'auth_unconfigured', 'Web sign-in is not configured on this server (AUTH_CLIENT_ID is unset).');
      const meta = await discover();
      const verifier = b64url(randomBytes(32));
      const state = b64url(randomBytes(16));
      const nonce = b64url(randomBytes(16));
      const codeChallenge = b64url(createHash('sha256').update(verifier).digest());
      const url = new URL(meta.authorization_endpoint);
      url.search = new URLSearchParams({
        response_type: 'code',
        client_id: config.auth.clientId,
        redirect_uri: `${config.publicUrl}/auth/callback`,
        scope: config.auth.scopes,
        state,
        nonce,
        code_challenge: codeChallenge,
        code_challenge_method: 'S256',
      }).toString();
      const cookie = `${LOGIN_COOKIE}=${seal({ s: state, v: verifier, n: nonce, next: safeNext(next), e: clock.now() + 600_000 })}; ${cookieFlags}; Max-Age=600`;
      return { location: url.toString(), cookie };
    },

    async completeLogin(request) {
      if (!config.auth.clientId) throw new CloudError(503, 'auth_unconfigured', 'Web sign-in is not configured on this server.');
      const url = new URL(request.url);
      const login = unseal(readCookie(request, LOGIN_COOKIE));
      if (url.searchParams.get('error')) throw forbidden(`Sign-in was cancelled: ${url.searchParams.get('error_description') || url.searchParams.get('error')}`);
      const code = url.searchParams.get('code');
      if (!login || !code || url.searchParams.get('state') !== login.s) throw badRequest('This sign-in link expired or was already used. Start again from /auth/login.');
      const meta = await discover();
      const body = new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: `${config.publicUrl}/auth/callback`,
        client_id: config.auth.clientId,
        code_verifier: login.v,
      });
      if (config.auth.clientSecret) body.set('client_secret', config.auth.clientSecret);
      const response = await fetchImpl(meta.token_endpoint, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' },
        body,
      });
      const tokens = (await response.json().catch(() => ({}))) as Record<string, any>;
      if (!response.ok || typeof tokens.id_token !== 'string') throw forbidden('The identity provider refused the sign-in.');
      const { payload } = await jwtVerify(tokens.id_token, await keySet(), {
        issuer: [config.auth.issuer!, `${config.auth.issuer}/`],
        audience: config.auth.clientId,
        clockTolerance: 5,
      });
      if (payload.nonce !== login.n || !payload.sub) throw forbidden('The sign-in response did not match this browser.');
      const user = await ensureUser(config.auth.issuer!, payload.sub, payload as JWTPayload & { email?: unknown; name?: unknown });
      const session = seal({ u: user.id, n: b64url(randomBytes(12)), e: clock.now() + SESSION_DAYS * 86_400_000 });
      return {
        user,
        next: safeNext(login.next),
        cookies: [
          `${SESSION_COOKIE}=${session}; ${cookieFlags}; Max-Age=${SESSION_DAYS * 86_400}`,
          `${LOGIN_COOKIE}=; ${cookieFlags}; Max-Age=0`,
        ],
      };
    },

    logoutCookie: () => `${SESSION_COOKIE}=; ${cookieFlags}; Max-Age=0`,
  };
}

/** Only same-site paths are followed after sign-in. */
export function safeNext(next: unknown): string {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\') ? next : '/account';
}
