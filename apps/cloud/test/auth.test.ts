import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT, type JWK } from 'jose';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { PUBLIC_URL, testServer, type TestServer } from './helpers.ts';

const ISSUER = 'https://auth.example';
let privateKey: CryptoKey;
let jwk: JWK;

beforeAll(async () => {
  const pair = await generateKeyPair('RS256');
  privateKey = pair.privateKey;
  jwk = { ...(await exportJWK(pair.publicKey)), kid: 'test', alg: 'RS256' };
});

const token = (claims: Record<string, unknown> = {}, { audience = `${PUBLIC_URL}/mcp`, issuer = ISSUER, expires = '1h' } = {}) =>
  new SignJWT({ email: 'ada@example.com', ...claims })
    .setProtectedHeader({ alg: 'RS256', kid: 'test' })
    .setIssuer(issuer)
    .setAudience(audience)
    .setSubject(String(claims.sub ?? 'user-1'))
    .setIssuedAt()
    .setExpirationTime(expires)
    .sign(privateKey);

const bearer = (value: string) => ({ authorization: `Bearer ${value}` });

let server: TestServer | undefined;
afterEach(async () => {
  await server?.close();
  server = undefined;
});

/** A fake identity provider: discovery and a token endpoint that returns an id_token. */
function provider(idToken: () => Promise<string>) {
  const calls: { url: string; body?: string }[] = [];
  const fetch = async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input instanceof Request ? input.url : input);
    calls.push({ url, body: init?.body ? String(init.body) : undefined });
    if (url === `${ISSUER}/.well-known/openid-configuration`) {
      return Response.json({ issuer: ISSUER, authorization_endpoint: `${ISSUER}/authorize`, token_endpoint: `${ISSUER}/token`, jwks_uri: `${ISSUER}/jwks` });
    }
    if (url === `${ISSUER}/token`) return Response.json({ id_token: await idToken(), access_token: 'x', token_type: 'Bearer' });
    return new Response('not found', { status: 404 });
  };
  return { fetch: fetch as typeof globalThis.fetch, calls };
}

async function oauthServer(fetchImpl?: typeof globalThis.fetch) {
  return testServer({
    env: { CLOUD_AUTH: 'oauth', AUTH_ISSUER: ISSUER, AUTH_CLIENT_ID: 'client-1', SESSION_SECRET: 's'.repeat(40) },
    auth: { jwks: createLocalJWKSet({ keys: [jwk] }), fetch: fetchImpl },
  });
}

describe('bearer auth', () => {
  it('publishes protected resource metadata in both forms', async () => {
    server = await oauthServer();
    expect(await (await server.request('/.well-known/oauth-protected-resource')).json()).toMatchObject({ resource: PUBLIC_URL, authorization_servers: [ISSUER] });
    expect(await (await server.request('/.well-known/oauth-protected-resource/mcp')).json()).toMatchObject({ resource: `${PUBLIC_URL}/mcp`, bearer_methods_supported: ['header'] });
  });

  it('answers 401 with where to sign in', async () => {
    server = await oauthServer();
    const response = await server.request('/v1/me');
    expect(response.status).toBe(401);
    expect(response.headers.get('www-authenticate')).toBe(`Bearer resource_metadata="${PUBLIC_URL}/.well-known/oauth-protected-resource"`);
    const invalid = await server.request('/v1/me', { headers: bearer('nonsense') });
    expect(invalid.headers.get('www-authenticate')).toContain('error="invalid_token"');
  });

  it('accepts a token for this resource from the issuer, and nothing else', async () => {
    server = await oauthServer();
    const me = await server.request('/v1/me', { headers: bearer(await token()) });
    expect(me.status).toBe(200);
    expect(await me.json()).toMatchObject({ user: { email: 'ada@example.com' }, mcp: `${PUBLIC_URL}/mcp` });
    expect((await server.request('/v1/me', { headers: bearer(await token({}, { audience: PUBLIC_URL })) })).status).toBe(200);
    for (const bad of [
      await token({}, { audience: 'https://other.example/mcp' }),
      await token({}, { issuer: 'https://evil.example' }),
      await token({}, { expires: '-1m' }),
    ]) {
      expect((await server.request('/v1/me', { headers: bearer(bad) })).status).toBe(401);
    }
  });

  it('creates API keys that work until deleted, and keeps keys from minting keys', async () => {
    server = await oauthServer();
    const oauth = bearer(await token());
    const created = await server.request('/v1/api-keys', { method: 'POST', headers: oauth, json: { name: 'laptop' } });
    expect(created.status).toBe(201);
    const key = await created.json();
    expect(key.key).toMatch(/^t2c_[0-9A-Za-z]{40}$/);
    const { rows } = await server.db.query('select hash from api_keys');
    expect(rows[0].hash).not.toContain(key.key); // only the digest is stored

    const withKey = bearer(key.key);
    expect((await server.request('/v1/me', { headers: withKey })).status).toBe(200);
    expect((await server.request('/v1/api-keys', { method: 'POST', headers: withKey, json: {} })).status).toBe(403);
    expect((await server.request(`/v1/api-keys/${key.id}`, { method: 'DELETE', headers: oauth })).status).toBe(204);
    expect((await server.request('/v1/me', { headers: withKey })).status).toBe(401);
  });

  it('signs everyone in as dev in development mode', async () => {
    server = await testServer();
    expect(await (await server.request('/v1/me')).json()).toMatchObject({ user: { id: 'dev' } });
  });

  it('refuses dev sign-in in production', async () => {
    const { loadConfig } = await import('../server/config.ts');
    expect(() => loadConfig({ NODE_ENV: 'production', CLOUD_AUTH: 'dev' })).toThrow(/refused when NODE_ENV=production/);
  });
});

describe('web sign-in', () => {
  it('signs in with code + PKCE, then manages API keys on the account page', async () => {
    let nonce = '';
    const idp = provider(() => token({ nonce, sub: 'web-user' }, { audience: 'client-1' }));
    server = await oauthServer(idp.fetch);

    const login = await server.request('/auth/login?next=/account');
    expect(login.status).toBe(302);
    const authorize = new URL(login.headers.get('location')!);
    expect(authorize.origin + authorize.pathname).toBe(`${ISSUER}/authorize`);
    expect(Object.fromEntries(authorize.searchParams)).toMatchObject({
      response_type: 'code',
      client_id: 'client-1',
      redirect_uri: `${PUBLIC_URL}/auth/callback`,
      code_challenge_method: 'S256',
    });
    nonce = authorize.searchParams.get('nonce')!;
    const loginCookie = login.headers.get('set-cookie')!.split(';')[0];

    const forged = await server.request(`/auth/callback?code=abc&state=wrong`, { headers: { cookie: loginCookie } });
    expect(forged.status).toBe(400);
    const callback = await server.request(`/auth/callback?code=abc&state=${authorize.searchParams.get('state')}`, { headers: { cookie: loginCookie } });
    expect(callback.status).toBe(302);
    expect(callback.headers.get('location')).toBe('/account');
    expect(idp.calls.find((call) => call.url.endsWith('/token'))?.body).toContain('code_verifier=');
    const session = callback.headers.getSetCookie().find((cookie) => cookie.startsWith('t2c_session='))!.split(';')[0];

    expect((await server.request('/account')).status).toBe(302); // signed out
    const account = await server.request('/account', { headers: { cookie: session } });
    const html = await account.text();
    expect(html).toContain(`${PUBLIC_URL}/mcp`);
    const csrf = /name="csrf" value="([^"]+)"/.exec(html)![1];

    const rejected = await server.request('/account/api-keys', { method: 'POST', headers: { cookie: session, 'content-type': 'application/x-www-form-urlencoded' }, body: 'name=laptop&csrf=forged' });
    expect(rejected.status).toBe(403);
    const created = await server.request('/account/api-keys', { method: 'POST', headers: { cookie: session, 'content-type': 'application/x-www-form-urlencoded' }, body: `name=laptop&csrf=${encodeURIComponent(csrf)}` });
    const key = /t2c_[0-9A-Za-z]{40}/.exec(await created.text())![0];
    expect(await (await server.request('/v1/me', { headers: bearer(key) })).json()).toMatchObject({ user: { email: 'ada@example.com' } });
  });
});
