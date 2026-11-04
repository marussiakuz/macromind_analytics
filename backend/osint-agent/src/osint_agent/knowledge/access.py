"""Workspace access control for knowledge API (Astra P1 §6.2).

No parallel user system: principals come from the existing internal token
and configured workspace tokens. Workspace is resolved on the server; the
client may only select among workspaces the principal is allowed to use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from fastapi import Header, HTTPException

from osint_agent.config import settings

PUBLIC_WORKSPACE = "public"


@dataclass(frozen=True)
class Principal:
    name: str
    # None → unrestricted (internal service token)
    allowed_workspaces: frozenset[str] | None = None
    is_service: bool = False

    def can_use(self, workspace_id: str | None) -> bool:
        if self.is_service or self.allowed_workspaces is None:
            return True
        ws = workspace_id or ""
        return ws in self.allowed_workspaces or ws == PUBLIC_WORKSPACE

    def resolve_workspace(self, requested: str | None) -> str | None:
        """Client workspace is a selector among allowed ones, not a grant."""
        if self.is_service or self.allowed_workspaces is None:
            return requested
        if requested is None or requested == "":
            # default: first allowed private workspace, else public
            priv = sorted(w for w in self.allowed_workspaces if w != PUBLIC_WORKSPACE)
            return priv[0] if priv else PUBLIC_WORKSPACE
        if not self.can_use(requested):
            raise HTTPException(403, detail="workspace access denied")
        return requested

    def workspace_filter(self, requested: str | None) -> str | None:
        """Value for SQL COALESCE(workspace_id,'') filters."""
        return self.resolve_workspace(requested)


def _parse_access_table(raw: str) -> dict[str, tuple[str, frozenset[str]]]:
    """Parse KNOWLEDGE_USER_ACCESS='alice:tok-a:ws-1|ws-2;bob:tok-b:ws-3'."""
    out: dict[str, tuple[str, frozenset[str]]] = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) < 2:
            continue
        name, token = bits[0].strip(), bits[1].strip()
        wss = frozenset(w.strip() for w in (bits[2] if len(bits) > 2 else "").split("|") if w.strip())
        if name and token:
            out[token] = (name, wss)
    return out


def _service_token() -> str:
    # Runtime env first (tests and service managers override the .env snapshot),
    # then settings loaded from .env.
    apply = os.environ.get("KNOWLEDGE_INTERNAL_TOKEN", "") or getattr(
        settings, "knowledge_internal_token", ""
    )
    return (apply or "").strip()


def resolve_principal(
    authorization: str | None = None,
    x_api_key: str | None = None,
    x_workspace_token: str | None = None,
) -> Principal:
    token = ""
    for raw in (authorization, x_api_key, x_workspace_token):
        if not raw:
            continue
        token = raw.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        break

    svc = _service_token()
    if svc and token == svc:
        return Principal(name="service", allowed_workspaces=None, is_service=True)

    raw_users = os.environ.get("KNOWLEDGE_USER_ACCESS", "")
    table = _parse_access_table(raw_users)
    if token and token in table:
        name, wss = table[token]
        return Principal(name=name, allowed_workspaces=wss, is_service=False)

    # No/unknown token: refuse private data. Empty access table + empty service
    # token would leave the API open — require at least one credential.
    raise HTTPException(401, detail="missing or unknown knowledge credentials")


async def current_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    x_workspace_token: str | None = Header(default=None, alias="X-Workspace-Token"),
) -> Principal:
    return resolve_principal(authorization, x_api_key, x_workspace_token)
