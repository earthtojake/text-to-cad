// The server-rendered pages: the home page, sign-in, and the account page (API keys,
// builds, the MCP URL). Plain HTML with inline styles and no external assets.
import { Hono, type Context } from 'hono';
import type { Auth, User } from './auth.ts';
import { safeNext } from './auth.ts';
import { CloudError, isCloudError } from './errors.ts';
import type { usageToday } from './limits.ts';
import { buildTitle } from './present.ts';
import type { Service } from './service.ts';

export const escapeHtml = (value: unknown) =>
  String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!);

const STYLE = `
:root { color-scheme: light dark; --fg: #1d1d1f; --muted: #5f6368; --bg: #fff; --line: #d9d9de; --accent: #0b57d0; }
@media (prefers-color-scheme: dark) { :root { --fg: #ececf1; --muted: #a0a0a8; --bg: #141416; --line: #34343a; --accent: #8ab4f8; } }
* { box-sizing: border-box; }
body { margin: 0; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--fg); background: var(--bg); }
main { max-width: 760px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.6rem; margin: 0 0 8px; } h2 { font-size: 1.15rem; margin: 32px 0 8px; }
a { color: var(--accent); } p { margin: 8px 0; } .muted { color: var(--muted); }
code, .key { font: 0.9rem/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
.key { display: block; padding: 12px; border: 1px solid var(--line); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
form.inline { display: inline; } input[type=text] { font: inherit; padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; background: transparent; color: inherit; }
button { font: inherit; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--line); background: transparent; color: inherit; cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.note { padding: 12px; border-left: 3px solid var(--accent); margin: 16px 0; }
`;

export function page(title: string, body: string): string {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title><style>${STYLE}</style></head>
<body><main>${body}</main></body></html>`;
}

const PAGE_HEADERS = {
  'content-security-policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'same-origin',
  'cache-control': 'no-store',
};

export function htmlResponse(c: Context, html: string, status = 200) {
  for (const [name, value] of Object.entries(PAGE_HEADERS)) c.header(name, value);
  return c.html(html, status as 200);
}

const when = (value: string | null) => (value ? new Date(value).toISOString().replace('T', ' ').slice(0, 16) + ' UTC' : '—');

export function webRoutes(service: Service, auth: Auth, deps: { usage: (user: User) => ReturnType<typeof usageToday> }) {
  const app = new Hono();
  const { config } = service;
  const mcpUrl = `${config.publicUrl}/mcp`;

  app.get('/', (c) => htmlResponse(c, page('Text-to-CAD Cloud', `
<h1>Text-to-CAD Cloud</h1>
<p>Build CAD models from code in a sandbox and open them in the CAD viewer from a link.
Agents send model code over MCP or REST; each build runs the released cadgen in a single-use
sandbox with no network, and gets a link anyone with the link can open.</p>
<h2>Connect an agent</h2>
<p>Add this MCP server URL as a custom connector in Claude, ChatGPT or any MCP host:</p>
<p class="key">${escapeHtml(mcpUrl)}</p>
<p>The host signs you in with your account. For scripts and other agents, create an API key on your <a href="/account">account page</a> and send it as <code>Authorization: Bearer t2c_…</code>.</p>
<p><a href="/account">Account</a></p>`)));

  app.get('/auth/login', async (c) => {
    try {
      const { location, cookie } = await auth.loginRedirect(safeNext(c.req.query('next')));
      if (cookie) c.header('set-cookie', cookie);
      return c.redirect(location, 302);
    } catch (error) {
      if (isCloudError(error)) return htmlResponse(c, page('Sign in', `<h1>Sign in</h1><p>${escapeHtml(error.message)}</p>`), error.status);
      throw error;
    }
  });

  app.get('/auth/callback', async (c) => {
    try {
      const { next, cookies } = await auth.completeLogin(c.req.raw);
      for (const cookie of cookies) c.header('set-cookie', cookie, { append: true });
      return c.redirect(next, 302);
    } catch (error) {
      if (isCloudError(error)) {
        return htmlResponse(c, page('Sign in', `<h1>Sign in failed</h1><p>${escapeHtml(error.message)}</p><p><a href="/auth/login">Try again</a></p>`), error.status);
      }
      throw error;
    }
  });

  const logout = (c: Context) => {
    c.header('set-cookie', auth.logoutCookie());
    return c.redirect('/', 302);
  };
  app.get('/auth/logout', logout);
  app.post('/auth/logout', logout);

  async function account(c: Context, created?: { name: string; key: string }, message?: string) {
    const session = await auth.sessionUser(c.req.raw);
    if (!session) return c.redirect(`/auth/login?next=${encodeURIComponent('/account')}`, 302);
    const { user, csrf } = session;
    const [keys, builds, usage] = await Promise.all([auth.listApiKeys(user), service.listBuilds(user, 20), deps.usage(user)]);
    const csrfField = `<input type="hidden" name="csrf" value="${escapeHtml(csrf)}">`;
    const keyRows = keys.map((key) => `<tr><td>${escapeHtml(key.name)}</td><td><code>${escapeHtml(key.prefix)}</code></td><td>${when(key.createdAt)}</td><td>${when(key.lastUsedAt)}</td>
<td><form class="inline" method="post" action="/account/api-keys/${encodeURIComponent(key.id)}/delete">${csrfField}<button type="submit" aria-label="Delete the key ${escapeHtml(key.name)}">Delete</button></form></td></tr>`).join('');
    const buildRows = builds.map((build) => `<tr><td><a href="${escapeHtml(service.buildLink(build))}">${escapeHtml(buildTitle(build))}</a></td><td>${escapeHtml(build.status)}</td><td>${when(build.createdAt)}</td></tr>`).join('');
    return htmlResponse(c, page('Account · Text-to-CAD Cloud', `
<h1>Account</h1>
<p>Signed in as <strong>${escapeHtml(user.email ?? user.name ?? user.id)}</strong>.
${auth.mode === 'dev' ? '<span class="muted">(development sign-in)</span>' : `<form class="inline" method="post" action="/auth/logout">${csrfField}<button type="submit">Sign out</button></form>`}</p>
${message ? `<p class="note" role="status">${escapeHtml(message)}</p>` : ''}
<h2>MCP server</h2>
<p>Add this URL to Claude, ChatGPT or another MCP host as a custom connector:</p>
<p class="key">${escapeHtml(mcpUrl)}</p>
<h2>API keys</h2>
${created ? `<div class="note" role="status"><p>New key <strong>${escapeHtml(created.name)}</strong>. Copy it now: it is not shown again.</p><p class="key">${escapeHtml(created.key)}</p></div>` : ''}
${keys.length ? `<table><thead><tr><th scope="col">Name</th><th scope="col">Key</th><th scope="col">Created</th><th scope="col">Last used</th><th scope="col"><span class="muted">Delete</span></th></tr></thead><tbody>${keyRows}</tbody></table>` : '<p class="muted">No API keys yet.</p>'}
<form method="post" action="/account/api-keys">${csrfField}<p><label for="key-name">Name</label>
<input type="text" id="key-name" name="name" maxlength="80" placeholder="e.g. laptop"> <button class="primary" type="submit">Create API key</button></p></form>
<h2>Today</h2>
<p>${usage.vcpuSeconds} of ${usage.limitVcpuSeconds} vCPU-seconds used (resets ${when(usage.resetsAt)}).</p>
<h2>Recent builds</h2>
${builds.length ? `<table><thead><tr><th scope="col">Build</th><th scope="col">Status</th><th scope="col">Created</th></tr></thead><tbody>${buildRows}</tbody></table>` : '<p class="muted">No builds yet.</p>'}`));
  }

  app.get('/account', (c) => account(c));

  app.post('/account/api-keys', async (c) => {
    const form = await c.req.parseBody();
    if (!(await auth.checkCsrf(c.req.raw, form.csrf))) throw new CloudError(403, 'forbidden', 'This form expired; reload the account page.');
    const session = (await auth.sessionUser(c.req.raw))!;
    const created = await auth.createApiKey(session.user, typeof form.name === 'string' ? form.name : '');
    return account(c, created);
  });

  app.post('/account/api-keys/:id/delete', async (c) => {
    const form = await c.req.parseBody();
    if (!(await auth.checkCsrf(c.req.raw, form.csrf))) throw new CloudError(403, 'forbidden', 'This form expired; reload the account page.');
    const session = (await auth.sessionUser(c.req.raw))!;
    const deleted = await auth.deleteApiKey(session.user, c.req.param('id'));
    return account(c, undefined, deleted ? 'The key was deleted.' : 'That key was already gone.');
  });

  return app;
}
