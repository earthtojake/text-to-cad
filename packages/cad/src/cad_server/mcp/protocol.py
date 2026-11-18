"""JSON-RPC 2.0 as the engine's MCP endpoint answers it: the error codes, an error a handler returns as
it is (``RpcError``), and what a handler knows of the request it serves (``RequestContext``). The stdio
transport a host starts speaks the same over its standard input and output (``cad_mcp.protocol``)."""

from __future__ import annotations

from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class RpcError(Exception):
    """A JSON-RPC error the handler wants returned to the caller as-is."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


class RequestContext:
    """What a handler knows about the request it is serving."""

    __slots__ = ("request_id", "meta")

    def __init__(self, request_id: Any, meta: dict[str, Any]) -> None:
        self.request_id = request_id
        self.meta = meta
