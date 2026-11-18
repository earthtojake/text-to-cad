# Security Policy

## Scope

text-to-cad is a local development tool: agent skills and `cad`, one package that holds the
library models import, the `cad` command and the server that builds, views and exports CAD models
on your own machine. Everything below runs as you, with your files.

**The server.** One warm server daemon on your computer does the building,
viewing and exporting. It starts only when asked (`cad server start`, or the CAD
app an agent app starts). Its clients reach it through its door, a named pipe with
a pair of pipes per connection, that only you can open (on Windows, a loopback
port and a token in a file only you can read). The door lives in the servers'
folder (`CAD_ENGINE_DIR`, by default
`cad-engine` in `$XDG_RUNTIME_DIR`, else in a temporary folder that is yours alone (on macOS
the system's per-user one, else `$TMPDIR`),
else `/tmp/cad-<uid>`). The client and the daemon refuse a folder that
another user owns or that others can write to. A shell inside an agent's
sandbox that can open the door builds with the server's own rights, outside
the sandbox -- in the Python its build names, too: a script's worker runs the
interpreter the script was launched with; and the packages a `cad run` names
(its `--with`, a script's `# /// script` block) the server installs with uv,
the network included -- by design (the door is how a sandboxed agent reaches
the server), so the boundary is your user account, not the sandbox.

**The CAD Viewer and the MCP endpoint.** The server serves the CAD Viewer and
the CAD app's MCP endpoint over HTTP on `127.0.0.1` (port 3245 unless you name
another; when another program holds it, the next free port, which your
installation keeps and names in `cad server status`). Every route needs one of three
credentials, all made from one token:

- **The token** is yours, not one server's: made once, kept in a file only you
  can read in cad's data folder (`engines/token`), and served by the server at
  every start, through updates, until you rotate it. No URL carries it,
  and only `cad viewer --api-only --json` prints it, for the development
  client's proxy. Your own clients read it through the server's door and send
  it as a Bearer header.
- **A link** is what every URL text-to-cad prints or opens carries (`cad_show`'s,
  `cad viewer`'s, a build's `view:` line, the page it opens in your
  browser): `?token=` with an expiry and the token's signature of it. It works
  until you rotate the token (`cad server --rotate-token`, which ends every link
  and every session at once), as a Jupyter server's URL token does; the token is
  kept in cad's data folder and survives restarts, reboots and updates, and so do
  links. Every link of one token is the same text, whenever it is printed (its
  expiry is one fixed date, the start of the year 3000), until the token is rotated. It stays in the page's address (a page opened without one is given
  one), so the address copied into another browser on this machine opens the
  same page. A link works only from this machine: the server listens on
  loopback (unless you bind another `--host`, below) and refuses any other Host. It never leaves in a Referer
  (every page is sent `Referrer-Policy: no-referrer`). A page's
  and a CAD app card's **Copy link** copy that link; the card asks for it
  through its tunnel, with a capability that already reaches everything a link
  does, so this widens nothing.
- **The session cookie** is what a browser is given for a link it opens:
  HttpOnly, SameSite=Strict, one name for every port of this host, holding the
  token's signature of its own expiry, never the token. It lasts 30 days from
  its last use: every page load renews it, and so does any request once it is a
  day old. It is what lets a reloaded page get the link for its address.

A server checks a link or a cookie by signing it again, so it keeps no
sessions: links and cookies outlive a restart, a reboot, a port that moved and
an upgrade. `cad server --rotate-token` replaces the token once you say yes (it
asks; `--yes` where it cannot), and with it every link and every session made
before: it writes the new token, and the running server takes it at once. A server
of 0.11.11 or earlier reads its token only as it starts, so it takes the new one
when it restarts. Behind the credentials:

- A Host check refuses DNS rebinding.
- A request the cookie alone admits must come from the server's own pages or
  from you (the browser says which in `Sec-Fetch-Site`), so another site, or a
  page on another port of this host, cannot use it.
- A state-changing request also needs a custom header, so a cross-site form or
  fetch cannot make one.
- One cross-origin case is answered, and only that one: a request whose
  `Authorization` header carries a link, and that request's
  preflight, get CORS headers for the origin that sent it, so a CAD card whose
  host carries none of its calls back can read the server from its sandbox
  (`cad_server.viewer.engine_app`). A browser never sends that header by itself, so
  only a page already holding the link can; no credentials header is ever sent,
  so the session cookie never rides a cross-origin read. A link in a URL, the
  cookie, your own token and `/mcp` get no CORS headers.

**The credentials are the boundary.** Whoever holds the token, a link, or a session cookie can read any CAD file on your machine by its path, list
folders, export, and use every Viewer action. So keep links private: treat a
link, and the address of an open CAD page, as you would a password for your
files on this computer. Do not bind
a non-loopback `--host` unless you mean to offer exactly that to everyone who
can reach the port.

**The CAD app in agent hosts.** The page's own tools (`cad_sync`,
`cad_capture_reply` and `cad_http`, its requests of the viewer's routes) need a
capability, one for each host connection. The server delivers it in tool-result metadata, which
MCP Apps hosts keep out of the model's context; to Cursor, which hands its card no result
metadata, in the metadata of the tool that opens the card (`cad_show`), which Cursor hands the
card and keeps out of what its agent reads of the tool. The server refuses a call without it
before anything routes the request: no host is trusted to keep the page's tools from the model.
Agents reach none of the viewer's routes.
The page answers only messages from its host's window.

**Files from others.** A STEP, xbf, GLB, STL, 3MF, DXF, URDF, SDF, SRDF, KiCad board or
schematic written by someone else is untrusted input. The server reads it in separate
processes (a KiCad file off its request threads, its refill in KiCad's own process) and bounds its work: assembly, node and block expansion, archive
unpacking, and buffer reads. It fetches nothing a file names over the network. The 3D models a KiCad
board names are read only as STEP files, and only inside the board's own folder, KiCad's installed 3D
library and the folders `CAD_KICAD_3DMODELS` names, every symlink followed first; any other file a board
names is shown as missing, and the page asks for a model's mesh by an id, never by a path. A name is
checked against those folders as text before any file system call is made for it, and one that is a
network share (`\\server\share`), a device (`\\?\`, `\\.\`) or drive-relative is refused outright, on
every platform: on Windows, opening a share would offer its server the person's credentials. A board
names at most 512 distinct models, each STEP at most 64 MiB and all of them at most 512 MiB.
`cad sdf validate` runs `gz sdf --check` on a document that names a remote
reference only when asked (`--gz-remote`).

**The install command.** `curl -fsSL https://texttocad.dev/install.sh | sh` (on
Windows `irm https://www.texttocad.dev/install.ps1 | iex`) runs, as you, with no sudo
and nothing asked:

- `install.sh` or `install.ps1`, served by texttocad.dev over HTTPS. Where uv is
  missing, or too old and cannot update itself, it downloads and runs uv's own
  installer from `astral.sh`.
- `install.py`, downloaded from texttocad.dev and run with uv's Python. Where no
  `cad` is installed, or the one there does not start, it installs PyPI's newest
  release of `cad` with `uv tool install`; a `cad` that is installed and starts is
  left as it is. Where cad's folder is not on the PATH, it runs uv's own
  `uv tool update-shell`, which adds it to your shell profile (on Windows, your
  user PATH); `UV_NO_MODIFY_PATH` stops that. cad sets it whenever cad itself runs
  the install command (`cad plugin update`, and when cad has been updated), so only
  a person's own run changes the PATH.
- The plugin, from this repository's `latest` branch on GitHub, installed in each
  agent app it finds with that app's own command. It removes what earlier releases
  left there, among them the CAD server they wrote into Claude Desktop's config
  (keeping a `.bak`).
- Where cad is there, `cad plugin update auto on`, so that each time cad is newer
  than the release the install command last ended well for, however it got newer
  (below), cad runs the install command again, once; a run that ends badly says so
  to cad, which then keeps no release as up to date. `cad plugin update` runs it
  too.

It starts no server. To read the scripts first, take the copies attached to a
release on GitHub and check them against the release's `SHA256SUMS`; they install
the newest release, not that one.

**Automatic updates.** A cad installed globally (`uv tool install cad`) installs
new releases of its own major version by itself, with no one asked, unless you turn
that off with `cad update auto off`; a new major version installs only when a person
runs `cad update --major`. At most once an hour, and as its server starts, cad asks
`api.texttocad.dev/v1/releases` which release is newest, of each major (releases before
0.11.12 ask `api.texttocad.dev/v1/versions`, which names nothing from 0.12.0 on). The feed
names a release only once it has been on PyPI for an hour, and we can hold a release back
from it. When the feed names a release of cad's major newer than cad's and nothing has
run for a minute, cad stops its server, runs its installer's own upgrade bounded to that
major (`uv tool install --upgrade "cad>=<installed>,<<next major>"`), which downloads
PyPI's newest release of `cad` in that range, and starts the server again. It never
installs an older release; where a failed upgrade left no `cad`, it puts back the
release that ran. A typed `cad update` asks PyPI which release of its major is newest
and runs the same upgrade; `cad update --major` runs `uv tool install --upgrade
"cad>=<installed>"`, PyPI's newest of all. Then, where `cad plugin update auto` is on, the
server of the newer cad (however it got newer: by itself, by `cad update`, or by an
upgrade by hand) downloads and runs the hosted install command once, unattended: it
fetches `install.sh` or `install.ps1` and `install.py` from texttocad.dev, and the
plugin from GitHub; a run that fails is tried again an hour or more later, at most
three runs for one release, and one still running after 15 minutes is stopped. So
with automatic updates on, whoever
controls `api.texttocad.dev` (which decides only when), `texttocad.dev`, the `cad`
project on PyPI or this repository's `latest` branch can run code as you.

**What else installs by itself.** The CAD app's server line in Codex's plugin
(`uvx ... cad@<release> mcp`) runs `uv tool install` for PyPI's newest `cad` of that
release's major where the computer has no global cad, and never over a `cad` of a higher
major. A computer that the updater of 0.10.0 to 0.11.11 brought to this release runs the
hosted install command, unattended, where our install command or an earlier release's
update had put our plugin there, and otherwise installs cad itself the same bounded way.
cad's own update never crosses a major, but the hosted install command, which cad runs by
itself there and after an update, is not bounded by major: it installs the newest plugin
of all, and, where cad is missing or does not start, PyPI's newest `cad` of all. No higher
major exists today, and the command, fetched at every run, is to keep a computer inside
its major before one ships.

### What we treat as a vulnerability

- Reaching the server, its files or its actions without the token, a link or
  the session cookie, or taking one of them, from another origin, another
  local user, or a file you open.
- A file from someone else that reads, writes or runs anything beyond what
  opening, viewing, exporting or snapshotting it should. This includes a file
  that makes the server do unbounded work or hold unbounded memory.
- An MCP tool that the model can use to act as the CAD app's page, or a frame
  that can act as its host.
- A way to publish to PyPI or the install branches (`latest`, `claude-plugin`,
  `codex-plugin`) other than a merged release, or to change what texttocad.dev
  serves as the install scripts.
- A way to make cad install, by itself, anything but a release of `cad` from
  PyPI, or to make it move to an older release than the one that ran.
- `api.texttocad.dev`: anything beyond its documented behaviour (version feed,
  consented analytics), including a way to make the feed name a release it should
  not.

Out of scope: what someone who already has your token, a link or
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
