# Security Policy

## Scope

text-to-cad is a local-filesystem development tool. The CAD Viewer backend
(`viewer/server_py`) binds to loopback (`127.0.0.1`) by default and serves
**unauthenticated**. Any local process can read files under the directory the
viewer opens, trigger STEP builds/exports, and activate directories.

This is a single-user, local-filesystem viewer: **loopback binding is the
trust boundary**. Do NOT bind a non-loopback `--host` or expose this server
beyond localhost without adding authentication.

## Reporting a Vulnerability

If you discover a security vulnerability, report it privately:

1. Use the repository's **Security tab → Report a vulnerability**
   (GitHub Security Advisories).
2. Do **NOT** open a public issue or pull request for a security
   vulnerability.
3. Include a description, reproduction steps, and potential impact.

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
