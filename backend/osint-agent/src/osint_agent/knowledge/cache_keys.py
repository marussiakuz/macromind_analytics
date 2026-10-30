"""LLM cache keys must include corpus snapshot AND access scope (2026-10-22).

§6.5 p.4 + ACL: a cached answer generated for workspace A must never be
served to workspace B or to a principal with a different allowed set.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _norm_acl(access: Any) -> list[str]:
    """Stable ACL fingerprint. None → empty (service/unrestricted is explicit)."""
    if access is None:
        return ["*"]
    if isinstance(access, str):
        return [access]
    try:
        return sorted(str(x) for x in access)
    except TypeError:
        return [str(access)]


def corpus_snapshot_id(
    *,
    workspace_id: str | None,
    document_ids: list[str] | None = None,
    allowed_workspaces: Any = None,
    extra: dict | None = None,
) -> str:
    """Stable id for the corpus + ACL state used in a generation call."""
    doc_key = sorted(str(d) for d in (document_ids or []))
    payload = {
        "workspace_id": workspace_id or "",
        "documents": doc_key,
        "acl": _norm_acl(allowed_workspaces),
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_key_with_corpus(
    *,
    model: str,
    prompt_version: str,
    system: str,
    payload: dict[str, Any],
    workspace_id: str | None = None,
    document_ids: list[str] | None = None,
    allowed_workspaces: Any = None,
) -> str:
    """Cache key that cannot collide across corpus snapshots OR access scopes."""
    snap = corpus_snapshot_id(
        workspace_id=workspace_id,
        document_ids=document_ids,
        allowed_workspaces=allowed_workspaces,
    )
    body = {
        "model": model,
        "prompt_version": prompt_version,
        "system": system,
        "payload": payload,
        "corpus_snapshot": snap,
        "acl": _norm_acl(allowed_workspaces),
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
