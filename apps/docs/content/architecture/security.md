---
title: Security and privacy
description: The trust boundary of the local CAD server, what a page can reach, what telemetry sends and how to turn it off, and how to report a vulnerability.
---

text-to-cad runs on your computer, as your user, with your files. [SECURITY.md](repo:SECURITY.md) is the full policy.

## Models are programs you run

A model is a Python script your agent writes and runs on your computer, with the rights of any script you run. Packages it names (in its `# /// script` header or `cad run --with`) are installed with uv, from the network. Review what your agent runs as you would any code.

## The door

Commands and model scripts reach the server through its door: named pipes in a folder only you can open (on Windows, a loopback port and a token in a file only you can read). A shell inside an agent's sandbox that can open the door builds with the server's rights, outside the sandbox. By design, the boundary is your user account, not the sandbox.

## Pages and links

The server serves the viewer and the CAD app's MCP endpoint over HTTP on `127.0.0.1` (port 3245 unless another program holds it). Every request needs one of three credentials made from one token:

- **The token**, kept in a file only you can read in your state folder (`engines/token`) and never put in a URL.
- **A link**, the `?token=` every URL text-to-cad prints or opens carries: an expiry and its signature. It works until you rotate the token, and only from this computer.
- **A session cookie**, which your browser gets when it opens a link: HttpOnly, SameSite=Strict, lasting 30 days from its last use.

> [!WARNING]
> Whoever holds a link or a session can read any CAD file on your computer by its path, list folders and export. Treat a link, and the address of an open CAD page, like a password, and do not bind a non-loopback `--host` unless you mean to offer that to everyone who can reach the port.

To end every link and session at once, stop the server with `cad stop`, then run `cad server --rotate-token`.

The server also refuses another Host (against DNS rebinding), cookie-only requests from other sites, and changes without a custom header. The CAD app's page tools need a capability the host keeps out of the model's context, so the agent cannot act as the page.

A CAD file from someone else is untrusted input: the server reads it in separate processes, bounds the work it can cause, and fetches nothing it names over the network.

## Telemetry and the version check

Telemetry is on by default once text-to-cad has told you: the first `cad` command says so, once, in its output, and nothing is sent before that. It sends usage counts and crash reports under a random install ID, never your files, models, file or folder names, prompts or anything you type. Nothing is sent by default in CI or from a development install.

To turn it off, run `cad telemetry off`, use **Telemetry** in the menu under CAD's logo, or install with:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --no-telemetry
```

Turning it off deletes the install ID and asks for everything stored under it to be deleted. `DO_NOT_TRACK=1` or `CAD_TELEMETRY=0` turns it off for one process and the builds it asks for.

At most once an hour, text-to-cad also asks `api.texttocad.dev` for the newest release, with no ID and nothing about you. `CAD_UPDATE_CHECK=0` turns that off, and automatic updates with it. The [privacy policy](https://www.texttocad.dev/privacy-policy) says exactly what is sent and how long it is kept.

## Reporting a vulnerability

Report it privately:

1. Use the repository's **Security tab, Report a vulnerability** (GitHub Security Advisories) on [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
2. Do not open a public issue or pull request for a security vulnerability.
3. Include a description, reproduction steps and the potential impact. A small file or command that shows the effect is the most useful. Do not run automated scans or load against `api.texttocad.dev`.

The maintainers aim to acknowledge a report within 48 hours and give a fix timeline within 7 days, and ask for time to address it before it is disclosed publicly. Only the latest release receives security fixes.

## Read more

- [SECURITY.md](repo:SECURITY.md) and the viewer's [usage stats](repo:apps/web/README.md#usage-stats-telemetry).
- [Architecture overview](/docs/architecture), [The engine](/docs/architecture/engine), [The viewer and the CAD app](/docs/architecture/viewer-and-cad-app) and [What is installed where](/docs/architecture/installation-layout).
