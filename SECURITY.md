# Security Policy

## Scope

text-to-cad is a local development tool: agent skills and `cadgen`, the
distribution that builds, views and exports CAD models on your own machine.
Everything below runs as you, with your files.

**The engine.** One warm `cadgen` daemon per installation does the building,
viewing and exporting. Its clients reach it through its door, a named pipe
with a pair of pipes per connection, that only you can open (on Windows, a
loopback port and a token in a file only you can read). The door lives in the
engine's folder (`CADGEN_ENGINE_DIR`, by default
`cadgen-engine` in `$XDG_RUNTIME_DIR`, else in a temporary folder that is yours alone (on macOS
the system's per-user one, else `$TMPDIR`),
else `/tmp/cadgen-<uid>`). The client and the daemon refuse a folder that
another user owns or that others can write to. A shell inside an agent's
sandbox that can open the door builds with the engine's own rights, outside
the sandbox, by design (the door is how a sandboxed agent reaches the
engine), so the boundary is your user account, not the sandbox.

**The CAD Viewer and the MCP endpoint.** The engine serves the CAD Viewer and
the CAD app's MCP endpoint over HTTP on `127.0.0.1` (port 3245 unless you name
another; when another program holds it, the next free port, which your
installation keeps and names in `cadgen status`). Every route needs one of three
credentials, all made from one token:

- **The token** is yours, not one engine's: made once, kept in a file only you
  can read in your state folder (`engines/token`), and served by every
  installation's engine at every start until you rotate it. No URL carries it,
  and only `cadgen viewer --api-only --json` prints it, for the development
  client's proxy. Your own clients read it through the engine's door and send
  it as a Bearer header.
- **A link** is what every URL cadgen prints or opens carries (`cad_show`'s,
  `cadgen viewer`'s, a build's `view:` line, the page it opens in your
  browser): `?token=` with an expiry and the token's signature of it. It works
  for 24 hours. After that it opens the viewer only in a browser that holds a
  session; anywhere else its page says it has expired and to run
  `cadgen viewer` for a new one.
- **The session cookie** is what a browser is given for a link: HttpOnly,
  SameSite=Strict, one name for every port of this host, holding the token's
  signature of its own expiry, never the token. It lasts 30 days from its last
  use: every page load renews it, and so does any request once it is a day old.

An engine checks a link or a cookie by signing it again, so it keeps no
sessions: links and cookies outlive a restart, a reboot, a port that moved and
an upgrade. `cadgen server --rotate-token`, with every engine stopped
(`cadgen stop`, with each version that runs one), replaces the token, and with
it every link and every session made before. Behind the credentials:

- A Host check refuses DNS rebinding.
- A request the cookie alone admits must come from the engine's own pages or
  from you (the browser says which in `Sec-Fetch-Site`), so another site, or a
  page on another port of this host, cannot use it.
- A state-changing request also needs a custom header, so a cross-site form or
  fetch cannot make one.
- One cross-origin case is answered, and only that one: a request whose
  `Authorization` header carries a link within its day, and that request's
  preflight, get CORS headers for the origin that sent it, so a CAD card whose
  host carries none of its calls back can read the engine from its sandbox
  (`cadgen.viewer.engine_app`). A browser never sends that header by itself, so
  only a page already holding the link can; no credentials header is ever sent,
  so the session cookie never rides a cross-origin read. A link in a URL, the
  cookie, your own token and `/mcp` get no CORS headers.

**The credentials are the boundary.** Whoever holds the token, a link within its
day, or a session cookie can read any CAD file on your machine by its path, list
folders, export, and use every Viewer action. So keep links private. Do not bind
a non-loopback `--host` unless you mean to offer exactly that to everyone who
can reach the port.

**The CAD app in agent hosts.** The page's own tools (`cad_sync`,
`cad_capture_reply` and `cad_http`, its requests of the viewer's routes) need a
per-session capability. The server delivers it in tool-result metadata, which
MCP Apps hosts keep out of the model's context, and refuses a call without it
before anything routes the request. Agents reach none of the viewer's routes.
The page answers only messages from its host's window.

**Files from others.** A STEP, xbf, GLB, STL, 3MF, DXF, URDF, SDF or SRDF
written by someone else is untrusted input. The engine reads it in separate
processes and bounds its work: assembly, node and block expansion, archive
unpacking, and buffer reads. It fetches nothing a file names over the network.
`cadgen sdf validate` runs `gz sdf --check` on a document that names a remote
reference only when asked (`--gz-remote`).

### What we treat as a vulnerability

- Reaching the engine, its files or its actions without the token, a link or
  the session cookie, or taking one of them, from another origin, another
  local user, or a file you open.
- A file from someone else that reads, writes or runs anything beyond what
  opening, viewing, exporting or snapshotting it should. This includes a file
  that makes the engine do unbounded work or hold unbounded memory.
- An MCP tool that the model can use to act as the CAD app's page, or a frame
  that can act as its host.
- A way to publish to PyPI or the install branches (`latest`, `claude-plugin`)
  other than a merged release.
- `api.texttocad.dev`: anything beyond its documented behaviour (version feed,
  consented analytics).

Out of scope: what someone who already has your token, a link within its day or
your session cookie, or already runs code as you, can do; and effects on your
own machine that you start yourself, such as building your own script.

## Reporting a Vulnerability

Report it privately:

1. Use the repository's **Security tab → Report a vulnerability**
   (GitHub Security Advisories).
2. Do **NOT** open a public issue or pull request for a security
   vulnerability.
3. Include a description, reproduction steps, and potential impact. A small
   file or command that shows the effect is the most useful. Do not run
   automated scans or load against `api.texttocad.dev`.

We aim to acknowledge reports within 48 hours and provide a fix timeline
within 7 days. We ask that you give us time to address the issue before
disclosing it publicly.

## Supported Versions

Only the latest release is supported. No older versions receive security
fixes; update to the newest tagged release to stay covered.

| Version | Supported |
|---------|-----------|
| latest  | Yes       |
| older   | No        |
