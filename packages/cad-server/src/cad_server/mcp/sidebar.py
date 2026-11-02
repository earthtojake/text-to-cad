"""Sidebar views shared by MCP sessions in one engine, entirely in memory."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from .views import NoAnswer, ViewRegistry


@dataclass
class SidebarView:
    id: str
    model: str | None
    state: dict[str, Any] = field(default_factory=dict)
    touched: float = 0.0


class SidebarViews:
    def __init__(self, registry: ViewRegistry | None = None):
        self.registry = registry if registry is not None else ViewRegistry()
        self.owned: set[str] = set()

    def publish(self, view_id, *, model, state, touched):
        self.owned.add(view_id)
        self.registry.register(view_id, surface='sidebar', thread_id=None, model=model)
        self.registry.report(view_id, model=model, state=state, focused=touched)

    def take(self, view_id):
        return self.registry.poll(view_id)

    def answer(self, request_id, reply):
        return self.registry.reply(request_id, reply)

    def forget(self, view_id):
        self.owned.discard(view_id)
        self.registry.forget(view_id)

    def close(self):
        for ident in list(self.owned):
            self.forget(ident)

    def live(self):
        return [SidebarView(view.id, view.model, dict(view.state), self.registry.wall(view.focused))
                for view in self.registry.live() if view.id not in self.owned]

    def post(self, view_id, event):
        self.registry.post([view_id], event)

    def ask(self, view_id, *, timeout=10.0):
        try:
            return self.registry.ask(view_id, 'capture', timeout=timeout)
        except NoAnswer:
            return None
