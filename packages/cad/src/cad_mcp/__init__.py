"""CAD beside an agent's chat: ``cad mcp``, the stdio transport an agent app starts (``shim``).

It starts this release's server as ``cad server start`` does, once, as it starts, and forwards MCP to it over HTTP
through the library's client (``cad.engine.client``). It installs nothing. Everything CAD is, the server is: this
process carries the host's requests to it and its answers back, opens the person's browser where a text host's
``cad_show`` asks (``browser``), and tells the server which host started it (``host``). ``cad-mcp``, the command of
releases before, is the same entry point.
"""
